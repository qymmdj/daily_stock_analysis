# -*- coding: utf-8 -*-
"""
经典上涨形态主分析器

整合形态识别和强度分析，输出完整的分析结果
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import logging

from .pattern_detector import BullishPatternDetector, detect_bullish_patterns
from .strength_analyzer import PriceStrengthAnalyzer, analyze_price_strength

try:
    from ..kline_fetcher import KLineFetcher
except ImportError:
    import sys
    import os
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from src.qym.trend_analysis.kline_fetcher import KLineFetcher

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """完整分析结果"""
    股票代码: str
    股票名称: str = ""
    分析时间段: str = ""
    识别形态: List[str] = field(default_factory=list)
    形态详情: List[Dict[str, Any]] = field(default_factory=list)
    股价强度: str = ""
    强度详情: Dict[str, Any] = field(default_factory=dict)
    当前风险提示: str = ""
    综合评分: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            '股票代码': self.股票代码,
            '股票名称': self.股票名称,
            '分析时间段': self.分析时间段,
            '识别形态': self.识别形态,
            '形态详情': self.形态详情,
            '股价强度': self.股价强度,
            '强度详情': self.强度详情,
            '当前风险提示': self.当前风险提示,
            '综合评分': round(self.综合评分, 2)
        }


class ClassicPatternAnalyzer:
    """经典上涨形态分析器"""

    MIN_DATA_DAYS = 120

    def __init__(self):
        self.fetcher = KLineFetcher()
        self.pattern_detector = BullishPatternDetector()
        self.strength_analyzer = PriceStrengthAnalyzer()

    def analyze(self, stock_code: str, days: int = 120, end_date: Optional[str] = None,
                stock_name: str = "") -> Optional[AnalysisResult]:
        """
        分析单只股票

        Args:
            stock_code: 股票代码
            days: 分析天数，默认120天
            end_date: 结束日期
            stock_name: 股票名称

        Returns:
            AnalysisResult 或 None
        """
        kline_data = self.fetcher.fetch_kline_data(stock_code, days, end_date)

        if not kline_data or len(kline_data) < self.MIN_DATA_DAYS:
            logger.warning(f"{stock_code} 数据不足，至少需要{self.MIN_DATA_DAYS}个交易日")
            return None

        df = self.pattern_detector._prepare_dataframe(kline_data)
        if df is None:
            return None

        patterns = self.pattern_detector.detect_all_patterns(df)

        if not patterns:
            return None

        strength = self.strength_analyzer.analyze(kline_data)

        start_date = df['date'].iloc[0].strftime('%Y-%m-%d')
        end_date_str = df['date'].iloc[-1].strftime('%Y-%m-%d')

        pattern_names = [p.pattern_name for p in patterns]
        pattern_details = [p.to_dict() for p in patterns]

        strength_rating = strength.rating if strength else "未知"
        strength_details = strength.to_dict() if strength else {}

        risk_warnings = []
        for p in patterns:
            if p.risk_warning:
                risk_warnings.append(p.risk_warning)
        if strength and strength.risk_warning:
            risk_warnings.append(strength.risk_warning)

        risk_warning = "；".join(risk_warnings) if risk_warnings else "暂无明显风险"

        pattern_scores = [p.confidence for p in patterns]
        avg_pattern_score = sum(pattern_scores) / len(pattern_scores) if pattern_scores else 0

        strength_score = strength.details.get('强度评分', 50) if strength else 50

        overall_score = avg_pattern_score * 0.6 + strength_score * 0.4

        result =  AnalysisResult(
            股票代码=stock_code,
            股票名称=stock_name,
            分析时间段=f"{start_date} ~ {end_date_str}",
            识别形态=pattern_names,
            形态详情=pattern_details,
            股价强度=strength_rating,
            强度详情=strength_details,
            当前风险提示=risk_warning,
            综合评分=overall_score
        )

        return result

    def analyze_multiple(self, stock_codes: List[str], days: int = 120,
                         end_date: Optional[str] = None,
                         stock_names: Optional[Dict[str, str]] = None) -> List[AnalysisResult]:
        """
        批量分析多只股票

        Args:
            stock_codes: 股票代码列表
            days: 分析天数
            end_date: 结束日期
            stock_names: 股票名称映射字典

        Returns:
            分析结果列表
        """
        results = []
        stock_names = stock_names or {}

        count = 0
        for code in stock_codes:
            name = stock_names.get(code, "")
            result = self.analyze(code, days, end_date, name)
            count = count+1
            logger.info(f"已完成{len(stock_codes)}/{count}")
            if result:
                logger.info(f"符合形态:{result.to_dict()}")
                results.append(result)

        return results


def analyze_stock(stock_code: str, days: int = 120, end_date: Optional[str] = None,
                  stock_name: str = "") -> Optional[Dict[str, Any]]:
    """
    便捷函数：分析单只股票

    Args:
        stock_code: 股票代码
        days: 分析天数
        end_date: 结束日期
        stock_name: 股票名称

    Returns:
        分析结果字典或None
    """
    analyzer = ClassicPatternAnalyzer()
    result = analyzer.analyze(stock_code, days, end_date, stock_name)
    return result.to_dict() if result else None


def analyze_stocks(stock_codes: List[str], days: int = 120,
                   end_date: Optional[str] = None,
                   stock_names: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """
    便捷函数：批量分析多只股票

    Args:
        stock_codes: 股票代码列表
        days: 分析天数
        end_date: 结束日期
        stock_names: 股票名称映射字典

    Returns:
        分析结果列表
    """
    analyzer = ClassicPatternAnalyzer()
    results = analyzer.analyze_multiple(stock_codes, days, end_date, stock_names)
    return [r.to_dict() for r in results]
