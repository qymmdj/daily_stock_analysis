# -*- coding: utf-8 -*-
"""
经典上涨形态识别器

识别4种经典上涨形态：
1. 均线多头排列 - MA5 > MA10 > MA20 > MA60，股价在MA5之上
2. 上升通道（旗形）- 低点抬高、高点抬高、量价配合
3. 首次回踩重要均线 - 上涨后缩量回调至MA20/MA60获支撑
4. 圆弧底/杯柄形态 - U型底部、右侧放量、突破颈线
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


class PatternType(Enum):
    """形态类型枚举"""
    MA_BULLISH_ALIGNMENT = "均线多头排列"
    ASCENDING_CHANNEL = "上升通道"
    MA_PULLBACK = "首次回踩重要均线"
    ROUNDING_BOTTOM = "圆弧底/杯柄形态"
    UNKNOWN = "未知形态"


@dataclass
class PatternResult:
    """形态识别结果"""
    pattern_type: PatternType
    pattern_name: str
    confidence: float
    description: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    key_points: Dict[str, Any] = field(default_factory=dict)
    risk_warning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            '形态名称': self.pattern_name,
            '置信度': round(self.confidence, 2),
            '形态描述': self.description,
            '开始日期': self.start_date,
            '结束日期': self.end_date,
            '关键点位': self.key_points,
            '风险提示': self.risk_warning
        }


class BullishPatternDetector:
    """经典上涨形态检测器"""

    MIN_DATA_DAYS = 120

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

        if 'ma5' not in df.columns:
            df['ma5'] = df['close'].rolling(window=5).mean()
        if 'ma10' not in df.columns:
            df['ma10'] = df['close'].rolling(window=10).mean()
        if 'ma20' not in df.columns:
            df['ma20'] = df['close'].rolling(window=20).mean()
        if 'ma60' not in df.columns:
            df['ma60'] = df['close'].rolling(window=60).mean()

        df['vol_ma5'] = df['volume'].rolling(window=5).mean()
        df['vol_ma20'] = df['volume'].rolling(window=20).mean()

        return df

    def detect_ma_bullish_alignment(self, df: pd.DataFrame) -> Optional[PatternResult]:
        """
        检测均线多头排列

        条件：
        1. MA5 > MA10 > MA20 > MA60
        2. 股价在MA5之上
        3. MA5、MA10、MA20均线呈发散向上趋势（斜率>0）
        """
        n = len(df)
        last = df.iloc[-1]

        if pd.isna(last['ma60']):
            return None

        if not (last['ma5'] > last['ma10'] > last['ma20'] > last['ma60']):
            return None

        if last['close'] < last['ma5']:
            return None

        recent_5 = df.iloc[-5:]
        ma5_slope = (recent_5['ma5'].iloc[-1] - recent_5['ma5'].iloc[0]) / recent_5['ma5'].iloc[0] * 100
        ma10_slope = (recent_5['ma10'].iloc[-1] - recent_5['ma10'].iloc[0]) / recent_5['ma10'].iloc[0] * 100
        ma20_slope = (recent_5['ma20'].iloc[-1] - recent_5['ma20'].iloc[0]) / recent_5['ma20'].iloc[0] * 100

        if ma5_slope <= 0 or ma10_slope <= 0 or ma20_slope <= 0:
            return None

        confidence = 60
        if ma5_slope > 2:
            confidence += 10
        if ma10_slope > 1.5:
            confidence += 10
        if ma20_slope > 1:
            confidence += 10

        recent_20 = df.iloc[-20:]
        up_days = sum(1 for i in range(1, len(recent_20)) if recent_20['close'].iloc[i] > recent_20['close'].iloc[i-1])
        if up_days >= 12:
            confidence += 10

        confidence = min(100, confidence)

        bias_ma20 = (last['close'] - last['ma20']) / last['ma20'] * 100
        risk_warning = ""
        if bias_ma20 > 15:
            risk_warning = f"股价偏离MA20达{bias_ma20:.1f}%，严重超买，注意回调风险"
            confidence = max(30, confidence - 20)
        elif bias_ma20 > 10:
            risk_warning = f"股价偏离MA20达{bias_ma20:.1f}%，接近超买区域，注意回调风险"
            confidence = max(40, confidence - 10)
        elif bias_ma20 > 8:
            risk_warning = f"股价偏离MA20达{bias_ma20:.1f}%，需关注回调风险"

        return PatternResult(
            pattern_type=PatternType.MA_BULLISH_ALIGNMENT,
            pattern_name="均线多头排列",
            confidence=confidence,
            description=f"5日、10日、20日、60日均线呈多头排列，股价沿5日线上方运行。MA5斜率{ma5_slope:.2f}%，MA10斜率{ma10_slope:.2f}%，MA20斜率{ma20_slope:.2f}%，量价配合良好。",
            start_date=df['date'].iloc[-20].strftime('%Y-%m-%d'),
            end_date=df['date'].iloc[-1].strftime('%Y-%m-%d'),
            key_points={
                'MA5': round(last['ma5'], 2),
                'MA10': round(last['ma10'], 2),
                'MA20': round(last['ma20'], 2),
                'MA60': round(last['ma60'], 2),
                '当前价': round(last['close'], 2),
                'MA5斜率': round(ma5_slope, 2),
                'MA10斜率': round(ma10_slope, 2),
                'MA20斜率': round(ma20_slope, 2),
                '近20日上涨天数': up_days
            },
            risk_warning=risk_warning
        )

    def detect_ascending_channel(self, df: pd.DataFrame) -> Optional[PatternResult]:
        """
        检测上升通道（旗形）

        条件：
        1. 过去N日（如20日）内，每个低点都高于前一个低点
        2. 每个高点也高于前一个高点
        3. 回调时成交量萎缩，上涨时成交量温和放大
        """
        n = len(df)
        lookback = 20
        recent = df.iloc[-lookback:].copy()

        lows = recent['low'].values
        highs = recent['high'].values
        closes = recent['close'].values
        volumes = recent['volume'].values

        low_points = []
        high_points = []
        for i in range(1, len(lows) - 1):
            if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                low_points.append((i, lows[i]))
            if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                high_points.append((i, highs[i]))

        if len(low_points) < 2 or len(high_points) < 2:
            return None

        higher_lows = sum(1 for i in range(1, len(low_points)) if low_points[i][1] > low_points[i-1][1])
        higher_highs = sum(1 for i in range(1, len(high_points)) if high_points[i][1] > high_points[i-1][1])

        if higher_lows < len(low_points) * 0.6 or higher_highs < len(high_points) * 0.6:
            return None

        up_days_idx = [i for i in range(1, len(closes)) if closes[i] > closes[i-1]]
        down_days_idx = [i for i in range(1, len(closes)) if closes[i] < closes[i-1]]

        if not up_days_idx or not down_days_idx:
            return None

        avg_up_vol = np.mean([volumes[i] for i in up_days_idx]) if up_days_idx else 0
        avg_down_vol = np.mean([volumes[i] for i in down_days_idx]) if down_days_idx else 0

        vol_ratio = avg_up_vol / avg_down_vol if avg_down_vol > 0 else 0

        if vol_ratio < 1.0:
            return None

        confidence = 50
        if higher_lows == len(low_points) - 1:
            confidence += 15
        else:
            confidence += higher_lows * 3

        if higher_highs == len(high_points) - 1:
            confidence += 15
        else:
            confidence += higher_highs * 3

        if 1.2 <= vol_ratio <= 2.0:
            confidence += 10
        elif vol_ratio > 2.0:
            confidence += 5

        confidence = min(100, confidence)

        trend_start = recent['close'].iloc[0]
        trend_end = recent['close'].iloc[-1]
        trend_change = (trend_end - trend_start) / trend_start * 100

        risk_warning = ""
        if trend_change > 25:
            risk_warning = f"近{lookback}日涨幅已达{trend_change:.1f}%，注意追高风险"
            confidence = max(40, confidence - 10)

        return PatternResult(
            pattern_type=PatternType.ASCENDING_CHANNEL,
            pattern_name="上升通道",
            confidence=confidence,
            description=f"过去{lookback}日形成上升通道，低点逐步抬高({higher_lows}次确认)，高点逐步抬高({higher_highs}次确认)，上涨均量/下跌均量比{vol_ratio:.2f}，量价配合良好。",
            start_date=recent['date'].iloc[0].strftime('%Y-%m-%d'),
            end_date=recent['date'].iloc[-1].strftime('%Y-%m-%d'),
            key_points={
                '分析周期': lookback,
                '低点抬高次数': higher_lows,
                '高点抬高次数': higher_highs,
                '量价比': round(vol_ratio, 2),
                '区间涨幅': round(trend_change, 2),
                '低点数量': len(low_points),
                '高点数量': len(high_points)
            },
            risk_warning=risk_warning
        )

    def detect_ma_pullback(self, df: pd.DataFrame) -> Optional[PatternResult]:
        """
        检测首次回踩重要均线

        条件：
        1. 股价经历一波上涨（如20日内涨幅>15%）
        2. 随后缩量回调至MA20或MA60附近
        3. 获得支撑（收盘价≥均线且下影线较长）
        4. 回调期间成交量明显低于上涨期间
        """
        n = len(df)
        lookback = 60
        recent = df.iloc[-lookback:].copy()

        prices = recent['close'].values
        volumes = recent['volume'].values
        ma20 = recent['ma20'].values
        ma60 = recent['ma60'].values if 'ma60' in recent.columns else None

        peak_idx = np.argmax(prices[:int(lookback * 0.7)])
        peak_price = prices[peak_idx]

        trough_before_peak = np.min(prices[:peak_idx + 1])
        rise_amplitude = (peak_price - trough_before_peak) / trough_before_peak * 100

        if rise_amplitude < 10:
            return None

        pullback_start = peak_idx
        pullback_end = lookback - 1
        pullback_amplitude = (prices[pullback_end] - peak_price) / peak_price * 100

        if pullback_amplitude > -3:
            return None

        rise_volumes = volumes[:peak_idx + 1]
        pullback_volumes = volumes[peak_idx + 1:]

        avg_rise_vol = np.mean(rise_volumes) if len(rise_volumes) > 0 else 0
        avg_pullback_vol = np.mean(pullback_volumes) if len(pullback_volumes) > 0 else 0

        vol_shrink_ratio = avg_pullback_vol / avg_rise_vol if avg_rise_vol > 0 else 1

        if vol_shrink_ratio > 0.8:
            return None

        last = recent.iloc[-1]
        last_close = last['close']
        last_low = last['low']
        last_high = last['high']
        last_ma20 = last['ma20']
        last_ma60 = last['ma60'] if 'ma60' in last else None

        support_ma = None
        support_level = None
        distance_to_ma20 = abs(last_close - last_ma20) / last_ma20 * 100
        distance_to_ma60 = abs(last_close - last_ma60) / last_ma60 * 100 if last_ma60 and not pd.isna(last_ma60) else 100

        if distance_to_ma20 <= 3:
            support_ma = 'MA20'
            support_level = last_ma20
        elif last_ma60 and not pd.isna(last_ma60) and distance_to_ma60 <= 3:
            support_ma = 'MA60'
            support_level = last_ma60

        if support_ma is None:
            return None

        lower_shadow = last_close - last_low
        body = abs(last_close - last['open'])
        upper_shadow = last_high - max(last_close, last['open'])

        has_support = False
        if last_close >= support_level:
            has_support = True
        if lower_shadow > body * 0.5 and last_low <= support_level * 1.02:
            has_support = True

        if not has_support:
            return None

        confidence = 50

        if vol_shrink_ratio < 0.5:
            confidence += 20
        elif vol_shrink_ratio < 0.7:
            confidence += 10

        if rise_amplitude > 20:
            confidence += 10

        if lower_shadow > body:
            confidence += 10

        if support_ma == 'MA20':
            confidence += 5
        elif support_ma == 'MA60':
            confidence += 10

        confidence = min(100, confidence)

        risk_warning = ""
        if pullback_amplitude < -15:
            risk_warning = f"回调幅度较大({abs(pullback_amplitude):.1f}%)，需确认支撑有效性"
            confidence = max(40, confidence - 10)

        return PatternResult(
            pattern_type=PatternType.MA_PULLBACK,
            pattern_name="首次回踩重要均线",
            confidence=confidence,
            description=f"股价前期上涨{rise_amplitude:.1f}%后缩量回调，成交量萎缩至上涨期的{vol_shrink_ratio:.1%}，当前回踩{support_ma}附近获得支撑，下影线较长显示支撑有效。",
            start_date=recent['date'].iloc[peak_idx].strftime('%Y-%m-%d'),
            end_date=recent['date'].iloc[-1].strftime('%Y-%m-%d'),
            key_points={
                '前期涨幅': round(rise_amplitude, 2),
                '回调幅度': round(abs(pullback_amplitude), 2),
                '支撑均线': support_ma,
                '均线价位': round(support_level, 2),
                '当前价位': round(last_close, 2),
                '成交量萎缩比': round(vol_shrink_ratio, 2),
                '距均线距离': round(distance_to_ma20 if support_ma == 'MA20' else distance_to_ma60, 2)
            },
            risk_warning=risk_warning
        )

    def detect_rounding_bottom(self, df: pd.DataFrame) -> Optional[PatternResult]:
        """
        检测圆弧底/杯柄形态

        条件：
        1. 过去60日内，股价先缓慢下跌后缓慢上涨，形成U型底部
        2. 右侧成交量较左侧明显放大
        3. 当前股价已突破底部区域的高点（或接近突破）
        """
        n = len(df)
        lookback = 60
        recent = df.iloc[-lookback:].copy()

        prices = recent['close'].values
        volumes = recent['volume'].values
        dates = recent['date'].values

        bottom_idx = np.argmin(prices)
        bottom_price = prices[bottom_idx]

        left_start = prices[0]
        right_end = prices[-1]

        if bottom_idx < 5 or bottom_idx > lookback - 5:
            return None

        left_prices = prices[:bottom_idx + 1]
        right_prices = prices[bottom_idx:]

        left_decline = (left_start - bottom_price) / left_start * 100
        right_rise = (right_end - bottom_price) / bottom_price * 100

        if left_decline < 10 or right_rise < 5:
            return None

        left_volumes = volumes[:bottom_idx + 1]
        right_volumes = volumes[bottom_idx:]

        avg_left_vol = np.mean(left_volumes)
        avg_right_vol = np.mean(right_volumes)

        vol_ratio = avg_right_vol / avg_left_vol if avg_left_vol > 0 else 1

        if vol_ratio < 1.2:
            return None

        neckline = max(left_start, prices[bottom_idx:bottom_idx + 10].max() if bottom_idx + 10 < lookback else left_start)

        current_price = prices[-1]
        breakthrough = (current_price - neckline) / neckline * 100

        is_breakthrough = current_price >= neckline * 0.98

        if not is_breakthrough:
            return None

        confidence = 50

        if vol_ratio > 1.5:
            confidence += 15
        elif vol_ratio > 1.3:
            confidence += 10

        if breakthrough > 3:
            confidence += 15
        elif breakthrough > 0:
            confidence += 10
        elif breakthrough > -2:
            confidence += 5

        left_days = bottom_idx
        right_days = lookback - bottom_idx
        symmetry = 1 - abs(left_days - right_days) / lookback
        confidence += symmetry * 10

        confidence = min(100, confidence)

        risk_warning = ""
        if breakthrough < 0:
            risk_warning = f"尚未正式突破颈线，距颈线{abs(breakthrough):.1f}%，需观察突破确认"
            confidence = max(40, confidence - 10)

        return PatternResult(
            pattern_type=PatternType.ROUNDING_BOTTOM,
            pattern_name="圆弧底/杯柄形态",
            confidence=confidence,
            description=f"过去{lookback}日形成圆弧底形态，左侧下跌{left_decline:.1f}%，右侧上涨{right_rise:.1f}%，右侧成交量较左侧放大{vol_ratio:.1f}倍，{'已突破' if breakthrough >= 0 else '接近突破'}颈线位置。",
            start_date=recent['date'].iloc[0].strftime('%Y-%m-%d'),
            end_date=recent['date'].iloc[-1].strftime('%Y-%m-%d'),
            key_points={
                '底部价位': round(bottom_price, 2),
                '底部日期': recent['date'].iloc[bottom_idx].strftime('%Y-%m-%d'),
                '颈线价位': round(neckline, 2),
                '当前价位': round(current_price, 2),
                '左侧跌幅': round(left_decline, 2),
                '右侧涨幅': round(right_rise, 2),
                '右侧放量比': round(vol_ratio, 2),
                '突破幅度': round(breakthrough, 2)
            },
            risk_warning=risk_warning
        )

    def detect_all_patterns(self, df: pd.DataFrame) -> List[PatternResult]:
        """检测所有形态"""
        patterns = []

        result = self.detect_ma_bullish_alignment(df)
        if result:
            patterns.append(result)

        result = self.detect_ascending_channel(df)
        if result:
            patterns.append(result)

        result = self.detect_ma_pullback(df)
        if result:
            patterns.append(result)

        result = self.detect_rounding_bottom(df)
        if result:
            patterns.append(result)

        return patterns


def detect_bullish_patterns(kline_data: List[Dict]) -> List[Dict]:
    """
    便捷函数：检测经典上涨形态

    Args:
        kline_data: K线数据列表

    Returns:
        检测到的形态列表（字典格式）
    """
    detector = BullishPatternDetector()
    df = detector._prepare_dataframe(kline_data)

    if df is None:
        return []

    patterns = detector.detect_all_patterns(df)
    return [p.to_dict() for p in patterns]
