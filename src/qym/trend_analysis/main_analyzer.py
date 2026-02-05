"""
趋势买点分析主函数
根据趋势买点分析.md需求实现完整的分析流程（更新版）
"""
import os
import sys
from typing import Dict, Optional

# 添加项目根目录到路径中
dirname = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(dirname, '../../../'))

from src.qym.trend_analysis.kline_fetcher import KLineFetcher
from src.qym.trend_analysis.trend_analyzer import TrendAnalyzer


def analyze_stock_trend_support(stock_code: str) -> Optional[Dict]:
    """分析股票趋势支撑点"""
    print(f"正在获取股票 {stock_code} 的历史K线数据...")
    
    fetcher = KLineFetcher()
    kline_data = fetcher.fetch_kline_data(stock_code, days=180)
    
    if not kline_data:
        print(f"未能获取股票 {stock_code} 的K线数据")
        return None

    print(f"成功获取 {len(kline_data)} 条K线数据")

    analyzer = TrendAnalyzer()
    result = analyzer.analyze_trend_support_point(stock_code, kline_data)

    if result:
        print("\n=== 趋势支撑点分析结果 ===")
        print(f"股票代码: {result['stock_code']}")
        print(f"接近均线总次数: {result['near_ma_count']}")
        print(f"满足放量大涨次数: {result['strong_signal_count']}")
        print(f"接近均线日期: {result['near_ma_dates']}")
        print(f"放量大涨日期: {result['strong_signal_dates']}")
        print(f"放量大涨及第二天涨幅详情: {result.get('strong_signals_with_next_day_change', [])}")

    return result


if __name__ == "__main__":
    # 示例：分析特定股票
    result = analyze_stock_trend_support("300118.SZ")  # 江苏银行
    if not result:
        print("未找到符合条件的趋势支撑点")
