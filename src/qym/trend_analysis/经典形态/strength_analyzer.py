# -*- coding: utf-8 -*-
"""
股价强度分析模块

基于个股自身趋势的强度分析：
1. 短期强度 - 最近5日涨跌幅 vs 最近20日涨跌幅
2. 中期强度 - 最近20日涨跌幅 vs 最近60日涨跌幅
3. 量价配合度 - 上涨日平均成交量 / 下跌日平均成交量
4. 均线乖离率 - (当前价 - MA20) / MA20 × 100%
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


class StrengthLevel(Enum):
    """强度等级枚举"""
    VERY_STRONG = "极强"
    STRONG = "强"
    NORMAL = "中等"
    WEAK = "弱"
    VERY_WEAK = "极弱"


@dataclass
class StrengthResult:
    """强度分析结果"""
    level: StrengthLevel
    rating: str
    short_term_strength: float
    mid_term_strength: float
    volume_price_ratio: float
    ma_bias: float
    details: Dict[str, Any] = field(default_factory=dict)
    risk_warning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            '强度等级': self.level.value,
            '强度评级': self.rating,
            '短期强度': f"{self.short_term_strength:.1f}%",
            '中期强度': f"{self.mid_term_strength:.1f}%",
            '量价比': round(self.volume_price_ratio, 2),
            'MA20乖离率': f"{self.ma_bias:.1f}%",
            '详细指标': self.details,
            '风险提示': self.risk_warning
        }


class PriceStrengthAnalyzer:
    """股价强度分析器"""

    MIN_DATA_DAYS = 60

    def __init__(self):
        pass

    def _prepare_dataframe(self, kline_data: List[Dict]) -> Optional[pd.DataFrame]:
        """准备数据框"""
        if not kline_data or len(kline_data) < self.MIN_DATA_DAYS:
            return None

        df = pd.DataFrame(kline_data)

        if 'date' not in df.columns and 'tick_at' in df.columns:
            from datetime import datetime
            df['date'] = pd.to_datetime(df['tick_at'].apply(
                lambda x: datetime.fromtimestamp(x if x < 1e10 else x / 1000)
            ))
        elif 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])

        column_mapping = {
            'open_px': 'open',
            'close_px': 'close',
            'high_px': 'high',
            'low_px': 'low',
            'turnover_volume': 'volume',
            'turnover_value': 'amount',
            'turnover_ratio': 'turnover_rate'
        }
        df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})

        df = df.sort_values('date').reset_index(drop=True)

        if 'ma20' not in df.columns:
            df['ma20'] = df['close'].rolling(window=20).mean()
        if 'ma60' not in df.columns:
            df['ma60'] = df['close'].rolling(window=60).mean()

        return df

    def analyze(self, kline_data: List[Dict]) -> Optional[StrengthResult]:
        """
        分析股价强度

        Args:
            kline_data: K线数据列表

        Returns:
            StrengthResult 或 None
        """
        df = self._prepare_dataframe(kline_data)
        if df is None:
            return None

        n = len(df)
        prices = df['close'].values
        volumes = df['volume'].values

        change_5d = (prices[-1] - prices[-6]) / prices[-6] * 100 if n >= 6 else 0
        change_20d = (prices[-1] - prices[-21]) / prices[-21] * 100 if n >= 21 else 0
        change_60d = (prices[-1] - prices[-61]) / prices[-61] * 100 if n >= 61 else 0

        short_term_strength = change_5d - change_20d / 4

        mid_term_strength = change_20d - change_60d / 3

        recent_20 = df.iloc[-20:]
        up_days_idx = [i for i in range(1, 20) if recent_20['close'].iloc[i] > recent_20['close'].iloc[i-1]]
        down_days_idx = [i for i in range(1, 20) if recent_20['close'].iloc[i] < recent_20['close'].iloc[i-1]]

        vol_20 = recent_20['volume'].values
        avg_up_vol = np.mean([vol_20[i] for i in up_days_idx]) if up_days_idx else 0
        avg_down_vol = np.mean([vol_20[i] for i in down_days_idx]) if down_days_idx else 0

        volume_price_ratio = avg_up_vol / avg_down_vol if avg_down_vol > 0 else (2.0 if avg_up_vol > 0 else 1.0)

        last = df.iloc[-1]
        ma20 = last['ma20']
        current_price = last['close']
        ma_bias = (current_price - ma20) / ma20 * 100 if ma20 and not pd.isna(ma20) else 0

        score = 0

        if short_term_strength > 5:
            score += 25
        elif short_term_strength > 2:
            score += 20
        elif short_term_strength > 0:
            score += 15
        elif short_term_strength > -2:
            score += 10
        else:
            score += 5

        if mid_term_strength > 10:
            score += 25
        elif mid_term_strength > 5:
            score += 20
        elif mid_term_strength > 0:
            score += 15
        elif mid_term_strength > -5:
            score += 10
        else:
            score += 5

        if 1.2 <= volume_price_ratio <= 2.0:
            score += 25
        elif volume_price_ratio > 2.0:
            score += 15
        elif volume_price_ratio >= 1.0:
            score += 20
        else:
            score += 10

        if 0 <= ma_bias <= 8:
            score += 25
        elif 8 < ma_bias <= 12:
            score += 15
        elif ma_bias > 12:
            score += 5
        elif -5 <= ma_bias < 0:
            score += 20
        else:
            score += 10

        if score >= 85:
            level = StrengthLevel.VERY_STRONG
        elif score >= 70:
            level = StrengthLevel.STRONG
        elif score >= 50:
            level = StrengthLevel.NORMAL
        elif score >= 35:
            level = StrengthLevel.WEAK
        else:
            level = StrengthLevel.VERY_WEAK

        rating = f"{level.value}（短期强度{short_term_strength:.1f}%，中期强度{mid_term_strength:.1f}%，量价比{volume_price_ratio:.2f}）"

        risk_warning = ""
        if ma_bias > 15:
            risk_warning = f"股价偏离MA20达{ma_bias:.1f}%，严重超买，注意回调风险"
        elif ma_bias > 10:
            risk_warning = f"股价偏离MA20达{ma_bias:.1f}%，接近超买区域，注意回调风险"
        elif ma_bias > 8:
            risk_warning = f"股价偏离MA20达{ma_bias:.1f}%，需关注回调风险"
        elif ma_bias < -10:
            risk_warning = f"股价偏离MA20达{ma_bias:.1f}%，严重超卖，可能存在反弹机会"

        details = {
            '近5日涨跌幅': round(change_5d, 2),
            '近20日涨跌幅': round(change_20d, 2),
            '近60日涨跌幅': round(change_60d, 2),
            '上涨日均量': round(avg_up_vol, 0) if avg_up_vol > 0 else 0,
            '下跌日均量': round(avg_down_vol, 0) if avg_down_vol > 0 else 0,
            '强度评分': score,
            'MA20价位': round(ma20, 2) if ma20 and not pd.isna(ma20) else None,
            '当前价位': round(current_price, 2)
        }

        return StrengthResult(
            level=level,
            rating=rating,
            short_term_strength=short_term_strength,
            mid_term_strength=mid_term_strength,
            volume_price_ratio=volume_price_ratio,
            ma_bias=ma_bias,
            details=details,
            risk_warning=risk_warning
        )


def analyze_price_strength(kline_data: List[Dict]) -> Optional[Dict]:
    """
    便捷函数：分析股价强度

    Args:
        kline_data: K线数据列表

    Returns:
        强度分析结果（字典格式）或 None
    """
    analyzer = PriceStrengthAnalyzer()
    result = analyzer.analyze(kline_data)
    return result.to_dict() if result else None
