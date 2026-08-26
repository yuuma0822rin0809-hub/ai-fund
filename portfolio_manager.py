import json
import os
from datetime import datetime
from stock_fetcher import get_latest_price
import pandas as pd

class PortfolioManager:
    def __init__(self, portfolio_file="portfolio.json"):
        """
        ポートフォリオマネージャーの初期化
        
        Args:
            portfolio_file (str): ポートフォリオデータファイル名
        """
        self.portfolio_file = portfolio_file
        self.portfolio = self.load_portfolio()
    
    def load_portfolio(self):
        """
        ポートフォリオデータをJSONファイルから読み込む
        
        Returns:
            dict: ポートフォリオデータ
        """
        if os.path.exists(self.portfolio_file):
            with open(self.portfolio_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            return {"holdings": {}, "created_at": datetime.now().isoformat()}
    
    def save_portfolio(self):
        """
        ポートフォリオデータをJSONファイルに保存
        """
        with open(self.portfolio_file, 'w', encoding='utf-8') as f:
            json.dump(self.portfolio, f, ensure_ascii=False, indent=2)
    
    def add_holding(self, ticker, quantity, buy_price):
        """
        銘柄をポートフォリオに追加
        
        Args:
            ticker (str): 銘柄コード
            quantity (float): 保有数量
            buy_price (float): 購入価格
        """
        if ticker not in self.portfolio["holdings"]:
            self.portfolio["holdings"][ticker] = {
                "quantity": 0,
                "buy_price": 0,
                "total_cost": 0,
                "added_at": datetime.now().isoformat()
            }
        
        holding = self.portfolio["holdings"][ticker]
        total_cost = holding["total_cost"] + (quantity * buy_price)
        total_quantity = holding["quantity"] + quantity
        avg_price = total_cost / total_quantity if total_quantity > 0 else 0
        
        holding["quantity"] = total_quantity
        holding["buy_price"] = avg_price
        holding["total_cost"] = total_cost
        
        self.save_portfolio()
    
    def remove_holding(self, ticker):
        """
        銘柄をポートフォリオから削除
        
        Args:
            ticker (str): 銘柄コード
        """
        if ticker in self.portfolio["holdings"]:
            del self.portfolio["holdings"][ticker]
            self.save_portfolio()
    
    def get_portfolio_value(self):
        """
        ポートフォリオの現在値を計算
        
        Returns:
            dict: 各銘柄の現在値、総資産額
        """
        portfolio_value = {}
        total_value = 0
        total_cost = 0
        
        for ticker, holding in self.portfolio["holdings"].items():
            try:
                current_price = get_latest_price(ticker)
                if current_price is not None:
                    current_value = holding["quantity"] * current_price
                    gain_loss = current_value - holding["total_cost"]
                    gain_loss_percent = (gain_loss / holding["total_cost"] * 100) if holding["total_cost"] > 0 else 0
                    
                    portfolio_value[ticker] = {
                        "quantity": holding["quantity"],
                        "buy_price": holding["buy_price"],
                        "current_price": current_price,
                        "current_value": current_value,
                        "total_cost": holding["total_cost"],
                        "gain_loss": gain_loss,
                        "gain_loss_percent": gain_loss_percent
                    }
                    
                    total_value += current_value
                    total_cost += holding["total_cost"]
            except Exception as e:
                print(f"警告: {ticker} の現在値取得に失敗しました。{e}")
        
        overall_gain_loss = total_value - total_cost
        overall_gain_loss_percent = (overall_gain_loss / total_cost * 100) if total_cost > 0 else 0
        
        return {
            "holdings": portfolio_value,
            "total_cost": total_cost,
            "total_value": total_value,
            "overall_gain_loss": overall_gain_loss,
            "overall_gain_loss_percent": overall_gain_loss_percent
        }
    
    def get_portfolio_allocation(self):
        """
        ポートフォリオの資産配分を計算
        
        Returns:
            dict: 各銘柄の配分比率
        """
        portfolio_value = self.get_portfolio_value()
        total_value = portfolio_value["total_value"]
        
        if total_value == 0:
            return {}
        
        allocation = {}
        for ticker, holding in portfolio_value["holdings"].items():
            allocation[ticker] = {
                "value": holding["current_value"],
                "percentage": (holding["current_value"] / total_value * 100)
            }
        
        return allocation
    
    def print_portfolio_summary(self):
        """
        ポートフォリオのサマリーを表示
        """
        portfolio_value = self.get_portfolio_value()
        allocation = self.get_portfolio_allocation()
        
        print("=" * 80)
        print("📊 ポートフォリオサマリー")
        print("=" * 80)
        print()
        
        if not portfolio_value["holdings"]:
            print("⚠️  保有銘柄がありません")
            return
        
        print("【保有銘柄】")
        print(f"{'銘柄':<10} {'保有数':<10} {'買値':<12} {'現在値':<12} {'評価額':<15} {'損益':<15} {'損益率':<10}")
        print("-" * 100)
        
        for ticker, holding in portfolio_value["holdings"].items():
            print(f"{ticker:<10} {holding['quantity']:<10.2f} ${holding['buy_price']:<11.2f} ${holding['current_price']:<11.2f} ${holding['current_value']:<14.2f} ${holding['gain_loss']:<14.2f} {holding['gain_loss_percent']:<9.2f}%")
        
        print()
        print("【資産配分】")
        print(f"{'銘柄':<10} {'評価額':<20} {'配分比率':<10}")
        print("-" * 50)
        
        for ticker, alloc in allocation.items():
            print(f"{ticker:<10} ${alloc['value']:<19.2f} {alloc['percentage']:<9.2f}%")
        
        print()
        print("【ポートフォリオ全体】")
        print(f"総投資額: ${portfolio_value['total_cost']:.2f}")
        print(f"現在値:   ${portfolio_value['total_value']:.2f}")
        print(f"損益:     ${portfolio_value['overall_gain_loss']:.2f}")
        print(f"損益率:   {portfolio_value['overall_gain_loss_percent']:.2f}%")
        print("=" * 80)

if __name__ == "__main__":
    print("=== ポートフォリオ管理テスト ===\n")
    
    # ポートフォリオマネージャーの初期化
    pm = PortfolioManager()
    
    # テストデータを追加
    print("サンプルデータを追加します...\n")
    pm.add_holding("AAPL", 10, 300.00)
    pm.add_holding("MSFT", 5, 400.00)
    pm.add_holding("9984", 100, 25.00)
    
    # ポートフォリオサマリーを表示
    pm.print_portfolio_summary()