import pandas as pd
import numpy as np

def calculate_moving_average(data, window=20):
    """
    移動平均線を計算する関数
    
    Args:
        data (pd.DataFrame): 株価データフレーム
        window (int): 期間（デフォルト：20日）
    
    Returns:
        pd.Series: 移動平均線
    """
    return data['Close'].rolling(window=window).mean()

def calculate_rsi(data, window=14):
    """
    RSI（相対力指数）を計算する関数
    
    Args:
        data (pd.DataFrame): 株価データフレーム
        window (int): 期間（デフォルト：14日）
    
    Returns:
        pd.Series: RSI値
    """
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(data, fast=12, slow=26, signal=9):
    """
    MACD（移動平均収束発散）を計算する関数
    
    Args:
        data (pd.DataFrame): 株価データフレーム
        fast (int): 高速EMA期間（デフォルト：12日）
        slow (int): 低速EMA期間（デフォルト：26日）
        signal (int): シグナル期間（デフォルト：9日）
    
    Returns:
        tuple: (MACD, Signal, Histogram)
    """
    ema_fast = data['Close'].ewm(span=fast).mean()
    ema_slow = data['Close'].ewm(span=slow).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal).mean()
    histogram = macd - signal_line
    
    return macd, signal_line, histogram

def analyze_technical(data):
    """
    テクニカル指標を一括計算して結果を返す関数
    
    Args:
        data (pd.DataFrame): 株価データフレーム
    
    Returns:
        pd.DataFrame: 各指標を含むデータフレーム
    """
    result = data.copy()
    
    # 移動平均線（20日、200日）
    result['MA20'] = calculate_moving_average(data, window=20)
    result['MA200'] = calculate_moving_average(data, window=200)
    
    # RSI
    result['RSI'] = calculate_rsi(data, window=14)
    
    # MACD
    macd, signal, histogram = calculate_macd(data)
    result['MACD'] = macd
    result['MACD_Signal'] = signal
    result['MACD_Histogram'] = histogram
    
    return result

if __name__ == "__main__":
    # テスト用：stock_fetcher.py のデータを使用
    from stock_fetcher import fetch_stock_data
    
    print("=== テクニカル指標計算テスト ===\n")
    
    ticker = "AAPL"
    print(f"銘柄: {ticker}\n")
    
    # データ取得
    data = fetch_stock_data(ticker, period="6mo")
    
    if data is not None:
        # テクニカル指標を計算
        analysis = analyze_technical(data)
        
        print("✅ テクニカル指標計算成功\n")
        print("直近5日の指標:")
        print(analysis[['Close', 'MA20', 'MA200', 'RSI', 'MACD']].tail(5))
    else:
        print("❌ データ取得失敗")