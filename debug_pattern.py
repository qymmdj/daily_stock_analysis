#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试形态识别算法
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from src.pattern_analyzer import PatternAnalyzer


def create_simple_dip_data():
    """创建简单的下跌数据用于调试"""
    dates = pd.date_range(start='2024-01-01', periods=80, freq='D')

    prices = []
    # 前期：20天上涨
    for i in range(20):
        prices.append(10.0 * (1 + i * 0.005))  # 每日上涨0.5%

    # 下跌：5天大幅下跌
    for i in range(5):
        prices.append(prices[-1] * 0.95)  # 每日下跌5%

    # 坑底：10天震荡
    for i in range(10):
        prices.append(prices[-1] * (1 + np.random.uniform(-0.02, 0.02)))

    # 反弹：15天上涨
    for i in range(15):
        prices.append(prices[-1] * 1.03)  # 每日上涨3%

    # 剩余天数
    remaining = 80 - len(prices)
    for i in range(remaining):
        prices.append(prices[-1] * (1 + np.random.uniform(-0.01, 0.01)))

    df = pd.DataFrame({
        'date': dates.strftime('%Y-%m-%d'),
        'open': [p * (1 + np.random.uniform(-0.01, 0.01)) for p in prices],
        'high': [p * (1 + np.random.uniform(0, 0.02)) for p in prices],
        'low': [p * (1 - np.random.uniform(0, 0.02)) for p in prices],
        'close': prices,
        'volume': [np.random.randint(1000000, 2000000) for _ in range(80)]
    })

    return df


def test_dip_detection():
    """测试下跌检测"""
    print("=" * 60)
    print("测试下跌检测")
    print("=" * 60)

    df = create_simple_dip_data()
    analyzer = PatternAnalyzer()

    # 计算指标
    df = analyzer._calculate_indicators(df)

    print(f"数据长度: {len(df)}")
    print(f"价格序列前10个: {df['close'].iloc[:10].values.round(2)}")
    print(f"价格序列20-30: {df['close'].iloc[20:30].values.round(2)}")

    # 手动检查_is_dip_start条件
    for i in range(30, 40):
        if analyzer._is_dip_start(df, i):
            print(f"\n在索引 {i} 检测到下跌起点")
            current = df.iloc[i]
            prev = df.iloc[i-1]

            # 前期趋势
            pre_prices = df['close'].iloc[i-analyzer.PRE_TREND_DAYS:i].values
            x = np.arange(len(pre_prices))
            slope, _ = np.polyfit(x, pre_prices, 1)
            avg_price = np.mean(pre_prices)
            trend_slope_pct = slope / avg_price if avg_price > 0 else 0

            print(f"  前期趋势斜率: {trend_slope_pct:.4%}")
            print(f"  当前K线: 开盘{current['open']:.2f}, 收盘{current['close']:.2f}, 是否为阴线: {current['close'] <= current['open']}")
            print(f"  价格变化: {(current['close'] - prev['close']) / prev['close'] * 100:.2f}%")
            break
    else:
        print("\n未检测到下跌起点")

    # 测试_find_potential_patterns
    print("\n" + "=" * 60)
    print("测试潜在形态查找")
    print("=" * 60)

    patterns = analyzer._find_potential_patterns(df, "TEST")
    print(f"找到 {len(patterns)} 个潜在形态")

    if patterns:
        for i, pattern in enumerate(patterns):
            print(f"\n形态 {i+1}:")
            print(f"  置信度: {pattern.confidence:.1f}")
            print(f"  下跌开始: {pattern.dip_start_date}")
            print(f"  坑底开始: {pattern.bottom_start_date}")
            print(f"  当前阶段: {pattern.current_stage.value}")

    return df, analyzer


def test_pattern_validation():
    """测试形态验证"""
    print("\n" + "=" * 60)
    print("测试形态验证")
    print("=" * 60)

    df = create_simple_dip_data()
    analyzer = PatternAnalyzer()
    df = analyzer._calculate_indicators(df)

    # 手动指定关键点
    dip_start = 20  # 第20天开始下跌
    dip_end = 24    # 第24天结束下跌
    bottom_end = 34 # 第34天结束坑底
    rebound_end = 49 # 第49天结束反弹

    is_valid = analyzer._validate_pattern(df, dip_start, dip_end, bottom_end, rebound_end)
    print(f"形态有效性: {is_valid}")

    if is_valid:
        # 计算特征
        dip_start_price = df['close'].iloc[dip_start-1]
        dip_end_price = df['close'].iloc[dip_end]
        dip_amplitude = (dip_end_price - dip_start_price) / dip_start_price * 100

        print(f"下跌特征:")
        print(f"  开始价格: {dip_start_price:.2f}")
        print(f"  结束价格: {dip_end_price:.2f}")
        print(f"  幅度: {dip_amplitude:.1f}%")
        print(f"  持续时间: {dip_end - dip_start + 1}天")

        # 检查参数
        print(f"\n算法参数:")
        print(f"  最小下跌幅度: {analyzer.DIP_MIN_AMPLITUDE}%")
        print(f"  最大下跌幅度: {analyzer.DIP_MAX_AMPLITUDE}%")
        print(f"  最小下跌天数: {analyzer.DIP_MIN_DAYS}")
        print(f"  最大下跌天数: {analyzer.DIP_MAX_DAYS}")


def main():
    """主调试函数"""
    print("开始调试形态识别算法")

    # 测试1: 下跌检测
    df, analyzer = test_dip_detection()

    # 测试2: 形态验证
    test_pattern_validation()

    # 测试3: 完整识别
    print("\n" + "=" * 60)
    print("测试完整识别")
    print("=" * 60)

    result = analyzer.detect_golden_pit(df, "DEBUG")
    if result:
        print("成功识别形态!")
        print(f"形态类型: {result.pattern_type.value}")
        print(f"置信度: {result.confidence:.1f}")
        print(f"下跌幅度: {result.dip_amplitude:.1f}%")
        print(f"反弹幅度: {result.rebound_amplitude:.1f}%")
        print(f"买点信号: {result.buy_signal} - {result.buy_reason}")
    else:
        print("未识别到形态")

        # 尝试放宽参数
        print("\n尝试放宽参数...")
        analyzer.DIP_MIN_AMPLITUDE = 5.0  # 降低最小跌幅
        analyzer.DIP_MIN_DAYS = 2         # 减少最小下跌天数

        result2 = analyzer.detect_golden_pit(df, "DEBUG")
        if result2:
            print("放宽参数后识别成功!")
            print(f"置信度: {result2.confidence:.1f}")
        else:
            print("放宽参数后仍未能识别")


if __name__ == "__main__":
    main()