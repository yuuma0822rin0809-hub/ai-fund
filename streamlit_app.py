import json
import re
from pathlib import Path

import requests
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

WATCHLIST_PATH = Path(__file__).with_name("watchlist.json")

# ページ設定
st.set_page_config(page_title="AI Smart Trader", layout="wide")
st.title("🎯 AI Smart Trader - インテリジェント投資判定システム")

# サイドバー設定
st.sidebar.header("⚙️ 設定")
risk_percent = st.sidebar.slider("損失許容率 (%)", 0.5, 5.0, 1.0, 0.1)
profit_target = st.sidebar.slider("利確目標 (%)", 1.0, 10.0, 3.0, 0.5)
period = st.sidebar.selectbox("分析期間", ["1mo", "3mo", "6mo", "1y", "2y"], index=3)


def currency_symbol(code: str) -> str:
    return "¥" if code.upper().endswith(".T") else "$"


def normalize_code(text: str) -> str:
    """LINE と同じルール：4桁の数字（285A のような英数字も）なら .T を自動で付ける。
    全角の数字・英字は半角に直す。"""
    code = (text or "").strip().upper()
    code = "".join(chr(ord(c) - 0xFEE0) if "０" <= c <= "９" or "Ａ" <= c <= "Ｚ" else c for c in code)
    if re.fullmatch(r"\d{4}", code) or re.fullmatch(r"\d{3}[A-Z]", code):
        code += ".T"
    return code


@st.cache_data(ttl=600, show_spinner=False)
def load_watchlist_names() -> dict:
    """LINE で登録した watchlist.json の銘柄名を読む（無ければ空）。"""
    try:
        data = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
        return data.get("names", {}) or {}
    except Exception:
        return {}


@st.cache_data(ttl=86400, show_spinner=False)
def lookup_name(code: str) -> str:
    """銘柄名を返す。watchlist.json に無ければ Yahoo!ファイナンス（日本版）の
    ページタイトルから取る（GAS と同じ方法。日本株・米国株どちらも日本語名が取れる）。"""
    names = load_watchlist_names()
    if names.get(code):
        return names[code]
    try:
        res = requests.get(
            f"https://finance.yahoo.co.jp/quote/{code}",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=8,
        )
        if res.status_code != 200:
            return ""
        m = re.search(r"<title>([^<]+)</title>", res.text)
        if not m or "【" not in m.group(1):
            return ""
        name = m.group(1).split("【")[0].replace("(株)", "").replace("株式会社", "").strip()
        return name if 0 < len(name) <= 24 else ""
    except Exception:
        return ""


def display_name(code: str) -> str:
    name = lookup_name(code)
    return f"{name}（{code}）" if name else code


@st.cache_data(ttl=300, show_spinner=False)
def fetch_history(code: str, term: str) -> pd.DataFrame:
    """yf.Ticker().history() を使う。yf.download() と違い列が単純構造で返るため
    yfinance のバージョン差でカラム構造が壊れない。"""
    df = yf.Ticker(code).history(period=term, auto_adjust=True)
    if df is None or df.empty:
        return pd.DataFrame()
    return df.dropna(subset=["Close"])


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["MA20"] = out["Close"].rolling(window=20).mean()
    out["MA200"] = out["Close"].rolling(window=200).mean()
    delta = out["Close"].diff()
    gain = delta.clip(lower=0).rolling(window=14).mean()
    loss = (-delta.clip(upper=0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, pd.NA)
    out["RSI"] = 100 - (100 / (1 + rs))
    return out


# タブ作成
tab1, tab2, tab3 = st.tabs(["📊 銘柄分析", "🎯 シグナル判定", "📈 テクニカル指標"])

with tab1:
    st.subheader("銘柄情報入力")
    ticker = st.text_input("銘柄コード入力", value="7974", help="例：7974（任天堂）、285A（キオクシア）、AAPL（Apple）。日本株は4桁だけでOK")

    if st.button("📥 分析開始") and ticker:
        code = normalize_code(ticker)
        with st.spinner(f"{code} のデータを取得中..."):
            data = fetch_history(code, period)
            shown = display_name(code)

        if data.empty:
            st.error(f"❌ {code} のデータが見つかりません。銘柄コードを確認してください。")
        else:
            st.markdown(f"## 🏷️ {shown}")
            sym = currency_symbol(code)
            latest_price = float(data["Close"].iloc[-1])
            prev_close = float(data["Close"].iloc[-2]) if len(data) > 1 else latest_price
            change_percent = ((latest_price - prev_close) / prev_close * 100) if prev_close else 0.0

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("現在値", f"{sym}{latest_price:,.2f}")
            col2.metric("前日比", f"{change_percent:+.2f}%")
            col3.metric("データ期間", f"{len(data)}日")
            col4.metric("取得日時", datetime.now().strftime("%Y-%m-%d %H:%M"))

            st.subheader("📈 株価推移")
            st.line_chart(data["Close"])

            st.session_state.ticker = code
            st.session_state.name = shown
            st.session_state.data = data
            st.success(f"✅ {shown} の分析準備完了（他のタブで判定を確認できます）")

with tab2:
    st.subheader("🎯 買い・売りシグナル")
    if "data" in st.session_state:
        code = st.session_state.get("ticker", "")
        st.markdown(f"#### 🏷️ {st.session_state.get('name', code)}")
        sym = currency_symbol(code)
        df = add_indicators(st.session_state.data)
        latest = df.iloc[-1]
        current_price = float(latest["Close"])

        signals = []
        confidence = 0

        ma20, ma200, rsi = latest["MA20"], latest["MA200"], latest["RSI"]

        if pd.notna(ma20) and pd.notna(ma200):
            if ma20 > ma200:
                signals.append("🟢 MA: 上昇トレンド（MA20 > MA200）")
                confidence += 30
            else:
                signals.append("🔴 MA: 下降トレンド（MA20 < MA200）")
                confidence -= 30
        else:
            signals.append("⚪ MA: データ不足（分析期間を長くしてください）")

        if pd.notna(rsi):
            if rsi < 30:
                signals.append(f"🟢 RSI: 売られ過ぎ・買いシグナル（{rsi:.1f}）")
                confidence += 40
            elif rsi > 70:
                signals.append(f"🔴 RSI: 買われ過ぎ・売りシグナル（{rsi:.1f}）")
                confidence -= 40
            else:
                signals.append(f"🟡 RSI: 中立（{rsi:.1f}）")
        else:
            signals.append("⚪ RSI: データ不足")

        if confidence >= 60:
            recommendation = "🟢 **買い推奨**"
        elif confidence <= -60:
            recommendation = "🔴 **売り推奨**"
        else:
            recommendation = "🟡 **様子見**"

        st.markdown(f"### {recommendation}")
        st.metric("信頼度スコア", f"{confidence}/100")

        st.write("**テクニカルシグナル**")
        for signal in signals:
            st.write(signal)

        st.write("**リスク管理レベル**")
        col1, col2 = st.columns(2)
        col1.write(f"🛑 損切りレベル：{sym}{current_price * (1 - risk_percent / 100):,.2f}")
        col2.write(f"💰 利確レベル：{sym}{current_price * (1 + profit_target / 100):,.2f}")
    else:
        st.info("「📊 銘柄分析」タブで銘柄を分析してから、このタブを開いてください")

with tab3:
    st.subheader("📊 テクニカル指標詳細")
    if "data" in st.session_state:
        st.markdown(f"#### 🏷️ {st.session_state.get('name', st.session_state.get('ticker', ''))}")
        df = add_indicators(st.session_state.data)
        col1, col2 = st.columns(2)
        with col1:
            st.write("**移動平均線（MA）**")
            st.line_chart(df[["Close", "MA20", "MA200"]].tail(100))
        with col2:
            st.write("**相対力指数（RSI）**")
            st.line_chart(df[["RSI"]].tail(100))
    else:
        st.info("「📊 銘柄分析」タブで銘柄を分析してから、このタブを開いてください")

st.sidebar.markdown("---")
st.sidebar.info("💡 このアプリは投資判定の参考です。最終判断はご自身の責任でお願いします。")
