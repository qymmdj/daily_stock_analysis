"""
趋势买点分析主函数
根据趋势买点分析.md需求实现完整的分析流程（更新版）
"""
import os
import sys

# 添加src目录到Python路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from typing import Dict, Optional, List
import json
from datetime import datetime, timedelta
 
from qym.trend_analysis.kline_fetcher import KLineFetcher
from qym.trend_analysis.ma1020_analyzer import TrendAnalyzer
from gitee_client import GiteeClient


def analyze_single_stock(stock_code: str) -> Optional[Dict]:
    """分析单个股票趋势支撑点"""
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
        print(f"股票代码: {result['code']}")
        print(f"接近10日均线记录数: {len(result['near_10'])}")
        print(f"接近20日均线记录数: {len(result['near_20'])}")
        print(f"接近10日均线详情: {result['near_10']}")
        print(f"接近20日均线详情: {result['near_20']}")

    return result


def batch_analyze_from_gitee() -> List[Dict]:
    """从Gitee获取股票列表并批量分析"""
    client = GiteeClient()
    
    # 计算4日前和10日后的时间
    four_days_ago = datetime.now() - timedelta(days=4)
    ten_days_later = datetime.now() + timedelta(days=15)
    
    # 生成日期列表
    date_range = []
    current_date = four_days_ago
    while current_date <= ten_days_later:
        date_range.append(current_date.strftime("%Y%m%d"))
        current_date += timedelta(days=1)
    
    # 获取所有日期的股票数据并合并
    all_stocks = {}
    for date_str in date_range:
        try:
            # 尝试获取指定日期的文件
            file_content = client.download_file(f"hotsubject/{date_str}.json", "qymmdj/stockdb")
            if file_content:
                data = json.loads(file_content)
                if 'data' in data and 'items' in data['data']:
                    for item in data['data']['items']:
                        if len(item) > 0:
                            stock_code = item[0]  # 股票代码在索引0
                            stock_info = {
                                'code': item[0],
                                'name': item[1] if len(item) > 1 else '',
                                'price': item[2] if len(item) > 2 else 0,
                                'change_rate': item[3] if len(item) > 3 else 0,
                                'circulation_value': item[4] if len(item) > 4 else 0,
                                'description': item[5] if len(item) > 5 else '',
                                'enter_time': item[6] if len(item) > 6 else 0,
                                'up_limit': item[7] if len(item) > 7 else False,
                                'plates': item[8] if len(item) > 8 else [],
                                'time_on_market': item[9] if len(item) > 9 else 0,
                                'turnover_ratio': item[10] if len(item) > 10 else 0,
                                'm_days_n_boards': item[11] if len(item) > 11 else 0,
                                'report_id': item[12] if len(item) > 12 else 0,
                                'report_title': item[13] if len(item) > 13 else '',
                                'report_type': item[14] if len(item) > 14 else 0,
                                'report_url': item[15] if len(item) > 15 else ''
                            }
                            # 去重：只保存第一次出现的股票
                            if stock_code not in all_stocks:
                                all_stocks[stock_code] = stock_info
        except Exception as e:
            print(f"获取 {date_str}.json 时出错: {str(e)}")
            continue
    
    # 分析每只股票
    total_stocks = len(all_stocks)
    print(f"\n开始分析总共 {total_stocks} 只股票")
    
    results = []
    processed_count = 0
    
    for stock_code, stock_info in all_stocks.items():
        processed_count += 1
        print(f"\n正在分析股票 ({processed_count}/{total_stocks}): {stock_code} ({stock_info['name']})")
        
        # 获取趋势分析结果
        trend_result = analyze_single_stock(stock_code)
        
        if trend_result:
            # 计算各项指标
            near_10_count = len(trend_result['near_10'])
            near_20_count = len(trend_result['near_20'])
            
            # 计算第二天上涨概率
            near_10_up_count = sum(1 for item in trend_result['near_10'] 
                                   if item['next_rate'] is not None and item['next_rate'] > 0)
            near_10_up_prob = near_10_up_count / near_10_count if near_10_count > 0 else 0
            
            near_20_up_count = sum(1 for item in trend_result['near_20'] 
                                   if item['next_rate'] is not None and item['next_rate'] > 0)
            near_20_up_prob = near_20_up_count / near_20_count if near_20_count > 0 else 0
            
            # 计算放量大涨相关指标
            large_vol_10_count = sum(1 for item in trend_result['near_10'] if item['is_large_volumn'])
            large_vol_20_count = sum(1 for item in trend_result['near_20'] if item['is_large_volumn'])
            
            large_vol_10_up_count = sum(1 for item in trend_result['near_10'] 
                                        if item['is_large_volumn'] and item['next_rate'] is not None and item['next_rate'] > 0)
            large_vol_10_up_prob = large_vol_10_up_count / large_vol_10_count if large_vol_10_count > 0 else 0
            
            large_vol_20_up_count = sum(1 for item in trend_result['near_20'] 
                                        if item['is_large_volumn'] and item['next_rate'] is not None and item['next_rate'] > 0)
            large_vol_20_up_prob = large_vol_20_up_count / large_vol_20_count if large_vol_20_count > 0 else 0
            
            # 获取今天是否靠近均线的信息
            today_near = ""
            if trend_result['near_10']:
                latest_near_10 = trend_result['near_10'][0]  # 最新的一条
                if latest_near_10['day'] == datetime.now().strftime('%Y-%m-%d'):
                    today_near = "10日均线"
            if not today_near and trend_result['near_20']:
                latest_near_20 = trend_result['near_20'][0]  # 最新的一条
                if latest_near_20['day'] == datetime.now().strftime('%Y-%m-%d'):
                    today_near = "20日均线"
            
            # 整合结果
            result = {
                'plate': ', '.join([p['name'] for p in stock_info['plates']]) if stock_info['plates'] else '',  # 归属板块
                'stock_code': stock_info['code'],  # 股票代码
                'stock_name': stock_info['name'],  # 股票名称
                'near_10_count': near_10_count,  # 靠近10日均线次数
                'near_10_up_prob': round(near_10_up_prob * 100, 2),  # 靠近10日均线次数第二天上涨概率
                'near_20_count': near_20_count,  # 靠近20日均线次数
                'near_20_up_prob': round(near_20_up_prob * 100, 2),  # 靠近20日均线次数第二天上涨概率
                'large_vol_10_count': large_vol_10_count,  # 10日均线放量大涨次数
                'large_vol_10_up_prob': round(large_vol_10_up_prob * 100, 2),  # 10日均线放量大涨第二天上涨概率
                'large_vol_20_count': large_vol_20_count,  # 20日均线放量大涨次数
                'large_vol_20_up_prob': round(large_vol_20_up_prob * 100, 2),  # 20日均线放量大涨第二天上涨概率
                'today_near': today_near  # 今天靠近10日还是20日
            }
            results.append(result)
        
        # 显示进度
        progress_percent = (processed_count / total_stocks) * 100
        print(f"进度: {processed_count}/{total_stocks} ({progress_percent:.1f}%) - 已处理股票: {stock_code}")
    
    print(f"\n股票分析完成! 总共处理了 {processed_count} 只股票，成功分析了 {len(results)} 只股票")
    return results


def output_batch_results(results: List[Dict]):
    """输出批量分析结果"""
    print("\n=== 批量分析结果 ===")
    print(f"{'板块':<15} {'代码':<10} {'名称':<10} {'10均次数':<8} {'10均上涨率':<10} {'20均次数':<8} {'20均上涨率':<10} {'放量10次':<8} {'放量10率':<8} {'放量20次':<8} {'放量20率':<8} {'今日靠近':<8}")
    print("-" * 140)
    
    for result in results:
        print(f"{result['plate']:<15} {result['stock_code']:<10} {result['stock_name']:<10} "
              f"{result['near_10_count']:<8} {result['near_10_up_prob']:<10} {result['near_20_count']:<8} "
              f"{result['near_20_up_prob']:<10} {result['large_vol_10_count']:<8} {result['large_vol_10_up_prob']:<8} "
              f"{result['large_vol_20_count']:<8} {result['large_vol_20_up_prob']:<8} {result['today_near']:<8}")


def generate_markdown_report(results: List[Dict]) -> str:
    """
    生成Markdown格式的分析报告
    
    Args:
        results: 分析结果列表
        
    Returns:
        str: Markdown格式的报告内容
    """
    import datetime
    current_date = datetime.datetime.now().strftime('%Y-%m-%d')
    
    markdown_content = f"""# MA趋势分析报告 - {current_date}

## 概述

本次分析了从 {(datetime.datetime.now() - datetime.timedelta(days=4)).strftime('%Y-%m-%d')} 到 {(datetime.datetime.now() + datetime.timedelta(days=10)).strftime('%Y-%m-%d')} 期间的股票数据，共分析 {len(results)} 只股票。

## 详细分析结果

| 板块 | 代码 | 名称 | 10均次数 | 10均上涨率 | 20均次数 | 20均上涨率 | 放量10次 | 10日放量 | 20日放量 | 20日放量上涨概率 | 今日靠近 |
|------|------|------|--------|----------|--------|----------|--------|--------|--------|--------|--------|
"""
    
    for result in results:
        markdown_content += f"| {result['plate']} | {result['stock_code']} | {result['stock_name']} | {result['near_10_count']} | {result['near_10_up_prob']}% | {result['near_20_count']} | {result['near_20_up_prob']}% | {result['large_vol_10_count']} | {result['large_vol_10_up_prob']}% | {result['large_vol_20_count']} | {result['large_vol_20_up_prob']}% | {result['today_near']} |\n"
    
    # 添加统计摘要
    if results:
        avg_10_prob = sum(r['near_10_up_prob'] for r in results) / len(results)
        avg_20_prob = sum(r['near_20_up_prob'] for r in results) / len(results)
        
        markdown_content += f"""
## 统计摘要

- 平均10日均线上涨概率: {avg_10_prob:.2f}%
- 平均20日均线上涨概率: {avg_20_prob:.2f}%
- 总计股票数量: {len(results)}

## 分析说明

1. **靠近10日均线次数**: 股价接近10日均线的交易日数量
2. **靠近10日均线次数第二天上涨概率**: 接近10日均线后第二天上涨的概率
3. **靠近20日均线次数**: 股价接近20日均线的交易日数量
4. **靠近20日均线次数第二天上涨概率**: 接近20日均线后第二天上涨的概率
5. **放量大涨次数**: 成交量放大且涨幅较大的次数
6. **放量大涨第二天上涨概率**: 放量大涨后第二天上涨的概率

> 注意: 本报告基于趋势买点分析算法生成，投资决策需谨慎参考。
"""
    
    return markdown_content


def upload_report_to_gitee(markdown_content: str):
    """
    将分析报告上传到Gitee
    
    Args:
        markdown_content: Markdown格式的报告内容
    """
    client = GiteeClient()
    import datetime
    current_date = datetime.datetime.now().strftime('%Y-%m-%d')
    
    remote_path = f"xg/回踩10日20日均线_{current_date}.md"
    message = f"更新MA趋势分析报告 {current_date}"
    
    success = client.upload_content(markdown_content, remote_path, message=message)
    
    if success:
        print(f"✅ 分析报告已成功上传至Gitee: {remote_path}")
    else:
        print(f"❌ 分析报告上传失败: {remote_path}")


if __name__ == "__main__":
    # 示例：分析特定股票
    # result = analyze_single_stock("300903.SZ")  # 江苏银行
    # if not result:
    #     print("未找到符合条件的趋势支撑点")
        
    # 或者执行批量分析（需要配置Gitee客户端）
     batch_results = batch_analyze_from_gitee()
     
     # 只保留今日靠近有值的记录
     today_near_results = [r for r in batch_results if r.get('today_near')]
     
     # 排序结果：先按板块，再按20均上涨率，最后按10均上涨率降序排序
     today_near_results.sort(key=lambda x: (x['plate'], -x['near_20_up_prob'], -x['near_10_up_prob']))
     
     output_batch_results(today_near_results)
     
     # 生成并上传Markdown报告到Gitee（仅当有今日靠近的记录时）
     if today_near_results:
         markdown_report = generate_markdown_report(today_near_results)
         upload_report_to_gitee(markdown_report)
     else:
         print("没有今日靠近均线的记录，不生成报告文件")
