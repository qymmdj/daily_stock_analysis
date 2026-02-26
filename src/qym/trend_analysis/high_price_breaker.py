#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
历史突破近期高点 + 回踩分析程序

功能：
1. 读取 sources/stock_limitup.csv 文件中的股票列表
2. 获取每只股票历史K线数据
3. 识别「突破近期高点」：某日收盘价突破过去N日的最高价
4. 识别「回踩」：突破后价格回落，当前价在突破位附近（支撑位测试）
5. 输出符合条件的股票信息
"""

import csv
import os
import sys
from typing import Dict, List, Optional, Tuple
import argparse
from datetime import datetime

# 添加src目录到Python路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from qym.trend_analysis.kline_fetcher import KLineFetcher
import pandas as pd


class HighPriceBreaker:
    """历史新高突破分析器"""
    
    def __init__(self):
        """初始化分析器"""
        self.fetcher = KLineFetcher()
        self.stock_list = []
        self.limitup_data = {}
    
    def load_stock_and_limitup_data(self, csv_file: str) -> List[Dict]:
        """
        从涨停数据文件加载股票列表和涨停数据
        
        Args:
            csv_file: 涨停CSV文件路径
            
        Returns:
            股票信息列表
        """
        stock_list = []
        limitup_data = {}
        
        try:
            with open(csv_file, 'r', encoding='utf-8', newline='') as f:
                # 支持制表符或逗号分隔
                sample = f.read(4096)
                f.seek(0)
                lines = sample.split('\n')
                delimiter = '\t' if (len(lines) > 1 and '\t' in lines[1]) else ','
                reader = csv.reader(f, delimiter=delimiter)
                rows = list(reader)
                
                if not rows:
                    print("CSV文件为空")
                    return []
                
                # 跳过表头
                for row in rows[1:]:
                    if len(row) >= 4:
                        try:
                            limitup_count = int(row[0])
                        except (ValueError, IndexError):
                            continue
                        stock_info = {
                            'code': row[1],
                            'name': row[2],
                            'sector': row[3],
                            'limitup_count': limitup_count
                        }
                        stock_list.append(stock_info)
                        limitup_data[row[1]] = {'count': limitup_count, 'sector': row[3]}
            
            print(f"成功加载 {len(stock_list)} 只股票")
            print(f"成功加载 {len(limitup_data)} 只股票的涨停数据")
            
            self.stock_list = stock_list
            self.limitup_data = limitup_data
            
            return stock_list
            
        except Exception as e:
            print(f"加载数据失败: {str(e)}")
            return []
    
    def fetch_kline_data(self, stock_code: str, days: int = 400) -> List[Dict]:
        """
        获取股票K线数据
        
        Args:
            stock_code: 股票代码
            days: 获取天数（默认400天，确保至少1年数据）
            
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
    
    def _find_breakout_and_pullback(
        self,
        df: pd.DataFrame,
        lookback_days: int = 60,
        scan_days: int = 120,
        pullback_tolerance: float = 8.0,
        min_pullback_from_peak: float = 3.0
    ) -> Optional[Tuple[int, float, float, str]]:
        """
        在K线数据中寻找「突破近期高点 + 回踩」形态
        
        Args:
            df: K线DataFrame
            lookback_days: 近期高点回看天数
            scan_days: 向前扫描寻找突破的天数
            pullback_tolerance: 回踩容差，当前价与突破位的偏离百分比（±%）
            min_pullback_from_peak: 从突破后峰值的最小回撤幅度（%）
            
        Returns:
            (突破日索引, 突破位, 突破后峰值, 突破日期) 或 None
        """
        n = len(df)
        if n < lookback_days + scan_days + 5:
            return None
        
        current_price = float(df.iloc[-1]['close'])
        # 从最近往前扫描，寻找突破点
        for i in range(n - 2, n - scan_days - 1, -1):
            if i < lookback_days:
                break
            lookback = df.iloc[i - lookback_days:i]
            recent_high = float(lookback['high'].max())
            close_i = float(df.iloc[i]['close'])
            
            # 突破条件：收盘价突破近期高点
            if recent_high <= 0 or close_i <= recent_high:
                continue
            
            breakout_level = recent_high
            breakout_date = df.iloc[i]['date']
            breakout_idx = i
            
            # 突破后的数据
            after_breakout = df.iloc[breakout_idx + 1:]
            if after_breakout.empty:
                continue
            
            peak_after = float(after_breakout['high'].max())
            # 突破后需有更高点（确认突破有效）
            if peak_after <= breakout_level:
                continue
            
            # 回踩条件1：当前价已从峰值回落
            pullback_ratio = (peak_after - current_price) / peak_after * 100 if peak_after > 0 else 0
            if pullback_ratio < min_pullback_from_peak:
                continue
            
            # 回踩条件2：当前价在突破位附近（±pullback_tolerance%）
            distance_to_breakout = (current_price - breakout_level) / breakout_level * 100 if breakout_level > 0 else 0
            if abs(distance_to_breakout) > pullback_tolerance:
                continue
            
            return (breakout_idx, breakout_level, peak_after, breakout_date)
        
        return None
    
    def analyze_high_price_break(
        self,
        stock_info: Dict,
        days: int = 400,
        lookback_days: int = 60,
        pullback_tolerance: float = 8.0,
        min_pullback_from_peak: float = 3.0
    ) -> Optional[Dict]:
        """
        分析单个股票的「突破近期高点 + 回踩」形态
        
        Args:
            stock_info: 股票信息
            days: 获取K线天数
            lookback_days: 近期高点回看天数（默认60日）
            pullback_tolerance: 回踩容差（%）
            min_pullback_from_peak: 从峰值最小回撤（%）
            
        Returns:
            分析结果
        """
        stock_code = stock_info['code']
        stock_name = stock_info['name']
        stock_sector = stock_info['sector']
        limitup_count = stock_info['limitup_count']
        
        print(f"正在分析: {stock_code} - {stock_name}")
        
        kline_data = self.fetch_kline_data(stock_code, days=days)
        if not kline_data:
            return None
        
        df = self.convert_to_dataframe(kline_data)
        if df.empty:
            return None
        
        min_len = lookback_days + 80
        if len(df) < min_len:
            print(f"[WARN] {stock_code} 数据不足（需至少{min_len}日），跳过分析")
            return None
        
        found = self._find_breakout_and_pullback(
            df,
            lookback_days=lookback_days,
            pullback_tolerance=pullback_tolerance,
            min_pullback_from_peak=min_pullback_from_peak
        )
        
        if not found:
            return None
        
        breakout_idx, breakout_level, peak_after, breakout_date = found
        current_price = float(df.iloc[-1]['close'])
        pullback_ratio = (peak_after - current_price) / peak_after * 100 if peak_after > 0 else 0
        distance_to_breakout = (current_price - breakout_level) / breakout_level * 100 if breakout_level > 0 else 0
        
        return {
            'code': stock_code,
            'name': stock_name,
            'sector': stock_sector,
            'limitup_count': limitup_count,
            'breakout_level': breakout_level,
            'breakout_date': breakout_date,
            'peak_after_breakout': peak_after,
            'current_price': current_price,
            'pullback_ratio': pullback_ratio,
            'distance_to_breakout': distance_to_breakout
        }
    
    def batch_analyze(
        self,
        days: int = 400,
        max_stocks: int = None,
        lookback_days: int = 60,
        pullback_tolerance: float = 8.0,
        min_pullback_from_peak: float = 3.0
    ) -> List[Dict]:
        """
        批量分析股票
        
        Args:
            days: 获取K线天数
            max_stocks: 最大分析股票数
            lookback_days: 近期高点回看天数
            pullback_tolerance: 回踩容差（%）
            min_pullback_from_peak: 从峰值最小回撤（%）
            
        Returns:
            符合条件的股票列表
        """
        results = []
        processed_count = 0
        
        if not self.stock_list:
            print("未加载股票列表")
            return results
        
        total_stocks = len(self.stock_list)
        if max_stocks:
            total_stocks = min(max_stocks, total_stocks)
        
        print(f"开始批量分析 {total_stocks} 只股票（近期{lookback_days}日高点，回踩容差±{pullback_tolerance}%）...")
        
        for stock_info in self.stock_list[:total_stocks]:
            processed_count += 1
            print(f"\n[{processed_count}/{total_stocks}]")
            
            result = self.analyze_high_price_break(
                stock_info,
                days=days,
                lookback_days=lookback_days,
                pullback_tolerance=pullback_tolerance,
                min_pullback_from_peak=min_pullback_from_peak
            )
            if result:
                results.append(result)
                print(f"[OK] 发现突破回踩: {stock_info['code']} - {stock_info['name']} (突破日{result['breakout_date']})")
            else:
                print(f"[--] 不符合条件: {stock_info['code']} - {stock_info['name']}")
        
        print(f"\n分析完成！共发现 {len(results)} 只符合条件的股票")
        return results
    
    def generate_output(self, results: List[Dict]):
        """
        生成分析结果输出
        
        Args:
            results: 分析结果列表
        """
        if not results:
            print("未发现符合条件的股票")
            return
        
        # 按距离突破位排序（越接近突破位越靠前）
        results.sort(key=lambda x: abs(x['distance_to_breakout']))
        
        print("\n" + "="*140)
        print("突破近期高点 + 回踩 分析结果")
        print("="*140)
        print(f"分析日期: {datetime.now().strftime('%Y-%m-%d')}")
        print(f"符合条件的股票数量: {len(results)}")
        print("="*140)
        print("股票代码 | 股票名称 | 关联板块 | 涨停次数 | 突破日 | 突破位 | 突破后峰值 | 当前价 | 回撤% | 距突破位%")
        print("-"*140)
        
        for result in results:
            print(f"{result['code']} | {result['name']} | {result['sector']} | {result['limitup_count']} | "
                  f"{result['breakout_date']} | {result['breakout_level']:.2f} | {result['peak_after_breakout']:.2f} | "
                  f"{result['current_price']:.2f} | {result['pullback_ratio']:.1f}% | {result['distance_to_breakout']:.1f}%")
        
        print("="*140)
        
        self.save_results(results)
    
    def generate_markdown_report(self, results: List[Dict]) -> str:
        """
        生成Markdown格式的分析报告
        
        Args:
            results: 分析结果列表
            
        Returns:
            Markdown格式的报告内容
        """
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        report = f"# 突破近期高点+回踩 分析报告 - {current_date}\n\n"
        report += f"## 分析概况\n"
        report += f"- 分析日期: {current_date}\n"
        report += f"- 符合条件的股票数量: {len(results)}\n\n"
        
        if not results:
            report += "未发现符合条件的股票\n"
            return report
        
        results.sort(key=lambda x: abs(x['distance_to_breakout']))
        
        report += "## 股票列表\n"
        report += "| 股票代码 | 股票名称 | 关联板块 | 涨停次数 | 突破日 | 突破位 | 突破后峰值 | 当前价 | 回撤% | 距突破位% |\n"
        report += "|---------|---------|---------|---------|--------|--------|-----------|--------|-------|----------|\n"
        
        for result in results:
            report += f"| {result['code']} | {result['name']} | {result['sector']} | {result['limitup_count']} | "
            report += f"{result['breakout_date']} | {result['breakout_level']:.2f} | {result['peak_after_breakout']:.2f} | "
            report += f"{result['current_price']:.2f} | {result['pullback_ratio']:.1f}% | {result['distance_to_breakout']:.1f}% |\n"
        
        report += "\n## 投资建议\n"
        report += "1. 突破近期高点后回踩，通常为支撑位测试，可关注企稳后的二次上攻机会\n"
        report += "2. 距突破位越近，支撑有效性越强；负值表示略跌破，需观察是否快速收回\n"
        report += "3. 建议结合成交量（缩量回踩更健康）、均线等综合判断\n"
        report += "4. 止损位可设在突破位下方3-5%\n"
        report += "5. 关注大盘环境，避免在系统性风险时入场\n"
        
        return report
    
    def save_results(self, results: List[Dict]):
        """
        保存分析结果到文件
        
        Args:
            results: 分析结果列表
        """
        # 确保data/trend_analysis目录存在
        os.makedirs('data/trend_analysis', exist_ok=True)
        
        filename = f"high_price_break_results_{datetime.now().strftime('%Y%m%d')}.txt"
        filepath = os.path.join('data/trend_analysis', filename)
        
        try:
            results.sort(key=lambda x: abs(x['distance_to_breakout']))
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("突破近期高点+回踩 分析结果\n")
                f.write(f"分析日期: {datetime.now().strftime('%Y-%m-%d')}\n")
                f.write(f"符合条件的股票数量: {len(results)}\n")
                f.write("-"*140 + "\n")
                f.write("股票代码 | 股票名称 | 关联板块 | 涨停次数 | 突破日 | 突破位 | 突破后峰值 | 当前价 | 回撤% | 距突破位%\n")
                f.write("-"*140 + "\n")
                
                for result in results:
                    f.write(f"{result['code']} | {result['name']} | {result['sector']} | {result['limitup_count']} | "
                            f"{result['breakout_date']} | {result['breakout_level']:.2f} | {result['peak_after_breakout']:.2f} | "
                            f"{result['current_price']:.2f} | {result['pullback_ratio']:.1f}% | {result['distance_to_breakout']:.1f}%\n")
            
            print(f"\n结果已保存到: {filepath}")
        except Exception as e:
            print(f"保存结果失败: {str(e)}")
    
    def upload_results_to_gitee(self, results: List[Dict], skip_on_error: bool = True):
        """
        将分析结果上传到Gitee
        
        Args:
            results: 分析结果列表
            skip_on_error: 出错时是否静默跳过（默认True，避免影响主流程）
        """
        try:
            from gitee_client import GiteeClient
            client = GiteeClient()
            current_date = datetime.now().strftime('%Y%m%d')
            markdown_content = self.generate_markdown_report(results)
            remote_path = f"xg/突破回踩.{current_date}.md"
            message = f"更新突破近期高点+回踩分析报告 {current_date}"
            
            success = client.upload_content(markdown_content, remote_path, message=message)
            
            if success:
                print(f"[OK] 分析报告已成功上传至Gitee: {remote_path}")
            else:
                print(f"[FAIL] 分析报告上传失败: {remote_path}")
        except ImportError as e:
            if not skip_on_error:
                raise
            print(f"[WARN] 跳过Gitee上传（GiteeClient未配置）: {e}")
        except Exception as e:
            if not skip_on_error:
                raise
            print(f"[WARN] 上传到Gitee失败（已跳过）: {str(e)}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='突破近期高点+回踩分析程序')
    parser.add_argument('--limitup', type=str, default='sources/stock_limitup.csv', help='涨停CSV文件路径')
    parser.add_argument('--days', type=int, default=400, help='获取K线天数，默认400天')
    parser.add_argument('--max-stocks', type=int, default=None, help='最大分析股票数')
    parser.add_argument('--lookback', type=int, default=60, help='近期高点回看天数，默认60日')
    parser.add_argument('--tolerance', type=float, default=8.0, help='回踩容差（%%），默认8')
    parser.add_argument('--min-pullback', type=float, default=3.0, help='从峰值最小回撤（%%），默认3')
    
    args = parser.parse_args()
    
    analyzer = HighPriceBreaker()
    analyzer.load_stock_and_limitup_data(args.limitup)
    
    results = analyzer.batch_analyze(
        days=args.days,
        max_stocks=args.max_stocks,
        lookback_days=args.lookback,
        pullback_tolerance=args.tolerance,
        min_pullback_from_peak=args.min_pullback
    )
    
    analyzer.generate_output(results)
    if results:
        analyzer.upload_results_to_gitee(results)


if __name__ == "__main__":
    main()
