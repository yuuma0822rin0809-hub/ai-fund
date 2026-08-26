---
name: stock-research-skill
description: 株価データ取得・テクニカル分析・投資判断を自動化するスキル。日本株・米国株の銘柄分析、ポートフォリオ管理、買い増し判断を提案。
compatibility: Python 3.9+, yfinance, pandas, Google Gemini API
---

# Stock Research Skill

## 目的
株価調査・テクニカル分析・投資判断を LINE Bot で自動化する。

## 対応銘柄
- 日本株（例：9984, 9433）
- 米国株（例：AAPL, MSFT）

## 主要機能
- 単発銘柄分析（直近3ヶ月のテクニカル指標）
- ポートフォリオ管理（保有銘柄一括管理）
- 買い増し提案（AI 分析）

## 実装予定（10日）
- Day 1-2：設計・環境構築
- Day 3-5：株価データ取得・テクニカル指標
- Day 6-8：ポートフォリオ機能
- Day 9-10：LINE Bot 統合