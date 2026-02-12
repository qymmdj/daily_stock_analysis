#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
黄金坑买点分析程序

功能：
1. 读取 sources/stock.csv 文件中的股票列表
2. 批量分析股票的黄金坑买点机会
3. 输出符合条件的股票列表
4. 生成详细的分析报告
"""

import os
import sys
import csv
from typing import Dict, List, Optional, Tuple
import argparse
from datetime import datetime, timedelta

# 添加src目录到Python路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from qym.trend_analysis.kline_fetcher import KLineFetcher
from qym.trend_analysis.golden_analyzer import PatternAnalyzer, PatternResult, PatternType, PatternStage
from gitee_client import GiteeClient
import pandas as pd
import numpy as np


class GoldenPitScanner:
    """黄金坑买点扫描器"""
    
    def __init__(self):
        """初始化扫描器"""
        self.fetcher = KLineFetcher()
        self.analyzer = PatternAnalyzer()
        self.stock_list = []
        self.limitup_data = {}
    
    def load_stock_list(self, csv_file: str) -> List[Dict]:
        """
        加载股票列表
        
        Args:
            csv_file: 股票CSV文件路径
            
        Returns:
            股票信息列表
        """
        stock_list = []
        
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 3:
                        stock_info = {
                            'code': row[0],
                            'name': row[1],
                            'province': row[2]
                        }
                        stock_list.append(stock_info)
            
            print(f"成功加载 {len(stock_list)} 只股票")
            self.stock_list = stock_list
            return stock_list
            
        except Exception as e:
            print(f"加载股票列表失败: {str(e)}")
            return []
    
    def load_limitup_data(self, csv_file: str = 'sources/stock_limitup.csv'):
        """
        加载涨停数据
        
        Args:
            csv_file: 涨停CSV文件路径
            
        Returns:
            涨停数据字典 {股票代码: (涨停次数, 关联板块)}
        """
        limitup_data = {}
        
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 4:
                        stock_code = row[1]
                        limitup_count = row[0]
                        sector = row[3]
                        try:
                            limitup_data[stock_code] = {
                                'count': int(limitup_count),
                                'sector': sector
                            }
                        except ValueError:
                            continue
            
            print(f"成功加载 {len(limitup_data)} 只股票的涨停数据")
            self.limitup_data = limitup_data
            return limitup_data
            
        except Exception as e:
            print(f"加载涨停数据失败: {str(e)}")
            return {}
    
    def fetch_kline_data(self, stock_code: str, days: int = 180) -> List[Dict]:
        """
        获取股票K线数据
        
        Args:
            stock_code: 股票代码
            days: 获取天数
            
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
    
    def scan_golden_pit(self, stock_info: Dict, days: int = 180) -> Optional[Dict]:
        """
        扫描单个股票的黄金坑买点
        
        Args:
            stock_info: 股票信息
            days: 分析天数
            
        Returns:
            黄金坑分析结果
        """
        stock_code = stock_info['code']
        stock_name = stock_info['name']
        
        print(f"正在分析: {stock_code} - {stock_name}")
        
        # 获取K线数据
        kline_data = self.fetch_kline_data(stock_code, days=days)
        if not kline_data:
            return None
        
        # 转换为DataFrame
        df = self.convert_to_dataframe(kline_data)
        if df.empty:
            return None
        
        # 获取涨停数据
        limitup_info = self.limitup_data.get(stock_code, {})
        limitup_count = limitup_info.get('count', 0)
        limitup_sector = limitup_info.get('sector', '-')
        
        # 检测黄金坑
        golden_result = self.analyzer.detect_golden_pit(df, stock_code)
        if golden_result and golden_result.buy_signal:
            # 计算买点价格和预期收益
            bottom_date = golden_result.bottom_start_date
            bottom_idx = df[df['date'] == bottom_date].index
            
            if len(bottom_idx):
                buy_price = df.loc[bottom_idx[0], 'close']
                
                # 计算5天后的价格（如果有）
                future_price = None
                future_date = None
                if bottom_idx[0] + 5 < len(df):
                    future_idx = bottom_idx[0] + 5
                    future_price = df.loc[future_idx, 'close']
                    future_date = df.loc[future_idx, 'date']
                
                potential_return = None
                if future_price:
                    potential_return = (future_price - buy_price) / buy_price * 100
                
                # 判断是否买入（置信度>70且潜在收益>5%）
                should_buy = golden_result.confidence > 70 and (potential_return is None or potential_return > 5)
                
                return {
                    'code': stock_code,
                    'name': stock_name,
                    'province': stock_info['province'],
                    'pattern_type': golden_result.pattern_type.value,
                    'confidence': golden_result.confidence,
                    'buy_signal': golden_result.buy_signal,
                    'buy_reason': golden_result.buy_reason,
                    'bottom_date': bottom_date,
                    'buy_price': buy_price,
                    'future_price': future_price,
                    'future_date': future_date,
                    'potential_return': potential_return,
                    'dip_amplitude': golden_result.dip_amplitude,
                    'rebound_amplitude': golden_result.rebound_amplitude,
                    'current_stage': golden_result.current_stage.value,
                    'limitup_count': limitup_count,
                    'limitup_sector': limitup_sector,
                    'should_buy': should_buy
                }
        
        # 检测恐慌性洗盘
        panic_result = self.analyzer.detect_panic_wash(df, stock_code)
        if panic_result and panic_result.buy_signal:
            bottom_date = panic_result.bottom_start_date
            bottom_idx = df[df['date'] == bottom_date].index
            
            if len(bottom_idx):
                buy_price = df.loc[bottom_idx[0], 'close']
                
                # 计算5天后的价格（如果有）
                future_price = None
                future_date = None
                if bottom_idx[0] + 5 < len(df):
                    future_idx = bottom_idx[0] + 5
                    future_price = df.loc[future_idx, 'close']
                    future_date = df.loc[future_idx, 'date']
                
                potential_return = None
                if future_price:
                    potential_return = (future_price - buy_price) / buy_price * 100
                
                # 判断是否买入（置信度>70且潜在收益>5%）
                should_buy = panic_result.confidence > 70 and (potential_return is None or potential_return > 5)
                
                return {
                    'code': stock_code,
                    'name': stock_name,
                    'province': stock_info['province'],
                    'pattern_type': panic_result.pattern_type.value,
                    'confidence': panic_result.confidence,
                    'buy_signal': panic_result.buy_signal,
                    'buy_reason': panic_result.buy_reason,
                    'bottom_date': bottom_date,
                    'buy_price': buy_price,
                    'future_price': future_price,
                    'future_date': future_date,
                    'potential_return': potential_return,
                    'dip_amplitude': panic_result.dip_amplitude,
                    'rebound_amplitude': panic_result.rebound_amplitude,
                    'current_stage': panic_result.current_stage.value,
                    'limitup_count': limitup_count,
                    'limitup_sector': limitup_sector,
                    'should_buy': should_buy
                }
        
        return None
    
    def batch_scan(self, days: int = 180, max_stocks: int = None) -> List[Dict]:
        """
        批量扫描股票
        
        Args:
            days: 分析天数
            max_stocks: 最大分析股票数
            
        Returns:
            黄金坑买点列表
        """
        results = []
        processed_count = 0
        
        if not self.stock_list:
            print("未加载股票列表")
            return results
        
        total_stocks = len(self.stock_list)
        if max_stocks:
            total_stocks = min(max_stocks, total_stocks)
        
        print(f"开始批量扫描 {total_stocks} 只股票...")
        
        for stock_info in self.stock_list[:total_stocks]:
            processed_count += 1
            print(f"\n[{processed_count}/{total_stocks}]")
            
            result = self.scan_golden_pit(stock_info, days=days)
            if result:
                results.append(result)
                print(f"✅ 发现黄金坑买点: {stock_info['code']} - {stock_info['name']}")
            else:
                print(f"❌ 未发现买点: {stock_info['code']} - {stock_info['name']}")
        
        print(f"\n扫描完成！共发现 {len(results)} 个黄金坑买点")
        return results
    
    def generate_report(self, results: List[Dict]) -> str:
        """
        生成分析报告
        
        Args:
            results: 黄金坑分析结果列表
            
        Returns:
            分析报告内容
        """
        if not results:
            return "未发现黄金坑买点"
        
        # 按置信度排序
        results.sort(key=lambda x: x['confidence'], reverse=True)
        
        current_date = datetime.now().strftime('%Y-%m-%d')
        report = f"# 黄金坑买点分析报告 - {current_date}\n\n"
        report += f"## 分析概况\n"
        report += f"- 分析股票总数: {len(self.stock_list)}\n"
        report += f"- 发现黄金坑买点: {len(results)}\n"
        report += f"- 分析日期: {current_date}\n\n"
        
        report += "## 买点详情\n"
        report += "| 是否买入 | 股票代码 | 股票名称 | 买入价格 | 历史涨停次数 | 历史涨停关联的板块 | 形态类型 | 置信度 | 买点日期 | 5日预期收益 | 下跌幅度 | 反弹幅度 | 当前阶段 | 买点理由 |\n"
        report += "|---------|---------|---------|---------|-------------|------------------|---------|---------|---------|-------------|---------|---------|---------|---------|\n"
        
        for result in results:
            # 处理可能的None值
            should_buy_str = "是" if result.get('should_buy', False) else "否"
            
            potential_return = result.get('potential_return')
            potential_return_str = f"{potential_return:.2f}%" if potential_return is not None else "-"
            
            dip_amplitude = result.get('dip_amplitude')
            dip_amplitude_str = f"{dip_amplitude:.2f}%" if dip_amplitude is not None else "-"
            
            rebound_amplitude = result.get('rebound_amplitude')
            rebound_amplitude_str = f"{rebound_amplitude:.2f}%" if rebound_amplitude is not None else "-"
            
            confidence = result.get('confidence')
            confidence_str = f"{confidence:.1f}" if confidence is not None else "-"
            
            buy_price = result.get('buy_price')
            buy_price_str = f"{buy_price:.2f}" if buy_price is not None else "-"
            
            limitup_count = result.get('limitup_count', 0)
            limitup_sector = result.get('limitup_sector', '-')
            
            report += f"| {should_buy_str} | {result['code']} | {result['name']} | {buy_price_str} | {limitup_count} | {limitup_sector} | {result['pattern_type']} | {confidence_str} | {result['bottom_date']} | {potential_return_str} | {dip_amplitude_str} | {rebound_amplitude_str} | {result['current_stage']} | {result['buy_reason']} |\n"
        
        report += "\n## 投资建议\n"
        report += "1. 黄金坑形态是一种较为可靠的买点信号，但仍需结合其他技术指标验证\n"
        report += "2. 优先选择置信度高（>70）的股票\n"
        report += "3. 建议在买点价格附近分批建仓\n"
        report += "4. 设置止损位，通常为买点价格的8-10%\n"
        report += "5. 关注成交量变化，放量突破时可加仓\n"
        report += "6. 注意大盘环境，避免在系统性风险时入场\n"
        report += "7. 历史涨停次数多的股票通常具有较强的市场关注度和活跃度\n"
        
        return report
    
    def save_report(self, report: str, filename: str = None):
        """
        保存分析报告
        
        Args:
            report: 报告内容
            filename: 文件名
        """
        # 确保data/trend_analysis目录存在
        os.makedirs('data/trend_analysis', exist_ok=True)
        
        if not filename:
            filename = f"golden_pit_scan_report_{datetime.now().strftime('%Y%m%d')}.md"
        
        # 保存到data/trend_analysis目录
        filepath = os.path.join('data/trend_analysis', filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"\n报告已保存到: {filepath}")
        except Exception as e:
            print(f"保存报告失败: {str(e)}")
    
    def upload_report_to_gitee(self, markdown_content: str):
        """
        将分析报告上传到Gitee
        
        Args:
            markdown_content: Markdown格式的报告内容
        """
        client = GiteeClient()
        current_date = datetime.now().strftime('%Y%m%d')
        
        remote_path = f"xg/黄金坑_{current_date}.md"
        message = f"更新黄金坑买点分析报告 {current_date}"
        
        success = client.upload_content(markdown_content, remote_path, message=message)
        
        if success:
            print(f"✅ 分析报告已成功上传至Gitee: {remote_path}")
        else:
            print(f"❌ 分析报告上传失败: {remote_path}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='黄金坑买点分析程序')
    parser.add_argument('--csv', type=str, default='sources/stock.csv', help='股票CSV文件路径')
    parser.add_argument('--limitup', type=str, default='sources/stock_limitup.csv', help='涨停CSV文件路径')
    parser.add_argument('--days', type=int, default=180, help='分析天数，默认180天')
    parser.add_argument('--max-stocks', type=int, default=None, help='最大分析股票数')
    parser.add_argument('--report', type=str, default=None, help='报告文件名')
    
    args = parser.parse_args()
    
    scanner = GoldenPitScanner()
    
    # 加载股票列表
    scanner.load_stock_list(args.csv)
    
    # 加载涨停数据
    scanner.load_limitup_data(args.limitup)
    
    # 批量扫描
    results = scanner.batch_scan(days=args.days, max_stocks=args.max_stocks)
    
    # 生成报告
    if results:
        report = scanner.generate_report(results)
        print("\n" + "="*80)
        print("黄金坑买点分析报告")
        print("="*80)
        print(report)
        
        # 保存报告
        scanner.save_report(report, args.report)
        
        # 上传报告到Gitee
        scanner.upload_report_to_gitee(report)
    else:
        print("\n未发现黄金坑买点")


if __name__ == "__main__":
    main()
