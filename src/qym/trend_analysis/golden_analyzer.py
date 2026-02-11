# -*- coding: utf-8 -*-
"""
===================================
形态识别分析器 - 识别黄金坑/恐慌性洗盘形态
===================================

主要功能：
1. 识别黄金坑形态（横盘后突然下跌再暴涨）
2. 识别恐慌性洗盘形态（快速下跌洗盘后快速拉升）
3. 提供买点信号和置信度评分
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class PatternType(Enum):
    """形态类型枚举"""
    GOLDEN_PIT = "黄金坑"          # 黄金坑形态
    PANIC_WASH = "恐慌性洗盘"      # 恐慌性洗盘形态
    UNKNOWN = "未知形态"


class PatternStage(Enum):
    """形态阶段枚举"""
    BEFORE_DIP = "下跌前"          # 下跌前的横盘/上升阶段
    DIPPING = "下跌中"            # 快速下跌阶段（挖坑）
    BOTTOMING = "坑底震荡"         # 坑底震荡阶段
    REBOUNDING = "反弹中"          # 快速反弹阶段
    BREAKOUT = "突破中"           # 突破前期高点阶段
    COMPLETED = "形态完成"         # 形态已完成


@dataclass
class PatternResult:
    """形态识别结果"""
    code: str                     # 股票代码
    pattern_type: PatternType     # 形态类型
    confidence: float             # 置信度 0-100

    # 关键点位
    start_date: str              # 形态开始日期（下跌前阶段开始）
    dip_start_date: str          # 下跌开始日期
    bottom_start_date: str       # 坑底开始日期
    rebound_start_date: str      # 反弹开始日期
    breakout_date: Optional[str] # 突破日期（可能尚未突破）

    # 价格关键位
    pre_high: float              # 下跌前的高点
    dip_low: float               # 坑底最低点
    rebound_high: float          # 反弹高点
    current_stage: PatternStage  # 当前阶段

    # 统计信息
    dip_duration: int            # 下跌持续时间（交易日）
    dip_amplitude: float         # 下跌幅度（%）
    rebound_duration: int        # 反弹持续时间（交易日）
    rebound_amplitude: float     # 反弹幅度（%）
    volume_ratio: float          # 下跌/反弹期间成交量比率

    # 信号
    buy_signal: bool             # 是否出现买点信号
    buy_reason: str              # 买点理由
    risk_level: int              # 风险等级 1-5（1最低，5最高）

    # 附加信息
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'code': self.code,
            'pattern_type': self.pattern_type.value,
            'confidence': round(self.confidence, 2),
            'start_date': self.start_date,
            'dip_start_date': self.dip_start_date,
            'bottom_start_date': self.bottom_start_date,
            'rebound_start_date': self.rebound_start_date,
            'breakout_date': self.breakout_date,
            'pre_high': round(self.pre_high, 4),
            'dip_low': round(self.dip_low, 4),
            'rebound_high': round(self.rebound_high, 4),
            'current_stage': self.current_stage.value,
            'dip_duration': self.dip_duration,
            'dip_amplitude': round(self.dip_amplitude, 2),
            'rebound_duration': self.rebound_duration,
            'rebound_amplitude': round(self.rebound_amplitude, 2),
            'volume_ratio': round(self.volume_ratio, 2),
            'buy_signal': self.buy_signal,
            'buy_reason': self.buy_reason,
            'risk_level': self.risk_level,
            **self.metadata
        }


class PatternAnalyzer:
    """
    形态识别分析器

    核心算法：识别黄金坑和恐慌性洗盘形态
    黄金坑特征：
    1. 前期：上升趋势或横盘整理
    2. 挖坑：突然快速下跌（10%-30%）
    3. 坑底：低位震荡，成交量萎缩
    4. 反弹：快速反弹，收复失地
    5. 突破：突破前期高点

    恐慌性洗盘特征：
    1. 下跌更猛烈，时间更短
    2. 成交量可能放大（恐慌抛售）
    3. 反弹更迅速
    """

    # 形态识别参数
    PRE_TREND_DAYS = 20           # 前期趋势分析天数
    DIP_MIN_AMPLITUDE = 5.0       # 最小下跌幅度（%）
    DIP_MAX_AMPLITUDE = 35.0      # 最大下跌幅度（%）
    DIP_MIN_DAYS = 2              # 最小下跌天数
    DIP_MAX_DAYS = 15             # 最大下跌天数
    BOTTOM_MIN_DAYS = 3           # 最小坑底震荡天数
    BOTTOM_MAX_DAYS = 20          # 最大坑底震荡天数
    REBOUND_MIN_AMPLITUDE = 10.0  # 最小反弹幅度（%）
    REBOUND_MIN_DAYS = 3          # 最小反弹天数
    VOLUME_SHRINK_RATIO = 0.7     # 缩量阈值（相对于前期均量）
    VOLUME_EXPAND_RATIO = 1.5     # 放量阈值

    # 趋势判断参数
    TREND_SLOPE_THRESHOLD = 0.001  # 趋势斜率阈值（每日涨幅）
    CONSOLIDATION_RANGE = 0.05     # 横盘震荡幅度（5%）

    def __init__(self):
        """初始化分析器"""
        pass

    def detect_golden_pit(self, df: pd.DataFrame, code: str) -> Optional[PatternResult]:
        """
        识别黄金坑形态

        Args:
            df: 包含OHLCV数据的DataFrame，必须有'date', 'open', 'high', 'low', 'close', 'volume'列
            code: 股票代码

        Returns:
            PatternResult 或 None（未识别到形态）
        """
        if df is None or df.empty or len(df) < 60:
            logger.warning(f"{code} 数据不足，至少需要60个交易日数据")
            return None

        # 确保数据按日期排序
        df = df.sort_values('date').reset_index(drop=True)

        # 计算技术指标
        df = self._calculate_indicators(df)

        # 寻找潜在的形态
        patterns = self._find_potential_patterns(df, code)

        if not patterns:
            return None

        # 选择置信度最高的形态
        best_pattern = max(patterns, key=lambda x: x.confidence)
        return best_pattern

    def detect_panic_wash(self, df: pd.DataFrame, code: str) -> Optional[PatternResult]:
        """
        识别恐慌性洗盘形态

        与黄金坑的主要区别：
        1. 下跌时间更短（通常3-7天）
        2. 下跌幅度可能更大
        3. 成交量可能放大
        4. 反弹更快

        Args:
            df: 包含OHLCV数据的DataFrame
            code: 股票代码

        Returns:
            PatternResult 或 None（未识别到形态）
        """
        # 先使用黄金坑检测，然后调整参数评估
        result = self.detect_golden_pit(df, code)
        if result is None:
            return None

        # 检查是否符合恐慌性洗盘特征
        is_panic_wash = self._check_panic_wash_features(result, df)

        if is_panic_wash:
            result.pattern_type = PatternType.PANIC_WASH
            result.confidence = min(100, result.confidence * 1.1)  # 稍微提高置信度
            return result
        else:
            return None

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        df = df.copy()

        # 计算均线
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        df['MA60'] = df['close'].rolling(window=60).mean()

        # 计算价格变化率
        df['price_change'] = df['close'].pct_change() * 100

        # 计算成交量均线
        df['VOL_MA5'] = df['volume'].rolling(window=5).mean()
        df['VOL_MA10'] = df['volume'].rolling(window=10).mean()

        # 计算量比
        df['volume_ratio'] = df['volume'] / df['VOL_MA5']

        # 计算波动率（ATR近似）
        df['TR'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift()),
                abs(df['low'] - df['close'].shift())
            )
        )
        df['ATR'] = df['TR'].rolling(window=14).mean()

        # 计算RSI
        df = self._calculate_rsi(df)

        return df

    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """计算RSI指标"""
        df = df.copy()

        # 计算价格变化
        delta = df['close'].diff()

        # 分离上涨和下跌
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        # 计算平均涨跌幅
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()

        # 计算RS和RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        # 填充NaN值
        df['RSI'] = rsi.fillna(50)

        return df

    def _find_potential_patterns(self, df: pd.DataFrame, code: str) -> List[PatternResult]:
        """寻找潜在的黄金坑形态"""
        patterns = []
        n = len(df)

        # 从PRE_TREND_DAYS开始分析（确保有足够的历史数据）
        for i in range(self.PRE_TREND_DAYS, n - 10):  # 需要至少10天用于后续分析
            # 检查是否可能为下跌起点
            if self._is_dip_start(df, i):
                # 尝试识别完整形态
                pattern = self._identify_pattern(df, code, i)
                if pattern is not None:
                    patterns.append(pattern)

        return patterns

    def _is_dip_start(self, df: pd.DataFrame, idx: int) -> bool:
        """
        判断是否为下跌起点

        条件：
        1. 前期处于上升趋势或横盘
        2. 出现明显的阴线
        3. 可能伴随放量
        """
        if idx < self.PRE_TREND_DAYS:
            return False

        # 检查前期趋势
        pre_prices = df['close'].iloc[idx-self.PRE_TREND_DAYS:idx].values
        if len(pre_prices) < 10:
            return False

        # 计算前期趋势斜率
        x = np.arange(len(pre_prices))
        slope, _ = np.polyfit(x, pre_prices, 1)
        avg_price = np.mean(pre_prices)
        trend_slope_pct = slope / avg_price if avg_price > 0 else 0

        # 趋势应为上升或平缓（允许小幅下跌）
        if trend_slope_pct < -0.005:  # 前期明显下跌，不符合
            return False

        # 检查当前K线特征
        current = df.iloc[idx]
        prev = df.iloc[idx-1]

        # 检查收盘价是否较前一日下跌
        price_change = (current['close'] - prev['close']) / prev['close'] * 100
        if price_change > -1.5:  # 跌幅小于1.5%，不显著
            return False

        # 检查K线实体（允许小阳线，但要求收盘价下跌）
        body_size = abs(current['close'] - current['open']) / current['open'] * 100
        # 如果阳线实体过大（>3%），可能不是下跌起点
        if current['close'] > current['open'] and body_size > 3.0:
            return False

        # 检查成交量
        vol_ratio = current['volume'] / df['VOL_MA5'].iloc[idx] if df['VOL_MA5'].iloc[idx] > 0 else 1
        # 允许放量或缩量

        return True

    def _identify_pattern(self, df: pd.DataFrame, code: str, dip_start_idx: int) -> Optional[PatternResult]:
        """识别完整形态"""
        n = len(df)

        # 1. 确定下跌阶段
        dip_end_idx = self._find_dip_end(df, dip_start_idx)
        if dip_end_idx is None or dip_end_idx >= n:
            return None

        # 2. 确定坑底阶段
        bottom_start_idx = dip_end_idx + 1
        bottom_end_idx = self._find_bottom_end(df, bottom_start_idx)
        if bottom_end_idx is None or bottom_end_idx >= n:
            return None

        # 3. 确定反弹阶段
        rebound_start_idx = bottom_end_idx + 1
        rebound_end_idx = self._find_rebound_end(df, rebound_start_idx)
        if rebound_end_idx is None or rebound_end_idx >= n:
            # 可能尚未开始反弹或反弹不完整
            rebound_end_idx = n - 1

        # 4. 计算形态特征
        pre_high = df['high'].iloc[dip_start_idx-self.PRE_TREND_DAYS:dip_start_idx].max()
        dip_low = df['low'].iloc[dip_start_idx:dip_end_idx+1].min()

        # 下跌幅度
        dip_start_price = df['close'].iloc[dip_start_idx-1]  # 下跌前一日收盘价
        dip_end_price = df['close'].iloc[dip_end_idx]
        dip_amplitude = (dip_end_price - dip_start_price) / dip_start_price * 100

        # 反弹幅度
        if rebound_end_idx > rebound_start_idx:
            rebound_start_price = df['close'].iloc[rebound_start_idx-1]
            rebound_end_price = df['close'].iloc[rebound_end_idx]
            rebound_amplitude = (rebound_end_price - rebound_start_price) / rebound_start_price * 100
        else:
            rebound_amplitude = 0

        # 检查形态有效性
        if not self._validate_pattern(df, dip_start_idx, dip_end_idx, bottom_end_idx, rebound_end_idx):
            return None

        # 5. 确定当前阶段
        current_idx = n - 1
        current_stage = self._determine_stage(
            current_idx, dip_start_idx, dip_end_idx, bottom_end_idx, rebound_end_idx, df
        )

        # 6. 计算置信度
        confidence = self._calculate_confidence(
            df, dip_start_idx, dip_end_idx, bottom_end_idx, rebound_end_idx,
            dip_amplitude, rebound_amplitude
        )

        # 7. 判断买点
        buy_signal, buy_reason = self._check_buy_signal(
            df, current_idx, dip_start_idx, dip_end_idx, bottom_end_idx, rebound_end_idx,
            dip_amplitude, rebound_amplitude
        )

        # 8. 创建结果对象
        result = PatternResult(
            code=code,
            pattern_type=PatternType.GOLDEN_PIT,
            confidence=confidence,
            start_date=df['date'].iloc[dip_start_idx-self.PRE_TREND_DAYS],
            dip_start_date=df['date'].iloc[dip_start_idx],
            bottom_start_date=df['date'].iloc[bottom_start_idx],
            rebound_start_date=df['date'].iloc[rebound_start_idx] if rebound_start_idx < n else None,
            breakout_date=self._find_breakout_date(df, rebound_end_idx, pre_high),
            pre_high=pre_high,
            dip_low=dip_low,
            rebound_high=df['high'].iloc[rebound_start_idx:rebound_end_idx+1].max() if rebound_end_idx >= rebound_start_idx else dip_low,
            current_stage=current_stage,
            dip_duration=dip_end_idx - dip_start_idx + 1,
            dip_amplitude=abs(dip_amplitude),
            rebound_duration=rebound_end_idx - rebound_start_idx + 1 if rebound_end_idx >= rebound_start_idx else 0,
            rebound_amplitude=rebound_amplitude,
            volume_ratio=self._calculate_volume_ratio(df, dip_start_idx, dip_end_idx, rebound_start_idx, rebound_end_idx),
            buy_signal=buy_signal,
            buy_reason=buy_reason,
            risk_level=self._calculate_risk_level(df, current_idx, dip_amplitude, rebound_amplitude)
        )

        return result

    def _find_dip_end(self, df: pd.DataFrame, start_idx: int) -> Optional[int]:
        """寻找下跌结束点"""
        n = len(df)
        min_price = df['close'].iloc[start_idx]
        min_idx = start_idx

        for i in range(start_idx + 1, min(start_idx + self.DIP_MAX_DAYS + 1, n)):
            current_price = df['close'].iloc[i]

            # 更新最低点
            if current_price < min_price:
                min_price = current_price
                min_idx = i

            # 检查是否出现反弹信号
            if i > start_idx:
                # 连续2根阳线或单根大阳线
                is_bullish = df['close'].iloc[i] > df['open'].iloc[i]
                prev_bullish = df['close'].iloc[i-1] > df['open'].iloc[i-1]

                big_bullish = (df['close'].iloc[i] - df['open'].iloc[i]) / df['open'].iloc[i] * 100 > 3.0

                if (is_bullish and prev_bullish) or big_bullish:
                    # 检查反弹幅度
                    dip_start_price = df['close'].iloc[start_idx-1]
                    current_amplitude = (current_price - dip_start_price) / dip_start_price * 100

                    if current_amplitude < -self.DIP_MIN_AMPLITUDE:
                        return i  # 下跌结束，开始反弹
                    else:
                        continue

        # 如果达到最大下跌天数，返回最低点
        if min_idx > start_idx:
            # 检查跌幅是否足够
            dip_start_price = df['close'].iloc[start_idx-1]
            dip_amplitude = (min_price - dip_start_price) / dip_start_price * 100

            if abs(dip_amplitude) >= self.DIP_MIN_AMPLITUDE:
                return min_idx

        return None

    def _find_bottom_end(self, df: pd.DataFrame, start_idx: int) -> Optional[int]:
        """寻找坑底结束点"""
        n = len(df)
        if start_idx >= n:
            return None

        bottom_low = df['low'].iloc[start_idx]
        bottom_high = df['high'].iloc[start_idx]

        for i in range(start_idx + 1, min(start_idx + self.BOTTOM_MAX_DAYS + 1, n)):
            current_low = df['low'].iloc[i]
            current_high = df['high'].iloc[i]

            # 更新坑底范围
            bottom_low = min(bottom_low, current_low)
            bottom_high = max(bottom_high, current_high)

            # 检查震荡幅度
            if bottom_high > 0:
                consolidation_range = (bottom_high - bottom_low) / bottom_low * 100

                # 如果震荡幅度开始扩大，可能结束坑底
                if consolidation_range > self.CONSOLIDATION_RANGE * 100:  # 转换为百分比
                    # 检查是否出现放量阳线
                    if df['close'].iloc[i] > df['open'].iloc[i] and df['volume'].iloc[i] > df['VOL_MA5'].iloc[i] * 1.2:
                        return i

            # 检查是否出现明显的突破信号
            if i > start_idx + self.BOTTOM_MIN_DAYS:
                # 连续阳线或大阳线突破
                if df['close'].iloc[i] > bottom_high * 1.02:  # 突破坑底高点2%
                    return i

        # 如果达到最大坑底天数，返回最后一天
        if start_idx + self.BOTTOM_MIN_DAYS < n:
            return min(start_idx + self.BOTTOM_MAX_DAYS, n - 1)

        return None

    def _find_rebound_end(self, df: pd.DataFrame, start_idx: int) -> Optional[int]:
        """寻找反弹结束点"""
        n = len(df)
        if start_idx >= n:
            return None

        rebound_high = df['high'].iloc[start_idx]
        rebound_start_price = df['close'].iloc[start_idx-1] if start_idx > 0 else df['close'].iloc[start_idx]

        for i in range(start_idx, min(start_idx + 30, n)):  # 最多看30天
            current_high = df['high'].iloc[i]
            rebound_high = max(rebound_high, current_high)

            # 计算反弹幅度
            rebound_amplitude = (rebound_high - rebound_start_price) / rebound_start_price * 100

            # 检查是否达到最小反弹幅度
            if rebound_amplitude >= self.REBOUND_MIN_AMPLITUDE and i >= start_idx + self.REBOUND_MIN_DAYS - 1:
                # 寻找反弹中的调整
                if i < n - 1:
                    # 检查是否出现连续调整
                    for j in range(i + 1, min(i + 5, n)):
                        if df['close'].iloc[j] < df['close'].iloc[j-1] * 0.98:  # 调整超过2%
                            return j - 1  # 反弹结束于调整前

                return i

        return None

    def _validate_pattern(self, df: pd.DataFrame, dip_start: int, dip_end: int,
                         bottom_end: int, rebound_end: int) -> bool:
        """验证形态有效性"""
        # 检查时间顺序
        if not (dip_start < dip_end <= bottom_end <= rebound_end):
            return False

        # 检查下跌幅度
        dip_start_price = df['close'].iloc[dip_start-1]
        dip_end_price = df['close'].iloc[dip_end]
        dip_amplitude = (dip_end_price - dip_start_price) / dip_start_price * 100

        if abs(dip_amplitude) < self.DIP_MIN_AMPLITUDE or abs(dip_amplitude) > self.DIP_MAX_AMPLITUDE:
            return False

        # 检查下跌持续时间
        dip_duration = dip_end - dip_start + 1
        if dip_duration < self.DIP_MIN_DAYS or dip_duration > self.DIP_MAX_DAYS:
            return False

        # 检查坑底持续时间
        bottom_duration = bottom_end - dip_end
        if bottom_duration < self.BOTTOM_MIN_DAYS or bottom_duration > self.BOTTOM_MAX_DAYS:
            return False

        # 检查反弹幅度（如果已有反弹）
        if rebound_end > bottom_end:
            rebound_start_price = df['close'].iloc[bottom_end]
            rebound_end_price = df['close'].iloc[rebound_end]
            rebound_amplitude = (rebound_end_price - rebound_start_price) / rebound_start_price * 100

            if rebound_amplitude < self.REBOUND_MIN_AMPLITUDE:
                return False

        return True

    def _determine_stage(self, current_idx: int, dip_start: int, dip_end: int,
                        bottom_end: int, rebound_end: int, df: pd.DataFrame) -> PatternStage:
        """确定当前形态阶段"""
        if current_idx < dip_start:
            return PatternStage.BEFORE_DIP
        elif current_idx <= dip_end:
            return PatternStage.DIPPING
        elif current_idx <= bottom_end:
            return PatternStage.BOTTOMING
        elif current_idx <= rebound_end:
            return PatternStage.REBOUNDING
        else:
            # 检查是否突破前期高点
            pre_high = df['high'].iloc[dip_start-self.PRE_TREND_DAYS:dip_start].max()
            current_high = df['high'].iloc[rebound_end:current_idx+1].max()

            if current_high > pre_high:
                return PatternStage.BREAKOUT
            else:
                return PatternStage.REBOUNDING

    def _calculate_confidence(self, df: pd.DataFrame, dip_start: int, dip_end: int,
                            bottom_end: int, rebound_end: int, dip_amplitude: float,
                            rebound_amplitude: float) -> float:
        """计算形态置信度"""
        confidence = 50.0  # 基础置信度

        # 1. 下跌特征（最高30分）
        dip_duration = dip_end - dip_start + 1
        ideal_dip_duration = (self.DIP_MIN_DAYS + self.DIP_MAX_DAYS) / 2

        # 持续时间得分
        duration_diff = abs(dip_duration - ideal_dip_duration)
        duration_score = max(0, 15 - duration_diff * 2)
        confidence += duration_score

        # 幅度得分
        ideal_dip_amplitude = (self.DIP_MIN_AMPLITUDE + self.DIP_MAX_AMPLITUDE) / 2
        amplitude_diff = abs(abs(dip_amplitude) - ideal_dip_amplitude)
        amplitude_score = max(0, 15 - amplitude_diff * 2)
        confidence += amplitude_score

        # 2. 坑底特征（最高20分）
        bottom_duration = bottom_end - dip_end
        ideal_bottom_duration = (self.BOTTOM_MIN_DAYS + self.BOTTOM_MAX_DAYS) / 2

        duration_diff = abs(bottom_duration - ideal_bottom_duration)
        bottom_score = max(0, 20 - duration_diff * 3)
        confidence += bottom_score

        # 3. 反弹特征（最高20分）
        if rebound_end > bottom_end:
            rebound_duration = rebound_end - bottom_end
            if rebound_amplitude > 0:
                # 反弹幅度得分
                rebound_amp_score = min(10, rebound_amplitude / 2)
                confidence += rebound_amp_score

                # 反弹持续时间得分
                if rebound_duration >= self.REBOUND_MIN_DAYS:
                    rebound_dur_score = min(10, 10 - (rebound_duration - self.REBOUND_MIN_DAYS) * 0.5)
                    confidence += rebound_dur_score

        # 4. 成交量特征（最高10分）
        vol_score = self._calculate_volume_score(df, dip_start, dip_end, bottom_end, rebound_end)
        confidence += vol_score

        # 5. 技术指标一致性（最高10分）
        tech_score = self._calculate_technical_score(df, dip_start, dip_end, bottom_end, rebound_end)
        confidence += tech_score

        return min(100, max(0, confidence))

    def _calculate_volume_score(self, df: pd.DataFrame, dip_start: int, dip_end: int,
                               bottom_end: int, rebound_end: int) -> float:
        """计算成交量特征得分"""
        score = 0.0

        # 下跌期间成交量（恐慌性抛售可能放量）
        dip_vol_avg = df['volume'].iloc[dip_start:dip_end+1].mean()
        pre_dip_vol_avg = df['volume'].iloc[dip_start-10:dip_start].mean() if dip_start >= 10 else dip_vol_avg

        if pre_dip_vol_avg > 0:
            dip_vol_ratio = dip_vol_avg / pre_dip_vol_avg

            # 放量下跌得5分，缩量下跌得3分，正常得2分
            if dip_vol_ratio > 1.3:
                score += 5  # 明显放量
            elif dip_vol_ratio < 0.7:
                score += 3  # 明显缩量
            else:
                score += 2  # 正常

        # 坑底期间成交量（应萎缩）
        if bottom_end > dip_end:
            bottom_vol_avg = df['volume'].iloc[dip_end+1:bottom_end+1].mean()
            if dip_vol_avg > 0:
                bottom_vol_ratio = bottom_vol_avg / dip_vol_avg

                # 坑底缩量得5分
                if bottom_vol_ratio < 0.8:
                    score += 5

        # 反弹期间成交量（应放量）
        if rebound_end > bottom_end:
            rebound_vol_avg = df['volume'].iloc[bottom_end+1:rebound_end+1].mean()
            if bottom_vol_avg > 0:
                rebound_vol_ratio = rebound_vol_avg / bottom_vol_avg

                # 反弹放量得5分
                if rebound_vol_ratio > 1.2:
                    score += 5

        return min(10, score)

    def _calculate_technical_score(self, df: pd.DataFrame, dip_start: int, dip_end: int,
                                  bottom_end: int, rebound_end: int) -> float:
        """计算技术指标一致性得分"""
        score = 0.0

        # 检查RSI指标
        if 'RSI' in df.columns:
            # 下跌结束时RSI应处于低位（可能超卖）
            dip_end_rsi = df['RSI'].iloc[dip_end]
            if dip_end_rsi < 30:
                score += 3  # 超卖信号

            # 反弹时RSI应回升
            if rebound_end > bottom_end:
                rebound_end_rsi = df['RSI'].iloc[rebound_end]
                if rebound_end_rsi > 40:
                    score += 3

        # 检查均线排列
        if all(col in df.columns for col in ['MA5', 'MA10', 'MA20']):
            # 反弹时短期均线应开始上穿长期均线
            if rebound_end > bottom_end:
                ma5 = df['MA5'].iloc[rebound_end]
                ma10 = df['MA10'].iloc[rebound_end]

                if ma5 > ma10:
                    score += 2

        return min(10, score)

    def _check_buy_signal(self, df: pd.DataFrame, current_idx: int, dip_start: int, dip_end: int,
                         bottom_end: int, rebound_end: int, dip_amplitude: float,
                         rebound_amplitude: float) -> Tuple[bool, str]:
        """检查买点信号"""
        # 如果当前处于坑底或反弹初期，可能是买点
        current_stage = self._determine_stage(current_idx, dip_start, dip_end, bottom_end, rebound_end, df)

        if current_stage == PatternStage.BOTTOMING:
            # 坑底阶段，寻找缩量企稳信号
            current_data = df.iloc[current_idx]
            prev_data = df.iloc[current_idx-1] if current_idx > 0 else current_data

            # 检查是否缩量
            vol_ratio = current_data['volume'] / current_data['VOL_MA5'] if current_data['VOL_MA5'] > 0 else 1
            if vol_ratio < self.VOLUME_SHRINK_RATIO:
                # 检查是否出现企稳K线（小阳线或十字星）
                body_size = abs(current_data['close'] - current_data['open']) / current_data['open'] * 100
                if body_size < 2.0:  # 小实体
                    return True, "坑底缩量企稳，出现买点"

        elif current_stage == PatternStage.REBOUNDING:
            # 反弹初期，寻找放量突破信号
            if current_idx - bottom_end <= 5:  # 反弹开始5天内
                current_data = df.iloc[current_idx]

                # 检查是否放量上涨
                is_bullish = current_data['close'] > current_data['open']
                vol_ratio = current_data['volume'] / current_data['VOL_MA5'] if current_data['VOL_MA5'] > 0 else 1

                if is_bullish and vol_ratio > self.VOLUME_EXPAND_RATIO:
                    return True, "反弹初期放量上涨，出现买点"

        return False, "尚未出现明确买点"

    def _find_breakout_date(self, df: pd.DataFrame, rebound_end: int, pre_high: float) -> Optional[str]:
        """寻找突破前期高点的日期"""
        n = len(df)

        for i in range(rebound_end + 1, n):
            if df['high'].iloc[i] > pre_high:
                return df['date'].iloc[i]

        return None

    def _calculate_volume_ratio(self, df: pd.DataFrame, dip_start: int, dip_end: int,
                               rebound_start: int, rebound_end: int) -> float:
        """计算成交量比率（反弹期间均量/下跌期间均量）"""
        if rebound_end >= rebound_start:
            dip_vol_avg = df['volume'].iloc[dip_start:dip_end+1].mean()
            rebound_vol_avg = df['volume'].iloc[rebound_start:rebound_end+1].mean()

            if dip_vol_avg > 0:
                return rebound_vol_avg / dip_vol_avg

        return 1.0

    def _calculate_risk_level(self, df: pd.DataFrame, current_idx: int,
                             dip_amplitude: float, rebound_amplitude: float) -> int:
        """计算风险等级"""
        risk = 3  # 中等风险

        # 基于跌幅调整风险
        if abs(dip_amplitude) > 25:
            risk += 1  # 大跌幅，风险较高

        # 基于反弹幅度调整风险
        if rebound_amplitude > 30:
            risk -= 1  # 大幅反弹，风险降低

        # 基于当前价格位置调整风险
        if 'MA20' in df.columns:
            current_price = df['close'].iloc[current_idx]
            ma20 = df['MA20'].iloc[current_idx]

            if current_price < ma20 * 0.9:
                risk += 1  # 远离均线，风险较高
            elif current_price > ma20:
                risk -= 1  # 站上均线，风险降低

        return max(1, min(5, risk))

    def _check_panic_wash_features(self, result: PatternResult, df: pd.DataFrame) -> bool:
        """检查是否符合恐慌性洗盘特征"""
        # 恐慌性洗盘通常特征：
        # 1. 下跌时间更短（3-7天）
        # 2. 下跌可能伴随放量
        # 3. 反弹更快

        if result.dip_duration > 10:  # 下跌时间过长
            return False

        if result.dip_amplitude < 15:  # 跌幅不够大
            return False

        if result.rebound_duration > 0 and result.rebound_amplitude / result.rebound_duration < 2.0:
            # 反弹速度不够快（日均涨幅小于2%）
            return False

        return True


def analyze_pattern(df: pd.DataFrame, code: str) -> Dict[str, Any]:
    """
    便捷函数：分析股票形态

    Args:
        df: 包含OHLCV数据的DataFrame
        code: 股票代码

    Returns:
        包含分析结果的字典
    """
    analyzer = PatternAnalyzer()

    # 先尝试识别恐慌性洗盘
    panic_result = analyzer.detect_panic_wash(df, code)
    if panic_result is not None:
        return panic_result.to_dict()

    # 再尝试识别黄金坑
    golden_result = analyzer.detect_golden_pit(df, code)
    if golden_result is not None:
        return golden_result.to_dict()

    # 未识别到形态
    return {
        'code': code,
        'pattern_type': '无形态',
        'confidence': 0,
        'message': '未识别到黄金坑或恐慌性洗盘形态'
    }


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)

    print("形态识别分析器已准备就绪")
    print("使用方法：")
    print("1. 准备包含'date', 'open', 'high', 'low', 'close', 'volume'列的DataFrame")
    print("2. 调用 analyze_pattern(df, stock_code) 函数")
    print("3. 结果包含形态类型、置信度、关键点位和买点信号")