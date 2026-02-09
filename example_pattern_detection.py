#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
形态识别使用示例

本示例展示如何使用形态识别功能分析股票数据：
1. 从Akshare获取历史K线数据
2. 识别黄金坑和恐慌性洗盘形态
3. 输出分析结果和买点信号
"""

import sys
import os
import logging
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

from src.pattern_analyzer import analyze_pattern, PatternAnalyzer
try:
    from data_provider.akshare_fetcher import AkshareFetcher
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False
    print("警告：未找到AkshareFetcher，将使用模拟数据")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def analyze_stock_pattern(stock_code: str, days: int = 120):
    """
    分析单只股票的形态

    Args:
        stock_code: 股票代码（如'000001.SZ'）
        days: 需要分析的天数（默认120天）
    """
    print(f"\n{'='*60}")
    print(f"分析股票: {stock_code}")
    print(f"{'='*60}")

    # 1. 获取数据
    df = fetch_stock_data(stock_code, days)
    if df is None or df.empty:
        print(f"无法获取 {stock_code} 的数据")
        return None

    print(f"获取到 {len(df)} 个交易日数据")
    print(f"数据时间范围: {df['date'].iloc[0]} 至 {df['date'].iloc[-1]}")

    # 2. 形态识别
    print("\n开始形态识别...")
    result = analyze_pattern(df, stock_code)

    # 3. 输出结果
    print_result(result)

    return result


def fetch_stock_data(stock_code: str, days: int):
    """获取股票数据"""
    if HAS_AKSHARE:
        try:
            fetcher = AkshareFetcher()

            # 计算开始日期
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days * 2)  # 多取一些数据，因为akshare可能返回非交易日

            # 获取日线数据
            df = fetcher.get_daily_data(stock_code, start_date, end_date)

            if df is not None and not df.empty:
                # 确保数据格式正确
                required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
                if all(col in df.columns for col in required_cols):
                    # 按日期排序
                    df = df.sort_values('date').reset_index(drop=True)

                    # 如果数据太多，只取最近days天
                    if len(df) > days:
                        df = df.iloc[-days:]

                    return df
                else:
                    print(f"数据列不完整，获取到的列: {df.columns.tolist()}")
            else:
                print(f"获取到的数据为空")

        except Exception as e:
            logger.error(f"获取数据失败: {e}")

    # 如果Akshare不可用或获取失败，使用模拟数据
    print(f"使用模拟数据替代（实际使用时请配置Akshare）")
    return generate_sample_data(days)


def generate_sample_data(days: int):
    """生成模拟数据用于演示"""
    import numpy as np

    dates = pd.date_range(
        start=datetime.now() - timedelta(days=days),
        periods=days,
        freq='D'
    )

    # 生成价格序列（包含一个黄金坑形态）
    prices = []
    # 前期上涨
    for i in range(int(days * 0.3)):
        prices.append(10.0 * (1 + i * 0.003))

    # 下跌
    dip_days = int(days * 0.1)
    for i in range(dip_days):
        prices.append(prices[-1] * 0.97)

    # 坑底震荡
    bottom_days = int(days * 0.15)
    for i in range(bottom_days):
        prices.append(prices[-1] * (1 + np.random.uniform(-0.02, 0.02)))

    # 反弹
    rebound_days = int(days * 0.2)
    for i in range(rebound_days):
        prices.append(prices[-1] * 1.02)

    # 剩余天数
    remaining = days - len(prices)
    for i in range(remaining):
        prices.append(prices[-1] * (1 + np.random.uniform(-0.01, 0.01)))

    # 确保长度正确
    prices = prices[:days]

    # 生成OHLCV
    data = []
    for i, price in enumerate(prices):
        date = dates[i]
        open_price = price * (1 + np.random.uniform(-0.01, 0.01))
        close_price = price * (1 + np.random.uniform(-0.01, 0.01))
        high_price = max(open_price, close_price) * (1 + np.random.uniform(0, 0.02))
        low_price = min(open_price, close_price) * (1 - np.random.uniform(0, 0.02))

        # 成交量：下跌放量，坑底缩量，反弹放量
        if i < len(prices) * 0.3:
            volume = np.random.randint(800000, 1500000)
        elif i < len(prices) * 0.4:
            volume = np.random.randint(1500000, 2500000)  # 下跌放量
        elif i < len(prices) * 0.55:
            volume = np.random.randint(600000, 1200000)   # 坑底缩量
        elif i < len(prices) * 0.75:
            volume = np.random.randint(1400000, 2300000)  # 反弹放量
        else:
            volume = np.random.randint(900000, 1800000)

        data.append({
            'date': date.strftime('%Y-%m-%d'),
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'volume': volume
        })

    return pd.DataFrame(data)


def print_result(result: dict):
    """打印分析结果"""
    if result['pattern_type'] == '无形态':
        print(f"\n未识别到明显的黄金坑或恐慌性洗盘形态")
        print(f"置信度: {result['confidence']}")
        return

    print(f"\n✅ 识别到形态: {result['pattern_type']}")
    print(f"   置信度: {result['confidence']}/100")
    print(f"   风险等级: {result['risk_level']}/5 (1最低, 5最高)")

    print(f"\n📅 关键时间点:")
    print(f"   下跌开始: {result.get('dip_start_date', 'N/A')}")
    print(f"   坑底开始: {result.get('bottom_start_date', 'N/A')}")
    print(f"   反弹开始: {result.get('rebound_start_date', 'N/A')}")
    if result.get('breakout_date'):
        print(f"   突破前期高点: {result['breakout_date']}")

    print(f"\n📊 形态特征:")
    print(f"   下跌幅度: {result['dip_amplitude']:.1f}% ({result['dip_duration']}天)")
    print(f"   反弹幅度: {result['rebound_amplitude']:.1f}% ({result['rebound_duration']}天)")
    print(f"   成交量比率: {result['volume_ratio']:.2f} (反弹/下跌)")
    print(f"   当前阶段: {result['current_stage']}")

    print(f"\n🎯 操作建议:")
    if result['buy_signal']:
        print(f"   ⭐ 发现买点信号: {result['buy_reason']}")
        print(f"   建议: 可考虑分批建仓，设置止损位")
    else:
        print(f"   ⏳ {result['buy_reason']}")
        print(f"   建议: 继续观察，等待更好时机")

    # 风险提示
    if result['risk_level'] >= 4:
        print(f"\n⚠️ 高风险提示: 该形态风险等级较高，请谨慎操作")
    elif result['risk_level'] <= 2:
        print(f"\n✅ 低风险提示: 该形态风险等级较低，相对安全")


def batch_analyze(stock_codes: list, days: int = 120):
    """批量分析多只股票"""
    print(f"\n{'='*60}")
    print(f"批量形态分析 ({len(stock_codes)} 只股票)")
    print(f"{'='*60}")

    results = []
    for code in stock_codes:
        result = analyze_stock_pattern(code, days)
        if result is not None:
            results.append(result)

    # 汇总结果
    print(f"\n{'='*60}")
    print(f"批量分析完成")
    print(f"{'='*60}")

    if results:
        # 按置信度排序
        valid_results = [r for r in results if r['pattern_type'] != '无形态']
        valid_results.sort(key=lambda x: x['confidence'], reverse=True)

        print(f"\n识别到 {len(valid_results)} 只股票具有目标形态:")
        for i, result in enumerate(valid_results[:5]):  # 显示前5只
            print(f"\n{i+1}. {result['code']} - {result['pattern_type']}")
            print(f"   置信度: {result['confidence']:.1f}, 风险等级: {result['risk_level']}/5")
            print(f"   下跌幅度: {result['dip_amplitude']:.1f}%, 反弹幅度: {result['rebound_amplitude']:.1f}%")
            if result['buy_signal']:
                print(f"   ⭐ 有买点信号")

        if len(valid_results) > 5:
            print(f"\n... 还有 {len(valid_results) - 5} 只股票未显示")

    return results


def main():
    """主函数"""
    print("股票形态识别系统 - 黄金坑/恐慌性洗盘检测")
    print("=" * 60)

    # 示例股票列表（可根据需要修改）
    sample_stocks = [
        "000001.SZ",  # 平安银行
        "000002.SZ",  # 万科A
        "300750.SZ",  # 宁德时代
        "600519.SH",  # 贵州茅台
    ]

    # 选择分析模式
    print("\n请选择分析模式:")
    print("1. 分析单只股票")
    print("2. 批量分析多只股票")
    print("3. 使用示例数据测试")

    try:
        choice = input("\n请输入选择 (1-3, 默认1): ").strip()
        if choice == "2":
            # 批量分析
            batch_analyze(sample_stocks, days=120)
        elif choice == "3":
            # 使用示例数据测试
            print("\n使用示例数据测试形态识别...")
            df = generate_sample_data(100)
            result = analyze_pattern(df, "EXAMPLE")
            print_result(result)
        else:
            # 单只股票分析
            stock_code = input("请输入股票代码 (如 000001.SZ, 默认 000001.SZ): ").strip()
            if not stock_code:
                stock_code = "000001.SZ"
            analyze_stock_pattern(stock_code, days=120)
    except KeyboardInterrupt:
        print("\n\n用户中断操作")
    except Exception as e:
        logger.error(f"运行出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()