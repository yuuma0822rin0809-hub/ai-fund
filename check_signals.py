"""判定が変わった銘柄だけを LINE に通知するスクリプト。

GitHub Actions から1日1回実行される想定。
watchlist.json の銘柄について streamlit_app.py と同じロジックで判定を出し、
signal_state.json に記録した前回の判定と比べて、変わったものだけ通知する。
watchlist.json の names に銘柄名を書いておくと、通知に銘柄名が表示される。
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

import requests
import yfinance as yf

JST = timezone(timedelta(hours=9))
WATCHLIST_FILE = "watchlist.json"
STATE_FILE = "signal_state.json"
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"

NAMES = {}


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def label(code):
    """通知に出す見出し。銘柄名が分かれば「名前（コード）」、無ければコードのみ。"""
    name = NAMES.get(code)
    return f"{name}（{code}）" if name else code


def judge(code):
    """streamlit_app.py と同じ判定ロジック。(判定, スコア, 現在値, 明細) を返す。"""
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

    if v_ma20 == v_ma20 and v_ma200 == v_ma200:  # NaN でない
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

    state = load_json(STATE_FILE, {})
    first_run = not state

    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    changed_lines = []
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
        currency = "¥" if code.upper().endswith(".T") else "$"
        all_lines.append(
            f"■ {label(code)}\n"
            f"　{signal}（{confidence:+d}）　{currency}{price:,.2f}\n"
            f"　" + " / ".join(detail)
        )

        prev = state.get(code, {}).get("signal")
        if prev is not None and prev != signal:
            changed_lines.append(
                f"■ {label(code)}\n"
                f"　{prev} → {signal}（{confidence:+d}）\n"
                f"　{currency}{price:,.2f}　" + " / ".join(detail)
            )

        state[code] = {
            "name": NAMES.get(code, ""),
            "signal": signal,
            "confidence": confidence,
            "price": round(price, 4),
            "updated_at": now,
        }

    save_json(STATE_FILE, state)

    if first_run:
        body = f"[AI Smart Trader] 通知テスト・初回登録\n{now} 時点の判定です。\n\n" + "\n\n".join(all_lines)
        body += "\n\n次回からは、判定が変わったときだけ通知します。"
        send_line(body)
    elif changed_lines:
        body = f"[AI Smart Trader] 判定が変わりました\n{now}\n\n" + "\n\n".join(changed_lines)
        send_line(body)
    else:
        print("判定に変化なし。通知は送りません。")
        for line in all_lines:
            print(line)

    if errors:
        print("エラーがありました:")
        for e in errors:
            print(" ", e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
