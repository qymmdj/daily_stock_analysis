#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
黄金坑形态回测程序

功能：
1. 接收股票代码
2. 获取历史K线数据
3. 分析黄金坑形态买点
4. 回测成功率
5. 生成详细报告
"""

import os
import sys
from typing import Dict, List, Optional, Tuple
import argparse
from datetime import datetime, timedelta

# 添加src目录到Python路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from qym.trend_analysis.kline_fetcher import KLineFetcher
from qym.trend_analysis.golden_analyzer import PatternAnalyzer, PatternResult, PatternType, PatternStage
import pandas as pd
import numpy as np


class GoldenPitBacktester:
    """黄金坑形态回测器"""
    
    def __init__(self):
        """初始化回测器"""
        self.fetcher = KLineFetcher()
        self.analyzer = PatternAnalyzer()
    
    def fetch_kline_data(self, stock_code: str, days: int = 365) -> List[Dict]:
        """
        获取股票K线数据
        
        Args:
            stock_code: 股票代码
            days: 获取天数
            
        Returns:
            K线数据列表
        """
        print(f"正在获取 {stock_code} 的{days}天K线数据...")
        kline_data = self.fetcher.fetch_kline_data(stock_code, days=days)
        
        if not kline_data:
            print(f"获取 {stock_code} 的K线数据失败")
            return []
        
        print(f"成功获取 {len(kline_data)} 条K线数据")
        return kline_data
    
    def convert_to_dataframe(self, kline_data: List[Dict]) -> pd.DataFrame:
        """
        将K线数据转换为DataFrame
        
        Args:
            kline_data: K线数据列表
            
        Returns:
            DataFrame格式的K线数据
        """
        if not kline_data:
            return pd.DataFrame()
        
        data = []
        for item in kline_data:
            data.append({
                'date': item.get('date'),
                'open': item.get('open_px'),
                'high': item.get('high_px'),
                'low': item.get('low_px'),
                'close': item.get('close_px'),
                'volume': item.get('turnover_volume')
            })
        
        df = pd.DataFrame(data)
        
        # 确保数据类型正确
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 按日期排序
        df = df.sort_values('date').reset_index(drop=True)
        
        return df
    
    def detect_golden_pit_periods(self, df: pd.DataFrame, stock_code: str) -> List[PatternResult]:
        """
        检测历史上的黄金坑形态
        
        Args:
            df: K线数据DataFrame
            stock_code: 股票代码
            
        Returns:
            黄金坑形态结果列表
        """
        patterns = []
        n = len(df)
        
        # 滑动窗口检测黄金坑
        window_size = 120  # 每个窗口120天数据
        step = 30  # 步长30天
        
        print(f"开始检测 {stock_code} 的黄金坑形态...")
        
        for i in range(0, n - window_size + 1, step):
            window_df = df.iloc[i:i+window_size].copy()
            
            if len(window_df) < 60:
                continue
            
            # 检测黄金坑
            result = self.analyzer.detect_golden_pit(window_df, stock_code)
            if result:
                patterns.append(result)
            
            # 检测恐慌性洗盘
            panic_result = self.analyzer.detect_panic_wash(window_df, stock_code)
            if panic_result:
                patterns.append(panic_result)
        
        # 去重（基于开始日期）
        unique_patterns = []
        seen_dates = set()
        
        for pattern in patterns:
            if pattern.start_date not in seen_dates:
                seen_dates.add(pattern.start_date)
                unique_patterns.append(pattern)
        
        print(f"共检测到 {len(unique_patterns)} 个黄金坑形态")
        return unique_patterns
    
    def analyze_pattern_performance(self, df: pd.DataFrame, pattern: PatternResult, look_ahead_days: int = 20) -> Dict:
        """
        分析黄金坑形态的后续表现
        
        修正逻辑：从坑底日期开始计算持有期，而不是从形态开始日期
        
        Args:
            df: K线数据DataFrame
            pattern: 黄金坑形态结果
            look_ahead_days: 前瞻性分析天数
            
        Returns:
            形态表现分析结果
        """
        # 找到坑底日期在DataFrame中的位置（这是买点）
        bottom_idx = df[df['date'] == pattern.bottom_start_date].index
        if not len(bottom_idx):
            return {}
        
        bottom_idx = bottom_idx[0]
        
        # 从坑底日期开始，往后持有look_ahead_days天
        end_idx = min(bottom_idx + look_ahead_days, len(df) - 1)
        
        # 获取持有期数据（从坑底日期到持有期结束）
        hold_data = df.iloc[bottom_idx:end_idx+1].copy()
        
        if len(hold_data) < 1:
            return {}
        
        # 买点价格：坑底日期的收盘价
        buy_price = hold_data['close'].iloc[0]
        
        # 卖出价格：持有期结束时的收盘价
        sell_price = hold_data['close'].iloc[-1]
        sell_date = hold_data['date'].iloc[-1]
        
        # 计算持有期收益率
        hold_return = (sell_price - buy_price) / buy_price * 100
        
        # 计算持有期内的最高价格和收益率
        highest_price = hold_data['high'].max()
        highest_date = hold_data[hold_data['high'] == highest_price]['date'].iloc[0]
        max_return = (highest_price - buy_price) / buy_price * 100
        
        # 计算持有期内的最低价格和最大回撤
        lowest_price = hold_data['low'].min()
        lowest_date = hold_data[hold_data['low'] == lowest_price]['date'].iloc[0]
        max_drawdown = (lowest_price - buy_price) / buy_price * 100
        
        # 计算成功率（持有期收益为正视为成功）
        is_profitable = hold_return > 0
        
        # 计算持有天数
        hold_days = len(hold_data) - 1
        
        return {
            'pattern_start_date': pattern.start_date,
            'bottom_date': pattern.bottom_start_date,
            'buy_price': buy_price,
            'sell_price': sell_price,
            'sell_date': sell_date,
            'hold_days': hold_days,
            'highest_price': highest_price,
            'highest_date': highest_date,
            'lowest_price': lowest_price,
            'lowest_date': lowest_date,
            'max_return': max_return,
            'max_drawdown': max_drawdown,
            'hold_return': hold_return,
            'is_profitable': is_profitable,
            'pattern_type': pattern.pattern_type.value,
            'confidence': pattern.confidence
        }
    
    def run_backtest(self, stock_code: str, days: int = 730, look_ahead_days: int = 20) -> Dict:
        """
        运行回测
        
        Args:
            stock_code: 股票代码
            days: 回测天数
            look_ahead_days: 前瞻性分析天数
            
        Returns:
            回测结果
        """
        print(f"\n=== 开始回测 {stock_code} 的黄金坑指标 ===")
        
        # 1. 获取K线数据
        kline_data = self.fetch_kline_data(stock_code, days=days)
        if not kline_data:
            return {}
        
        # 2. 转换为DataFrame
        df = self.convert_to_dataframe(kline_data)
        if df.empty:
            return {}
        
        # 3. 检测黄金坑形态
        patterns = self.detect_golden_pit_periods(df, stock_code)
        if not patterns:
            print(f"未检测到 {stock_code} 的黄金坑形态")
            return {}
        
        # 4. 分析每个形态的表现
        performances = []
        for pattern in patterns:
            performance = self.analyze_pattern_performance(df, pattern, look_ahead_days)
            if performance:
                performances.append(performance)
        
        # 5. 计算整体统计
        if performances:
            profitable_count = sum(1 for p in performances if p['is_profitable'])
            total_count = len(performances)
            success_rate = (profitable_count / total_count) * 100
            avg_max_return = np.mean([p['max_return'] for p in performances])
            avg_hold_return = np.mean([p['hold_return'] for p in performances])
            avg_max_drawdown = np.mean([p['max_drawdown'] for p in performances])
            
            print(f"\n=== 回测统计结果 ===")
            print(f"总形态数: {total_count}")
            print(f"成功形态数: {profitable_count}")
            print(f"成功率: {success_rate:.2f}%")
            print(f"平均最大收益率: {avg_max_return:.2f}%")
            print(f"平均持有期收益率: {avg_hold_return:.2f}%")
            print(f"平均最大回撤: {avg_max_drawdown:.2f}%")
            
            # 按置信度排序
            performances.sort(key=lambda x: x['confidence'], reverse=True)
            
            return {
                'stock_code': stock_code,
                'total_patterns': total_count,
                'profitable_patterns': profitable_count,
                'success_rate': success_rate,
                'avg_max_return': avg_max_return,
                'avg_hold_return': avg_hold_return,
                'avg_max_drawdown': avg_max_drawdown,
                'performances': performances
            }
        else:
            print(f"无法分析 {stock_code} 的黄金坑形态表现")
            return {}
    
    def generate_report(self, backtest_result: Dict) -> str:
        """
        生成回测报告
        
        Args:
            backtest_result: 回测结果
            
        Returns:
            回测报告内容
        """
        if not backtest_result:
            return "回测失败，无结果可报告"
        
        stock_code = backtest_result['stock_code']
        report = f"# 黄金坑指标回测报告 - {stock_code}\n\n"
        report += f"## 回测概况\n"
        report += f"- 总形态数: {backtest_result['total_patterns']}\n"
        report += f"- 成功形态数: {backtest_result['profitable_patterns']}\n"
        report += f"- 成功率: {backtest_result['success_rate']:.2f}%\n"
        report += f"- 平均最大收益率: {backtest_result['avg_max_return']:.2f}%\n"
        report += f"- 平均持有期收益率: {backtest_result['avg_hold_return']:.2f}%\n"
        report += f"- 平均最大回撤: {backtest_result['avg_max_drawdown']:.2f}%\n\n"
        
        report += "## 形态表现详情\n"
        report += "| 形态类型 | 坑底日期 | 买点价格 | 卖出价格 | 卖出日期 | 持有天数 | 最高价格 | 最高日期 | 最大收益 | 最低价格 | 最低日期 | 最大回撤 | 持有收益 | 成功率 | 置信度 |\n"
        report += "|---------|---------|---------|---------|---------|---------|---------|---------|---------|---------|---------|---------|---------|---------|---------|\n"
        
        for perf in backtest_result['performances']:
            report += f"| {perf['pattern_type']} | {perf['bottom_date']} | {perf['buy_price']:.2f} | {perf['sell_price']:.2f} | {perf['sell_date']} | {perf['hold_days']} | {perf['highest_price']:.2f} | {perf['highest_date']} | {perf['max_return']:.2f}% | {perf['lowest_price']:.2f} | {perf['lowest_date']} | {perf['max_drawdown']:.2f}% | {perf['hold_return']:.2f}% | {'是' if perf['is_profitable'] else '否'} | {perf['confidence']:.1f} |\n"
        
        report += "\n## 结论\n"
        if backtest_result['success_rate'] > 60:
            report += f"✅ 黄金坑指标在 {stock_code} 上表现良好，成功率 {backtest_result['success_rate']:.2f}%，值得关注。\n"
        else:
            report += f"⚠️ 黄金坑指标在 {stock_code} 上表现一般，成功率 {backtest_result['success_rate']:.2f}%，建议结合其他指标使用。\n"
        
        return report


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='黄金坑形态回测程序')
    parser.add_argument('stock_code', type=str, help='股票代码，如 601969.SS')
    parser.add_argument('--days', type=int, default=730, help='回测天数，默认730天（2年）')
    parser.add_argument('--look_ahead', type=int, default=20, help='前瞻性分析天数，默认20天')
    
    args = parser.parse_args()
    
    backtester = GoldenPitBacktester()
    result = backtester.run_backtest(args.stock_code, days=args.days, look_ahead_days=args.look_ahead)
    
    if result:
        report = backtester.generate_report(result)
        print("\n" + "="*80)
        print("回测报告")
        print("="*80)
        print(report)
        
        # 保存报告到文件
        report_file = f"golden_pit_backtest_{args.stock_code}_{datetime.now().strftime('%Y%m%d')}.md"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n报告已保存到: {report_file}")
    else:
        print("回测失败")


if __name__ == "__main__":
    main()
