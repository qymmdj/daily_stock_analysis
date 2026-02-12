#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
历史新高突破分析程序

功能：
1. 读取 sources/stock_limitup.csv 文件中的股票列表
2. 获取每只股票至少1年的历史K线数据
3. 找出最近一年中的股价最高价
4. 判断当前价格是否已超过一年中的最高价，超出比率控制在10%以内
5. 输出符合条件的股票信息
"""

import os
import sys
from typing import Dict, List, Optional
import argparse
from datetime import datetime

# 添加src目录到Python路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from qym.trend_analysis.kline_fetcher import KLineFetcher
from gitee_client import GiteeClient
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
            with open(csv_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
                # 跳过表头
                for line in lines[1:]:
                    # 分割行数据（处理空格或制表符分隔）
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        # 加载股票信息
                        stock_info = {
                            'code': parts[1],
                            'name': parts[2],
                            'sector': parts[3],
                            'limitup_count': int(parts[0])
                        }
                        stock_list.append(stock_info)
                        
                        # 加载涨停数据
                        limitup_data[parts[1]] = {
                            'count': int(parts[0]),
                            'sector': parts[3]
                        }
            
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
    
    def analyze_high_price_break(self, stock_info: Dict, days: int = 400) -> Optional[Dict]:
        """
        分析单个股票的历史新高突破情况
        
        Args:
            stock_info: 股票信息
            days: 分析天数
            
        Returns:
            分析结果
        """
        stock_code = stock_info['code']
        stock_name = stock_info['name']
        stock_sector = stock_info['sector']
        limitup_count = stock_info['limitup_count']
        
        print(f"正在分析: {stock_code} - {stock_name}")
        
        # 获取K线数据
        kline_data = self.fetch_kline_data(stock_code, days=days)
        if not kline_data:
            return None
        
        # 转换为DataFrame
        df = self.convert_to_dataframe(kline_data)
        if df.empty:
            return None
        
        # 确保有足够的数据（至少250个交易日，约1年）
        if len(df) < 250:
            print(f"⚠️  {stock_code} 数据不足1年，跳过分析")
            return None
        
        # 计算最近一年的数据（最后250个交易日）
        recent_year_data = df.tail(250)
        
        # 找出最近一年的最高价
        yearly_high = recent_year_data['high'].max()
        
        # 获取当前价格（最后一天的收盘价）
        current_price = df.iloc[-1]['close']
        
        # 计算超出比率
        if yearly_high > 0:
            exceed_ratio = (current_price - yearly_high) / yearly_high * 100
        else:
            exceed_ratio = 0
        
        # 判断是否满足条件：当前价格超过历史最高价，且超出比率在10%以内
        if current_price > yearly_high and exceed_ratio <= 10:
            return {
                'code': stock_code,
                'name': stock_name,
                'sector': stock_sector,
                'limitup_count': limitup_count,
                'yearly_high': yearly_high,
                'current_price': current_price,
                'exceed_ratio': exceed_ratio
            }
        
        return None
    
    def batch_analyze(self, days: int = 400, max_stocks: int = None) -> List[Dict]:
        """
        批量分析股票
        
        Args:
            days: 分析天数
            max_stocks: 最大分析股票数
            
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
        
        print(f"开始批量分析 {total_stocks} 只股票...")
        
        for stock_info in self.stock_list[:total_stocks]:
            processed_count += 1
            print(f"\n[{processed_count}/{total_stocks}]")
            
            result = self.analyze_high_price_break(stock_info, days=days)
            if result:
                results.append(result)
                print(f"✅ 发现符合条件的股票: {stock_info['code']} - {stock_info['name']}")
            else:
                print(f"❌ 不符合条件: {stock_info['code']} - {stock_info['name']}")
        
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
        
        # 按超出比率排序
        results.sort(key=lambda x: x['exceed_ratio'])
        
        print("\n" + "="*120)
        print("历史新高突破分析结果")
        print("="*120)
        print(f"分析日期: {datetime.now().strftime('%Y-%m-%d')}")
        print(f"符合条件的股票数量: {len(results)}")
        print("="*120)
        print("股票代码 | 股票名称 | 关联板块 | 历史涨停次数 | 历史最高价 | 当前价格 | 超出比率")
        print("-"*120)
        
        for result in results:
            print(f"{result['code']} | {result['name']} | {result['sector']} | {result['limitup_count']} | {result['yearly_high']:.2f} | {result['current_price']:.2f} | {result['exceed_ratio']:.2f}%")
        
        print("="*120)
        
        # 保存结果到文件
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
        
        report = f"# 历史新高突破分析报告 - {current_date}\n\n"
        report += f"## 分析概况\n"
        report += f"- 分析日期: {current_date}\n"
        report += f"- 符合条件的股票数量: {len(results)}\n\n"
        
        if not results:
            report += "未发现符合条件的股票\n"
            return report
        
        # 按超出比率排序
        results.sort(key=lambda x: x['exceed_ratio'])
        
        report += "## 股票列表\n"
        report += "| 股票代码 | 股票名称 | 关联板块 | 历史涨停次数 | 历史最高价 | 当前价格 | 超出比率 |\n"
        report += "|---------|---------|---------|-------------|-----------|---------|---------|\n"
        
        for result in results:
            report += f"| {result['code']} | {result['name']} | {result['sector']} | {result['limitup_count']} | {result['yearly_high']:.2f} | {result['current_price']:.2f} | {result['exceed_ratio']:.2f}% |\n"
        
        report += "\n## 投资建议\n"
        report += "1. 历史新高突破通常意味着股票进入新的上涨空间，具有较强的上涨动能\n"
        report += "2. 超出比率控制在10%以内，避免追高风险\n"
        report += "3. 建议结合成交量、技术指标等综合判断\n"
        report += "4. 设置止损位，通常为历史最高价的5-8%\n"
        report += "5. 关注大盘环境，避免在系统性风险时入场\n"
        report += "6. 历史涨停次数多的股票通常具有较强的市场关注度和活跃度\n"
        
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
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("历史新高突破分析结果\n")
                f.write(f"分析日期: {datetime.now().strftime('%Y-%m-%d')}\n")
                f.write(f"符合条件的股票数量: {len(results)}\n")
                f.write("-"*120 + "\n")
                f.write("股票代码 | 股票名称 | 关联板块 | 历史涨停次数 | 历史最高价 | 当前价格 | 超出比率\n")
                f.write("-"*120 + "\n")
                
                for result in results:
                    f.write(f"{result['code']} | {result['name']} | {result['sector']} | {result['limitup_count']} | {result['yearly_high']:.2f} | {result['current_price']:.2f} | {result['exceed_ratio']:.2f}%\n")
            
            print(f"\n结果已保存到: {filepath}")
        except Exception as e:
            print(f"保存结果失败: {str(e)}")
    
    def upload_results_to_gitee(self, results: List[Dict]):
        """
        将分析结果上传到Gitee
        
        Args:
            results: 分析结果列表
        """
        try:
            client = GiteeClient()
            current_date = datetime.now().strftime('%Y%m%d')
            
            # 生成Markdown格式的内容
            markdown_content = self.generate_markdown_report(results)
            
            # 上传到Gitee
            remote_path = f"xg/历史新高.{current_date}.md"
            message = f"更新历史新高突破分析报告 {current_date}"
            
            success = client.upload_content(markdown_content, remote_path, message=message)
            
            if success:
                print(f"✅ 分析报告已成功上传至Gitee: {remote_path}")
            else:
                print(f"❌ 分析报告上传失败: {remote_path}")
                
        except Exception as e:
            print(f"上传到Gitee失败: {str(e)}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='历史新高突破分析程序')
    parser.add_argument('--limitup', type=str, default='sources/stock_limitup.csv', help='涨停CSV文件路径')
    parser.add_argument('--days', type=int, default=400, help='分析天数，默认400天')
    parser.add_argument('--max-stocks', type=int, default=None, help='最大分析股票数')
    
    args = parser.parse_args()
    
    analyzer = HighPriceBreaker()
    
    # 加载股票列表和涨停数据
    analyzer.load_stock_and_limitup_data(args.limitup)
    
    # 批量分析
    results = analyzer.batch_analyze(days=args.days, max_stocks=args.max_stocks)
    
    # 生成输出
    analyzer.generate_output(results)
    
    # 上传结果到Gitee
    analyzer.upload_results_to_gitee(results)


if __name__ == "__main__":
    main()
