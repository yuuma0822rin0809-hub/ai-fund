import pandas as pd
from stock_fetcher import fetch_stock_data, get_latest_price
from technical_indicators import analyze_technical
from portfolio_manager import PortfolioManager

def analyze_stock(ticker, period="6mo"):
    """
    単一銘柄を分析する関数
    """
    print(f"\n📊 {ticker} を分析中...")
    
    try:
        data = fetch_stock_data(ticker, period=period)
        if data is None:
            return None
        
        analysis = analyze_technical(data)
        
        latest_data = analysis.iloc[-1]
        current_price = get_latest_price(ticker)
        
        if current_price is None:
            return None
        
        try:
            ma20_val = float(latest_data['MA20']) if latest_data['MA20'] == latest_data['MA20'] else None
        except:
            ma20_val = None
        
        try:
            ma200_val = float(latest_data['MA200']) if latest_data['MA200'] == latest_data['MA200'] else None
        except:
            ma200_val = None
        
        try:
            rsi_val = float(latest_data['RSI']) if latest_data['RSI'] == latest_data['RSI'] else None
        except:
            rsi_val = None
        
        try:
            macd_val = float(latest_data['MACD']) if latest_data['MACD'] == latest_data['MACD'] else None
        except:
            macd_val = None
        
        result = {
            "ticker": ticker,
            "current_price": current_price,
            "ma20": ma20_val,
            "ma200": ma200_val,
            "rsi": rsi_val,
            "macd": macd_val,
        }
        
        return result
    except Exception as e:
        print(f"⚠️  {ticker} の分析に失敗しました: {e}")
        return None

def print_analysis_report(analysis_results):
    """
    分析結果レポートを表示
    """
    print("\n" + "=" * 110)
    print("📈 株価分析レポート")
    print("=" * 110)
    print()
    
    print("【銘柄分析】")
    print(f"{'銘柄':<10} {'現在値':<15} {'MA20':<15} {'MA200':<15} {'RSI':<12} {'MACD':<15}")
    print("-" * 110)
    
    for result in analysis_results:
        if result is None:
            continue
        
        ma20_str = f"${result['ma20']:.2f}" if result['ma20'] is not None else "計算中"
        ma200_str = f"${result['ma200']:.2f}" if result['ma200'] is not None else "計算中"
        rsi_str = f"{result['rsi']:.2f}" if result['rsi'] is not None else "計算中"
        macd_str = f"{result['macd']:.4f}" if result['macd'] is not None else "計算中"
        
        print(f"{result['ticker']:<10} ${result['current_price']:<14.2f} {ma20_str:<15} {ma200_str:<15} {rsi_str:<12} {macd_str:<15}")
    
    print()

def print_trading_signals(analysis_results):
    """
    トレードシグナルを表示
    """
    print("\n【トレードシグナル】")
    print(f"{'銘柄':<10} {'シグナル':<25} {'理由':<60}")
    print("-" * 110)
    
    for result in analysis_results:
        if result is None:
            continue
        
        signals = []
        reasons = []
        
        if result['ma20'] is not None and result['ma200'] is not None:
            if result['ma20'] > result['ma200']:
                signals.append("🟢 買い")
                reasons.append("MA20 > MA200（上昇トレンド）")
            else:
                signals.append("🔴 売り")
                reasons.append("MA20 < MA200（下降トレンド）")
        
        if result['rsi'] is not None:
            if result['rsi'] < 30:
                signals.append("🟢 買い")
                reasons.append("RSI < 30（過売れ）")
            elif result['rsi'] > 70:
                signals.append("🔴 売り")
                reasons.append("RSI > 70（過買い）")
        
        signal_text = " / ".join(signals) if signals else "様子見"
        reason_text = " / ".join(reasons) if reasons else "明確なシグナルなし"
        
        print(f"{result['ticker']:<10} {signal_text:<25} {reason_text:<60}")
    
    print()

def main():
    """
    メイン処理
    """
    print("=" * 110)
    print("🚀 AI ファンド - 株価分析システム")
    print("=" * 110)
    
    tickers = ["AAPL", "MSFT"]
    
    analysis_results = []
    for ticker in tickers:
        result = analyze_stock(ticker, period="6mo")
        analysis_results.append(result)
    
    print_analysis_report(analysis_results)
    print_trading_signals(analysis_results)
    
    print("\n【ポートフォリオ情報】")
    pm = PortfolioManager()
    pm.print_portfolio_summary()

if __name__ == "__main__":
    main()