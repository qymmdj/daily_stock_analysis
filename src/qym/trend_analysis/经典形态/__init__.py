# -*- coding: utf-8 -*-
"""
经典上涨形态识别模块

包含4种经典上涨形态识别：
1. 均线多头排列
2. 上升通道（旗形）
3. 首次回踩重要均线
4. 圆弧底/杯柄形态
"""

from .pattern_detector import (
    PatternType,
    PatternResult,
    BullishPatternDetector,
    detect_bullish_patterns
)
from .strength_analyzer import (
    StrengthLevel,
    StrengthResult,
    PriceStrengthAnalyzer,
    analyze_price_strength
)
from .classic_pattern_analyzer import (
    ClassicPatternAnalyzer,
    AnalysisResult,
    analyze_stock,
    analyze_stocks
)

__all__ = [
    'PatternType',
    'PatternResult',
    'BullishPatternDetector',
    'detect_bullish_patterns',
    'StrengthLevel',
    'StrengthResult',
    'PriceStrengthAnalyzer',
    'analyze_price_strength',
    'ClassicPatternAnalyzer',
    'AnalysisResult',
    'analyze_stock',
    'analyze_stocks'
]
