"""判定の変化と、保有銘柄の利益目標到達を LINE に通知するスクリプト。

GitHub Actions から1日1回実行される想定。

watchlist.json  … 監視する銘柄と銘柄名
holdings.json   … 保有株数・取得単価・利益目標・損切りライン・通知モード
signal_state.json … 前回の判定と通知済みフラグ（自動生成）
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

import requests
import yfinance as yf

JST = timezone(timedelta(hours=9))
WATCHLIST_FILE = "watchlist.json"
HOLDINGS_FILE = "holdings.json"
STATE_FILE = "signal_state.json"
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"

NAMES = {}


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"{path} を読めませんでした: {e}")
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def label(code):
    name = NAMES.get(code)
    return f"{name}（{code}）" if name else code


def judge(code):
    """MA20/MA200 と RSI14 から判定を出す。(判定, スコア, 現在値, 明細) を返す。"""
    df = yf.Ticker(code).history(period="1y", auto_adjust=True)
    if df is None or df.empty:
        return None
    df = df.dropna(subset=["Close"])
    if df.empty:
        return None

    close = df["Close"]
    ma20 = close.rolling(window=20).mean()
    ma200 = close.rolling(window=200).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=14).mean()
    loss = (-delta.clip(upper=0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))

    price = float(close.iloc[-1])
    v_ma20 = ma20.iloc[-1]
    v_ma200 = ma200.iloc[-1]
    v_rsi = rsi.iloc[-1]

    confidence = 0
    detail = []

    if v_ma20 == v_ma20 and v_ma200 == v_ma200:
        if v_ma20 > v_ma200:
            confidence += 30
            detail.append("MA: 上昇トレンド")
        else:
            confidence -= 30
            detail.append("MA: 下降トレンド")
    else:
        detail.append("MA: データ不足")

    if v_rsi == v_rsi:
        if v_rsi < 30:
            confidence += 40
            detail.append(f"RSI: 売られ過ぎ ({v_rsi:.1f})")
        elif v_rsi > 70:
            confidence -= 40
            detail.append(f"RSI: 買われ過ぎ ({v_rsi:.1f})")
        else:
            detail.append(f"RSI: 中立 ({v_rsi:.1f})")
    else:
        detail.append("RSI: データ不足")

    if confidence >= 60:
        signal = "買い推奨"
    elif confidence <= -60:
        signal = "売り推奨"
    else:
        signal = "様子見"

    return signal, confidence, price, detail


def currency_of(code):
    return "¥" if code.upper().endswith(".T") else "$"


def threshold_value(rule, cost, qty):
    """目標・損切りの設定を「金額」に換算する。

    rule の例: {"type": "amount", "value": 30000} / {"type": "percent", "value": 10}
    """
    if not rule:
        return None
    try:
        value = float(rule.get("value"))
    except (TypeError, ValueError):
        return None
    kind = rule.get("type", "amount")
    if kind == "percent":
        return cost * qty * value / 100.0
    return value


def evaluate_holding(code, price, holding, state_entry):
    """保有銘柄の損益を見て、通知すべきことがあれば文面を返す。"""
    try:
        qty = float(holding.get("qty", 0))
        cost = float(holding.get("cost", 0))
    except (TypeError, ValueError):
        return None, state_entry
    if qty <= 0 or cost <= 0:
        return None, state_entry

    sym = currency_of(code)
    profit = (price - cost) * qty
    profit_pct = (price - cost) / cost * 100.0

    target = threshold_value(holding.get("target"), cost, qty)
    stop = threshold_value(holding.get("stop"), cost, qty)

    target_hit = bool(state_entry.get("target_hit"))
    stop_hit = bool(state_entry.get("stop_hit"))

    head = None

    if target is not None and profit >= target:
        if not target_hit:
            head = "💰 目標達成"
        state_entry["target_hit"] = True
    else:
        state_entry["target_hit"] = False

    if stop is not None and profit <= stop:
        if not stop_hit:
            head = "🛑 損切りライン到達"
        state_entry["stop_hit"] = True
    else:
        state_entry["stop_hit"] = False

    if head is None:
        return None, state_entry

    qty_text = f"{qty:,.0f}".rstrip("0").rstrip(".") if qty % 1 else f"{qty:,.0f}"
    body = (
        f"■ {label(code)}\n"
        f"　{head}\n"
        f"　現在 {sym}{price:,.2f} / 取得 {sym}{cost:,.2f}\n"
        f"　{qty_text}株 → 損益 {sym}{profit:+,.0f}（{profit_pct:+.1f}%）"
    )
    return body, state_entry


def send_line(text):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    if not token:
        print("LINE_CHANNEL_ACCESS_TOKEN が未設定のため送信をスキップしました")
        print("--- 送信予定だった内容 ---")
        print(text)
        return False

    res = requests.post(
        LINE_BROADCAST_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"messages": [{"type": "text", "text": text[:4900]}]},
        timeout=30,
    )
    if res.status_code == 200:
        print("LINE 送信成功")
        return True
    print(f"LINE 送信失敗: {res.status_code} {res.text}")
    return False


def main():
    global NAMES

    watchlist = load_json(WATCHLIST_FILE, {"tickers": []})
    tickers = watchlist.get("tickers", [])
    NAMES = watchlist.get("names", {}) or {}
    if not tickers:
        print("watchlist.json に銘柄がありません")
        return 0

    holdings_file = load_json(HOLDINGS_FILE, {})
    holdings = holdings_file.get("holdings", {}) or {}
    mode = holdings_file.get("notify_mode", "both")
    if mode not in ("both", "signal", "profit"):
        mode = "both"

    state = load_json(STATE_FILE, {})
    first_run = not state

    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    signal_lines = []
    profit_lines = []
    all_lines = []
    errors = []

    for code in tickers:
        try:
            result = judge(code)
        except Exception as e:
            errors.append(f"{label(code)}: 取得エラー ({type(e).__name__})")
            continue

        if result is None:
            errors.append(f"{label(code)}: データが取得できませんでした")
            continue

        signal, confidence, price, detail = result
        sym = currency_of(code)
        entry = dict(state.get(code, {}))

        all_lines.append(
            f"■ {label(code)}\n"
            f"　{signal}（{confidence:+d}）　{sym}{price:,.2f}\n"
            f"　" + " / ".join(detail)
        )

        prev = entry.get("signal")
        if prev is not None and prev != signal:
            signal_lines.append(
                f"■ {label(code)}\n"
                f"　{prev} → {signal}（{confidence:+d}）\n"
                f"　{sym}{price:,.2f}　" + " / ".join(detail)
            )

        holding = holdings.get(code)
        if holding:
            body, entry = evaluate_holding(code, price, holding, entry)
            if body:
                profit_lines.append(body + f"\n　判定：{signal}（{confidence:+d}）")

        entry.update({
            "name": NAMES.get(code, ""),
            "signal": signal,
            "confidence": confidence,
            "price": round(price, 4),
            "updated_at": now,
        })
        state[code] = entry

    save_json(STATE_FILE, state)

    if first_run:
        body = f"[AI Smart Trader] 通知テスト・初回登録\n{now} 時点の判定です。\n\n" + "\n\n".join(all_lines)
        body += "\n\n次回からは、条件に合ったときだけ通知します。"
        send_line(body)
        return 0

    sections = []
    if mode in ("both", "signal") and signal_lines:
        sections.append("【判定が変わりました】\n\n" + "\n\n".join(signal_lines))
    if mode in ("both", "profit") and profit_lines:
        sections.append("【利益・損切りの目安に到達】\n\n" + "\n\n".join(profit_lines))

    if sections:
        send_line(f"[AI Smart Trader]\n{now}\n\n" + "\n\n\n".join(sections))
    else:
        print(f"通知なし（モード: {mode}）")
        for line in all_lines:
            print(line)

    if errors:
        print("エラーがありました:")
        for e in errors:
            print(" ", e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
