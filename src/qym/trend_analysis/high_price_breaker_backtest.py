#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
历史新高突破策略回测程序

功能：
1. 回测历史新高突破策略的成功率
2. 计算持有期收益
3. 统计策略表现指标
4. 生成回测报告
"""

import os
import sys
from typing import Dict, List, Optional
import argparse
from datetime import datetime

# 添加src目录到Python路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from qym.trend_analysis.kline_fetcher import KLineFetcher
import pandas as pd


class HighPriceBreakerBacktest:
    """历史新高突破策略回测器"""
    
    def __init__(self):
        """初始化回测器"""
        self.fetcher = KLineFetcher()
    
    def fetch_kline_data(self, stock_code: str, days: int = 1000) -> List[Dict]:
        """
        获取股票K线数据
        
        Args:
            stock_code: 股票代码
            days: 获取天数（默认1000天，确保有足够的回测数据）
            
        Returns:
            K线数据列表
        """
        try:
            kline_data = self.fetcher.fetch_kline_data(stock_code, days=days)
            if kline_data:
                return kline_data
            else:
                return []
        except Exception as e:
            print(f"获取 {stock_code} K线数据失败: {str(e)}")
            return []
    
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
    
    def identify_breakout_points(self, df: pd.DataFrame, lookback_days: int = 250, max_exceed_ratio: float = 10) -> List[Dict]:
        """
        识别历史新高突破点
        
        Args:
            df: K线数据DataFrame
            lookback_days: 回看天数（默认250天，约1年）
            max_exceed_ratio: 最大超出比率（默认10%）
            
        Returns:
            突破点列表
        """
        breakout_points = []
        
        if len(df) < lookback_days + 20:  # 确保有足够的数据
            return breakout_points
        
        # 遍历每一个交易日
        for i in range(lookback_days, len(df) - 20):  # 留出20天的持有期
            # 获取当前日期和价格
            current_date = df.loc[i, 'date']
            current_price = df.loc[i, 'close']
            
            # 获取过去lookback_days天的数据
            lookback_data = df.iloc[i - lookback_days:i]
            
            # 计算历史最高价
            historical_high = lookback_data['high'].max()
            
            # 计算超出比率
            if historical_high > 0:
                exceed_ratio = (current_price - historical_high) / historical_high * 100
            else:
                exceed_ratio = 0
            
            # 判断是否为突破点
            if current_price > historical_high and exceed_ratio <= max_exceed_ratio:
                breakout_points.append({
                    'date': current_date,
                    'price': current_price,
                    'historical_high': historical_high,
                    'exceed_ratio': exceed_ratio,
                    'index': i
                })
        
        return breakout_points
    
    def backtest_strategy(self, df: pd.DataFrame, breakout_points: List[Dict], hold_days: int = 20) -> List[Dict]:
        """
        回测突破策略
        
        Args:
            df: K线数据DataFrame
            breakout_points: 突破点列表
            hold_days: 持有天数（默认20天）
            
        Returns:
            回测结果列表
        """
        backtest_results = []
        
        for breakout in breakout_points:
            breakout_index = breakout['index']
            breakout_date = breakout['date']
            buy_price = breakout['price']
            
            # 计算卖出日期索引
            sell_index = min(breakout_index + hold_days, len(df) - 1)
            
            # 获取卖出价格和日期
            sell_price = df.loc[sell_index, 'close']
            sell_date = df.loc[sell_index, 'date']
            
            # 计算持有期收益
            if buy_price > 0:
                holding_return = (sell_price - buy_price) / buy_price * 100
            else:
                holding_return = 0
            
            # 计算持有天数
            actual_hold_days = sell_index - breakout_index
            
            # 计算最大回撤
            hold_period_data = df.iloc[breakout_index:sell_index+1]
            if len(hold_period_data) > 0:
                max_drawdown = ((hold_period_data['close'].cummax() - hold_period_data['close']) / hold_period_data['close'].cummax()).max() * 100
            else:
                max_drawdown = 0
            
            # 判断是否盈利
            is_profitable = holding_return > 0
            
            backtest_results.append({
                'breakout_date': breakout_date,
                'buy_price': buy_price,
                'sell_date': sell_date,
                'sell_price': sell_price,
                'holding_return': holding_return,
                'actual_hold_days': actual_hold_days,
                'max_drawdown': max_drawdown,
                'is_profitable': is_profitable,
                'historical_high': breakout['historical_high'],
                'exceed_ratio': breakout['exceed_ratio']
            })
        
        return backtest_results
    
    def calculate_metrics(self, backtest_results: List[Dict]) -> Dict:
        """
        计算回测指标
        
        Args:
            backtest_results: 回测结果列表
            
        Returns:
            回测指标字典
        """
        if not backtest_results:
            return {
                'total_trades': 0,
                'profitable_trades': 0,
                'success_rate': 0,
                'average_return': 0,
                'average_profitable_return': 0,
                'average_loss': 0,
                'total_return': 0,
                'max_return': 0,
                'min_return': 0,
                'average_hold_days': 0,
                'average_max_drawdown': 0
            }
        
        total_trades = len(backtest_results)
        profitable_trades = sum(1 for result in backtest_results if result['is_profitable'])
        success_rate = (profitable_trades / total_trades) * 100 if total_trades > 0 else 0
        
        returns = [result['holding_return'] for result in backtest_results]
        average_return = sum(returns) / len(returns) if returns else 0
        
        profitable_returns = [result['holding_return'] for result in backtest_results if result['is_profitable']]
        average_profitable_return = sum(profitable_returns) / len(profitable_returns) if profitable_returns else 0
        
        losing_returns = [result['holding_return'] for result in backtest_results if not result['is_profitable']]
        average_loss = sum(losing_returns) / len(losing_returns) if losing_returns else 0
        
        total_return = sum(returns) if returns else 0
        max_return = max(returns) if returns else 0
        min_return = min(returns) if returns else 0
        
        hold_days = [result['actual_hold_days'] for result in backtest_results]
        average_hold_days = sum(hold_days) / len(hold_days) if hold_days else 0
        
        max_drawdowns = [result['max_drawdown'] for result in backtest_results]
        average_max_drawdown = sum(max_drawdowns) / len(max_drawdowns) if max_drawdowns else 0
        
        return {
            'total_trades': total_trades,
            'profitable_trades': profitable_trades,
            'success_rate': success_rate,
            'average_return': average_return,
            'average_profitable_return': average_profitable_return,
            'average_loss': average_loss,
            'total_return': total_return,
            'max_return': max_return,
            'min_return': min_return,
            'average_hold_days': average_hold_days,
            'average_max_drawdown': average_max_drawdown
        }
    
    def generate_backtest_report(self, stock_code: str, stock_name: str, metrics: Dict, backtest_results: List[Dict]) -> str:
        """
        生成回测报告
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            metrics: 回测指标
            backtest_results: 回测结果
            
        Returns:
            回测报告内容
        """
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        report = f"# 历史新高突破策略回测报告\n\n"
        report += f"## 基本信息\n"
        report += f"- 股票代码: {stock_code}\n"
        report += f"- 股票名称: {stock_name}\n"
        report += f"- 回测日期: {current_date}\n"
        report += f"- 策略: 历史新高突破（超出比率≤10%）\n"
        report += f"- 持有期: 20天\n\n"
        
        report += "## 回测指标\n"
        report += "| 指标 | 值 |\n"
        report += "|------|-----|\n"
        report += f"| 总交易次数 | {metrics['total_trades']} |\n"
        report += f"| 盈利交易次数 | {metrics['profitable_trades']} |\n"
        report += f"| 成功率 | {metrics['success_rate']:.2f}% |\n"
        report += f"| 平均收益率 | {metrics['average_return']:.2f}% |\n"
        report += f"| 平均盈利 | {metrics['average_profitable_return']:.2f}% |\n"
        report += f"| 平均亏损 | {metrics['average_loss']:.2f}% |\n"
        report += f"| 总收益率 | {metrics['total_return']:.2f}% |\n"
        report += f"| 最大收益率 | {metrics['max_return']:.2f}% |\n"
        report += f"| 最小收益率 | {metrics['min_return']:.2f}% |\n"
        report += f"| 平均持有天数 | {metrics['average_hold_days']:.1f} |\n"
        report += f"| 平均最大回撤 | {metrics['average_max_drawdown']:.2f}% |\n\n"
        
        if backtest_results:
            report += "## 交易明细\n"
            report += "| 突破日期 | 买入价格 | 卖出日期 | 卖出价格 | 持有收益 | 持有天数 | 最大回撤 | 历史最高价 | 超出比率 |\n"
            report += "|---------|---------|---------|---------|---------|---------|---------|-----------|---------|\n"
            
            for result in backtest_results:
                report += f"| {result['breakout_date']} | {result['buy_price']:.2f} | {result['sell_date']} | {result['sell_price']:.2f} | {result['holding_return']:.2f}% | {result['actual_hold_days']} | {result['max_drawdown']:.2f}% | {result['historical_high']:.2f} | {result['exceed_ratio']:.2f}% |\n"
        else:
            report += "## 交易明细\n"
            report += "未发现符合条件的突破点\n"
        
        report += "\n## 策略评价\n"
        if metrics['success_rate'] > 60:
            report += "✅ 策略表现良好，成功率较高\n"
        elif metrics['success_rate'] > 50:
            report += "⚠️ 策略表现一般，有一定的盈利空间\n"
        else:
            report += "❌ 策略表现不佳，需要进一步优化\n"
        
        report += "\n## 风险提示\n"
        report += "1. 历史表现不代表未来收益\n"
        report += "2. 回测结果基于历史数据，实际交易可能存在滑点\n"
        report += "3. 市场环境变化可能影响策略有效性\n"
        report += "4. 建议结合其他技术指标和基本面分析\n"
        
        return report
    
    def run_backtest(self, stock_code: str, stock_name: str, days: int = 1000, lookback_days: int = 250, hold_days: int = 20):
        """
        运行完整回测
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            days: 获取数据天数
            lookback_days: 回看天数
            hold_days: 持有天数
        """
        print(f"==========================================")
        print(f"📊 历史新高突破策略回测")
        print(f"==========================================")
        print(f"股票代码: {stock_code}")
        print(f"股票名称: {stock_name}")
        print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"==========================================")
        
        # 获取K线数据
        kline_data = self.fetch_kline_data(stock_code, days=days)
        if not kline_data:
            print("❌ 获取K线数据失败")
            return
        
        # 转换为DataFrame
        df = self.convert_to_dataframe(kline_data)
        if df.empty:
            print("❌ 数据转换失败")
            return
        
        print(f"✅ 成功获取 {len(df)} 天的K线数据")
        
        # 识别突破点
        breakout_points = self.identify_breakout_points(df, lookback_days=lookback_days)
        print(f"✅ 识别到 {len(breakout_points)} 个突破点")
        
        # 回测策略
        backtest_results = self.backtest_strategy(df, breakout_points, hold_days=hold_days)
        
        # 计算指标
        metrics = self.calculate_metrics(backtest_results)
        
        # 生成报告
        report = self.generate_backtest_report(stock_code, stock_name, metrics, backtest_results)
        
        # 打印报告
        print("\n" + "="*80)
        print("回测报告摘要")
        print("="*80)
        print(f"总交易次数: {metrics['total_trades']}")
        print(f"盈利交易次数: {metrics['profitable_trades']}")
        print(f"成功率: {metrics['success_rate']:.2f}%")
        print(f"平均收益率: {metrics['average_return']:.2f}%")
        print(f"总收益率: {metrics['total_return']:.2f}%")
        print("="*80)
        
        # 保存报告
        self.save_report(report, stock_code)
        
        print(f"\n✅ 回测完成！报告已保存")
    
    def save_report(self, report: str, stock_code: str):
        """
        保存回测报告
        
        Args:
            report: 回测报告内容
            stock_code: 股票代码
        """
        # 确保data/trend_analysis目录存在
        os.makedirs('data/trend_analysis', exist_ok=True)
        
        filename = f"backtest_high_price_breaker_{stock_code}_{datetime.now().strftime('%Y%m%d')}.md"
        filepath = os.path.join('data/trend_analysis', filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"\n📄 报告已保存到: {filepath}")
        except Exception as e:
            print(f"❌ 保存报告失败: {str(e)}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='历史新高突破策略回测程序')
    parser.add_argument('--code', type=str, required=True, help='股票代码')
    parser.add_argument('--name', type=str, default='未知', help='股票名称')
    parser.add_argument('--days', type=int, default=1000, help='获取数据天数，默认1000天')
    parser.add_argument('--lookback', type=int, default=250, help='回看天数，默认250天')
    parser.add_argument('--hold', type=int, default=20, help='持有天数，默认20天')
    
    args = parser.parse_args()
    
    backtester = HighPriceBreakerBacktest()
    backtester.run_backtest(
        stock_code=args.code,
        stock_name=args.name,
        days=args.days,
        lookback_days=args.lookback,
        hold_days=args.hold
    )


if __name__ == "__main__":
    main()
