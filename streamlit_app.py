import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import json

# ページ設定
st.set_page_config(page_title="AI Smart Trader", layout="wide")
st.title("🎯 AI Smart Trader - インテリジェント投資判定システム")

# サイドバー設定
st.sidebar.header("⚙️ 設定")
risk_percent = st.sidebar.slider("損失許容率 (%)", 0.5, 5.0, 1.0, 0.1)
profit_target = st.sidebar.slider("利確目標 (%)", 1.0, 10.0, 3.0, 0.5)
period = st.sidebar.selectbox("分析期間", ["1mo", "3mo", "6mo", "1y", "2y"])

# タブ作成
tab1, tab2, tab3 = st.tabs(["📊 銘柄分析", "🎯 シグナル判定", "📈 テクニカル指標"])

with tab1:
    st.subheader("銘柄情報入力")
    ticker = st.text_input("銘柄コード入力", value="7201.T", help="例：7201.T（日産）、AAPL（Apple）")
    
    if ticker and st.button("📥 分析開始"):
        try:
            st.info(f"📥 {ticker} のデータを取得中...")
            data = yf.download(ticker, period=period, progress=False)
            
            if not data.empty:
                latest_price = float(data['Close'].iloc[-1])
                prev_close = float(data['Close'].iloc[-2]) if len(data) > 1 else latest_price
                change_percent = ((latest_price - prev_close) / prev_close * 100) if prev_close != 0 else 0
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("現在値", f"¥{latest_price:.2f}")
                with col2:
                    st.metric("前日比", f"{change_percent:+.2f}%")
                with col3:
                    st.metric("データ期間", f"{len(data)}日")
                with col4:
                    st.metric("取得日時", datetime.now().strftime("%Y-%m-%d %H:%M"))
                
                st.subheader("📈 株価推移")
                st.line_chart(data['Close'])
                
                st.success(f"✅ {ticker} の分析準備完了")
                st.session_state.ticker = ticker
                st.session_state.data = data
            else:
                st.error(f"❌ {ticker} のデータが見つかりません")
        except Exception as e:
            st.error(f"❌ エラー: {str(e)}")

with tab2:
    st.subheader("🎯 買い・売いシグナル")
    if 'data' in st.session_state:
        data = st.session_state.data
        try:
            data['MA20'] = data['Close'].rolling(window=20).mean()
            data['MA200'] = data['Close'].rolling(window=200).mean()
            
            delta = data['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            data['RSI'] = 100 - (100 / (1 + rs))
            
            latest = data.iloc[-1]
            current_price = latest['Close']
            
            signals = []
            confidence = 0
            
            if latest['MA20'] > latest['MA200']:
                signals.append("🟢 MA: 上昇トレンド")
                confidence += 30
            else:
                signals.append("🔴 MA: 下降トレンド")
                confidence -= 30
            
            if latest['RSI'] < 30:
                signals.append("🟢 RSI: 過売れ（買いシグナル）")
                confidence += 40
            elif latest['RSI'] > 70:
                signals.append("🔴 RSI: 過買い（売りシグナル）")
                confidence -= 40
            else:
                signals.append(f"🟡 RSI: 中立（{latest['RSI']:.1f}）")
            
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
            with col1:
                stop_loss = current_price * (1 - risk_percent / 100)
                st.write(f"🛑 損切りレベル：¥{stop_loss:.2f}")
            with col2:
                take_profit = current_price * (1 + profit_target / 100)
                st.write(f"💰 利確レベル：¥{take_profit:.2f}")
        except Exception as e:
            st.error(f"エラー: {str(e)}")
    else:
        st.info("左のタブで銘柄を分析してからこのタブを表示してください")

with tab3:
    st.subheader("📊 テクニカル指標詳細")
    if 'data' in st.session_state:
        data = st.session_state.data
        try:
            data['MA20'] = data['Close'].rolling(window=20).mean()
            data['MA200'] = data['Close'].rolling(window=200).mean()
            
            col1, col2 = st.columns(2)
            with col1:
                st.write("**移動平均線（MA）**")
                ma_data = data[['Close', 'MA20', 'MA200']].tail(100)
                st.line_chart(ma_data)
            with col2:
                st.write("**相対力指数（RSI）**")
                delta = data['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                st.line_chart(rsi.tail(100))
        except Exception as e:
            st.error(f"エラー: {str(e)}")

st.sidebar.markdown("---")
st.sidebar.info("💡 このアプリは投資判定の参考です。最終判断はご自身の責任でお願いします。")
