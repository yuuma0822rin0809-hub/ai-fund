import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

def fetch_stock_data(ticker, period="3mo"):
    """
    株価データを取得する関数
    
    Args:
        ticker (str): 銘柄コード（例："AAPL", "9984"）
        period (str): 期間（デフォルト：3ヶ月）
    
    Returns:
        pd.DataFrame: 株価データフレーム
    """
    try:
        data = yf.download(ticker, period=period, progress=False)
        return data
    except Exception as e:
        print(f"エラー: {ticker} のデータ取得に失敗しました。{e}")
        return None

if __name__ == "__main__":
    # テスト：AAPL（Apple）の過去3ヶ月のデータを取得
    print("=== 株価データ取得テスト ===\n")
    
    ticker = "AAPL"
    print(f"銘柄: {ticker}")
    print(f"期間: 過去3ヶ月\n")
    
    # データ取得
    data = fetch_stock_data(ticker)
    
    if data is not None:
        print("✅ データ取得成功\n")
        print("直近5日のデータ:")
        print(data.tail(5))
        
        # 最新株価を取得
        latest_price = data['Close'].iloc[-1].item()
        print(f"\n最新株価: ${latest_price:.2f}")
    else:
        print("❌ データ取得失敗")