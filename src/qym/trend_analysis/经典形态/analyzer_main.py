# -*- coding: utf-8 -*-
"""
经典上涨形态识别示例

演示如何使用经典形态识别模块
"""

import sys
import os
import datetime
import subprocess
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.qym.trend_analysis.经典形态 import (
    analyze_stock,
    analyze_stocks,
    ClassicPatternAnalyzer,
    detect_bullish_patterns,
    analyze_price_strength
)
from src.qym.trend_analysis.kline_fetcher import KLineFetcher
from src.qym.trend_analysis.csv_reader import StockLimitupCSVReader
import json


def single_stock():
    """示例：分析单只股票（从CSV文件读取）"""

    reader = StockLimitupCSVReader()
    stocks = reader.get_stock_list()

    if not stocks:
        print("CSV文件中没有股票数据")
        return

    stock = stocks[0]
    stock_code = stock.code
    stock_name = stock.name

    print(f"\n从CSV读取到 {len(stocks)} 只股票，分析第一只")
    print(f"正在分析 {stock_name}({stock_code})...")

    result = analyze_stock(stock_code, days=120, stock_name=stock_name)

    if result:
        print("\n分析结果：")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n{stock_name} 未检测到经典上涨形态")


def multiple_stocks():


    reader = StockLimitupCSVReader()
    stocks = reader.get_stock_list()

    if not stocks:
        print("CSV文件中没有股票数据")
        return

    stock_codes = [s.code for s in stocks]
    stock_names = {s.code: s.name for s in stocks}

    print(f"\n从CSV读取到 {len(stocks)} 只股票，分析前 {len(stock_codes)} 只")
    print(f"股票列表: {', '.join([f'{stock_names[c]}({c})' for c in stock_codes])}")

    results = analyze_stocks(stock_codes, days=120, stock_names=stock_names)

    if results:
        print(f"\n检测到 {len(results)} 只股票符合经典上涨形态：")
        for r in results:
            print(f"\n--- {r['股票名称']}({r['股票代码']}) ---")
            print(f"识别形态: {', '.join(r['识别形态'])}")
            print(f"股价强度: {r['股价强度']}")
            print(f"综合评分: {r['综合评分']}")
            print(f"风险提示: {r['当前风险提示']}")
    else:
        print("\n未检测到符合经典上涨形态的股票")
    
    # 生成markdown文件并推送到gitee
    generate_and_push_markdown(results)


def detailed_analysis():
    """示例：详细分析（从CSV文件读取）"""
    print("\n" + "=" * 60)
    print("示例3：详细分析（从CSV文件读取）")
    print("=" * 60)

    reader = StockLimitupCSVReader()
    stocks = reader.get_stock_list()

    if not stocks:
        print("CSV文件中没有股票数据")
        return

    stock = stocks[0] if len(stocks) == 1 else stocks[1]
    stock_code = stock.code
    stock_name = stock.name

    print(f"\n从CSV读取到 {len(stocks)} 只股票，分析第二只（如果存在）")
    print(f"正在获取 {stock_name}({stock_code}) 的K线数据...")

    fetcher = KLineFetcher()
    kline_data = fetcher.fetch_kline_data(stock_code, days=120)

    if not kline_data:
        print("获取数据失败")
        return

    print(f"获取到 {len(kline_data)} 条K线数据")

    print("\n1. 检测经典上涨形态...")
    patterns = detect_bullish_patterns(kline_data)

    if patterns:
        print(f"检测到 {len(patterns)} 个形态：")
        for p in patterns:
            print(f"  - {p['形态名称']}: 置信度 {p['置信度']}%")
            print(f"    描述: {p['形态描述']}")
            if p['风险提示']:
                print(f"    风险: {p['风险提示']}")
    else:
        print("未检测到经典上涨形态")

    print("\n2. 分析股价强度...")
    strength = analyze_price_strength(kline_data)

    if strength:
        print(f"强度等级: {strength['强度等级']}")
        print(f"短期强度: {strength['短期强度']}")
        print(f"中期强度: {strength['中期强度']}")
        print(f"量价比: {strength['量价比']}")
        print(f"MA20乖离率: {strength['MA20乖离率']}")
        if strength['风险提示']:
            print(f"风险提示: {strength['风险提示']}")


def with_analyzer_class():
    """示例：使用分析器类（从CSV文件读取）"""
    print("\n" + "=" * 60)
    print("示例4：使用分析器类（从CSV文件读取）")
    print("=" * 60)

    reader = StockLimitupCSVReader()
    stocks = reader.get_stock_list()

    if not stocks:
        print("CSV文件中没有股票数据")
        return

    stock = stocks[0]
    stock_code = stock.code
    stock_name = stock.name

    print(f"\n从CSV读取到 {len(stocks)} 只股票，分析第一只")
    print(f"正在分析 {stock_name}({stock_code})...")

    analyzer = ClassicPatternAnalyzer()

    result = analyzer.analyze(
        stock_code=stock_code,
        days=120,
        stock_name=stock_name
    )

    if result:
        print("\n分析结果：")
        print(result.to_dict())
    else:
        print(f"\n{stock_name} 未检测到经典上涨形态")


def generate_and_push_markdown(results):
    """生成markdown文件并推送到gitee的stockdb仓库xg目录"""
    # 获取当前日期
    today = datetime.datetime.now().strftime("%Y%m%d")
    filename = f"经典形态_{today}.md"
    
    # 生成markdown内容
    md_content = f"# 经典上涨形态分析报告\n\n"
    md_content += f"生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    if results:
        md_content += f"## 检测结果\n\n"
        md_content += f"共检测到 **{len(results)}** 只股票符合经典上涨形态\n\n"
        
        # 使用markdown表格展示
        md_content += "| 股票名称 | 股票代码 | 识别形态 | 股价强度 | 综合评分 | 风险提示 |\n"
        md_content += "|----------|----------|----------|----------|----------|----------|\n"
        
        for r in results:
            patterns = ', '.join(r['识别形态'])
            md_content += f"| {r['股票名称']} | {r['股票代码']} | {patterns} | {r['股价强度']} | {r['综合评分']} | {r['当前风险提示']} |\n"
        
        md_content += "\n"
        
        # 添加详细分析
        md_content += "## 详细分析\n\n"
        for r in results:
            md_content += f"### {r['股票名称']}({r['股票代码']})\n\n"
            md_content += f"- **识别形态**: {', '.join(r['识别形态'])}\n"
            md_content += f"- **股价强度**: {r['股价强度']}\n"
            md_content += f"- **综合评分**: {r['综合评分']}\n"
            md_content += f"- **风险提示**: {r['当前风险提示']}\n\n"
    else:
        md_content += "## 检测结果\n\n"
        md_content += "未检测到符合经典上涨形态的股票\n\n"
    
    # 保存markdown文件到stockdb仓库的xg目录
    stockdb_path = os.path.join(os.path.dirname(project_root), "stockdb")
    output_dir = os.path.join(stockdb_path, "xg")
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, filename)
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    
    print(f"\n已生成markdown文件: {file_path}")
    
    # 推送到gitee的stockdb仓库
    try:
        # 进入stockdb项目目录
        os.chdir(stockdb_path)
        
        # 执行git命令
        subprocess.run(["git", "add", f"xg/{filename}"], check=True)
        subprocess.run(["git", "commit", "-m", f"更新经典形态分析报告 {today}"], check=True)
        subprocess.run(["git", "push"], check=True)
        
        print("\n已成功推送到gitee的stockdb仓库xg目录")
    except subprocess.CalledProcessError as e:
        print(f"\n推送失败: {e}")
    except Exception as e:
        print(f"\n推送过程中出现错误: {e}")


if __name__ == "__main__":
    multiple_stocks()
