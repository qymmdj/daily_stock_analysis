# -*- coding: utf-8 -*-
"""
MACD 底背离检测器

算法说明：
1、从最新日 K 线开始往前查找，找到连续下跌超过 3 天小于 5 天且跌幅高于 5% 小于 10% 的日期 A
2、从日期 A 往后查找，找到第一个收阳线的日期 A1，计算 A1 到最新日 K 线的累计涨幅在 1% 到 10% 之间
3、在从日期 A 往前查找，找到第一个收阳线的日期 B
4、在从日期 B 往前查找，找到连续下跌超过 3 天小于 5 天且跌幅高于 15% 小于 25% 的日期 C
5、从日期 C 往后查找，找到第一个收阳线的日期 C1，计算 C1 到 B 时间段日 K 线的累计涨幅在 3% 到 12% 之间
6、计算两个下跌阶段 A 和下跌阶段 C MACD，判断是否明显价格和 MACD 背离 阶段 A 出现背离
7、从 C 继续往前查找首次出现阳线的日期 C2，从 C2 开始往前统计（250 天内）出现涨幅大于 9% 的次数大于等于 3 次
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
import pandas as pd
import numpy as np
import logging

try:
    from ..kline_fetcher import KLineFetcher
    from ..csv_reader import StockLimitupCSVReader
except ImportError:
    import sys
    import os
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from src.qym.trend_analysis.kline_fetcher import KLineFetcher
    from src.qym.trend_analysis.csv_reader import StockLimitupCSVReader

logger = logging.getLogger(__name__)


@dataclass
class DivergenceResult:
    """底背离检测结果"""
    code: str
    divergence_date: str
    is_divergence: bool
    confidence: float = 0.0
    dip_a_start: str = ""
    dip_a_end: str = ""
    dip_c_start: str = ""
    dip_c_end: str = ""
    macd_a_value: float = 0.0
    macd_c_value: float = 0.0
    message: str = ""

    def to_dict(self) -> Dict:
        return {
            'code': self.code,
            'divergence_date': self.divergence_date,
            'is_divergence': self.is_divergence,
            'confidence': round(self.confidence, 2),
            'dip_a_start': self.dip_a_start,
            'dip_a_end': self.dip_a_end,
            'dip_c_start': self.dip_c_start,
            'dip_c_end': self.dip_c_end,
            'macd_a_value': round(self.macd_a_value, 4),
            'macd_c_value': round(self.macd_c_value, 4),
            'message': self.message
        }


class BullMACDDivergenceDetector:
    """MACD 底背离检测器"""

    DIP_A_MIN_DAYS = 3
    DIP_A_MAX_DAYS = 5
    DIP_A_MIN_AMPLITUDE = 5.0
    DIP_A_MAX_AMPLITUDE = 10.0

    DIP_C_MIN_DAYS = 3
    DIP_C_MAX_DAYS = 5
    DIP_C_MIN_AMPLITUDE = 15.0
    DIP_C_MAX_AMPLITUDE = 25.0

    # 步骤 2：A1 到最新的涨幅范围
    A1_TO_LATEST_MIN = -2.0
    A1_TO_LATEST_MAX = 10.0

    # 步骤 5：C1 到 B 的涨幅范围
    C1_TO_B_MIN = 3.0
    C1_TO_B_MAX = 12.0

    def __init__(self):
        self.fetcher = KLineFetcher()

    def _calculate_macd(self, df: pd.DataFrame, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> pd.DataFrame:
        """计算 MACD 指标"""
        df = df.copy()
        df['EMA12'] = df['close'].ewm(span=fast_period, adjust=False).mean()
        df['EMA26'] = df['close'].ewm(span=slow_period, adjust=False).mean()
        df['MACD'] = df['EMA12'] - df['EMA26']
        df['MACD_Signal'] = df['MACD'].ewm(span=signal_period, adjust=False).mean()
        df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
        return df

    def _find_consecutive_dip(self, df: pd.DataFrame, start_idx: int, direction: str,
                               min_days: int, max_days: int, min_amp: float, max_amp: float,
                               verbose: bool = False, label: str = "") -> Optional[Tuple[int, int]]:
        """
        查找连续下跌区间

        Args:
            df: K 线数据
            start_idx: 开始查找的索引
            direction: 'forward' 往后找 (更新日期), 'backward' 往前找 (更早日期)
            min_days: 最小下跌天数
            max_days: 最大下跌天数
            min_amp: 最小跌幅
            max_amp: 最大跌幅
            verbose: 是否打印详细诊断信息
            label: 下跌段标签 (A 或 C)

        Returns:
            (下跌开始索引，下跌结束索引) 或 None
        """
        n = len(df)
        candidates = []

        if direction == 'backward':
            for offset in range(0, min(50, start_idx)):
                check_idx = start_idx - offset
                if check_idx < max_days:
                    continue

                for dip_len in range(min_days, max_days + 1):
                    dip_start = check_idx - dip_len
                    dip_end = check_idx - 1

                    if dip_start < 0:
                        continue

                    is_dip, amplitude = self._check_dip(df, dip_start, dip_end)
                    if is_dip:
                        candidates.append((dip_start, dip_end, amplitude))
                        if min_amp <= abs(amplitude) <= max_amp:
                            return (dip_start, dip_end)
        else:
            for offset in range(0, min(50, n - start_idx)):
                check_idx = start_idx + offset
                if check_idx + max_days >= n:
                    continue

                for dip_len in range(min_days, max_days + 1):
                    dip_start = check_idx
                    dip_end = check_idx + dip_len - 1

                    if dip_end >= n:
                        continue

                    is_dip, amplitude = self._check_dip(df, dip_start, dip_end)
                    if is_dip:
                        candidates.append((dip_start, dip_end, amplitude))
                        if min_amp <= abs(amplitude) <= max_amp:
                            return (dip_start, dip_end)

        if verbose and candidates:
            print(f"\n  [诊断] 下跌段{label}候选区间 (但跌幅不符合条件):")
            for i, (s, e, amp) in enumerate(candidates[:5]):
                print(f"    {i+1}. {df['date'].iloc[s].strftime('%Y-%m-%d')} ~ {df['date'].iloc[e].strftime('%Y-%m-%d')}, 跌幅：{amp:.2f}%")

        return None

    def _check_dip(self, df: pd.DataFrame, start_idx: int, end_idx: int) -> Tuple[bool, float]:
        """
        检查是否为连续下跌

        Returns:
            (是否下跌，跌幅)
        """
        if start_idx < 0 or end_idx >= len(df):
            return False, 0.0

        close_prices = df['close'].iloc[start_idx:end_idx + 1].values

        is_all_down = all(close_prices[i] <= close_prices[i - 1] for i in range(1, len(close_prices)))

        if not is_all_down:
            down_count = sum(1 for i in range(1, len(close_prices)) if close_prices[i] < close_prices[i - 1])
            if down_count < len(close_prices) * 0.6:
                return False, 0.0

        start_price = df['close'].iloc[start_idx - 1] if start_idx > 0 else df['open'].iloc[start_idx]
        end_price = df['close'].iloc[end_idx]
        amplitude = (end_price - start_price) / start_price * 100

        return amplitude < 0, amplitude

    def _find_first_up_day(self, df: pd.DataFrame, start_idx: int, direction: str) -> Optional[int]:
        """
        查找第一个收阳线的日期

        Args:
            df: K 线数据
            start_idx: 开始查找的索引
            direction: 'forward' 往后找，'backward' 往前找

        Returns:
            收阳线日的索引或 None
        """
        n = len(df)

        if direction == 'forward':
            for i in range(start_idx + 1, min(start_idx + 20, n)):
                if df['close'].iloc[i] > df['open'].iloc[i]:
                    return i
        else:
            for i in range(start_idx - 1, max(0, start_idx - 20), -1):
                if i > 0 and df['close'].iloc[i] > df['open'].iloc[i]:
                    return i

        return None

    def _count_large_gains(self, df: pd.DataFrame, start_idx: int, days: int = 250, threshold: float = 9.0) -> int:
        """
        统计从指定日期往前 N 天内涨幅超过阈值的次数

        Args:
            df: K 线数据
            start_idx: 开始统计的索引
            days: 统计天数，默认 250 天
            threshold: 涨幅阈值，默认 9%

        Returns:
            涨幅超过阈值的次数
        """
        count = 0
        end_idx = max(0, start_idx - days)

        for i in range(start_idx, end_idx, -1):
            if i > 0:
                prev_close = df['close'].iloc[i - 1]
                curr_close = df['close'].iloc[i]
                gain = (curr_close - prev_close) / prev_close * 100
                if gain > threshold:
                    count += 1

        return count

    def _calculate_period_change(self, df: pd.DataFrame, start_idx: int, end_idx: int) -> float:
        """计算区间涨跌幅"""
        if start_idx < 0 or end_idx >= len(df) or start_idx > end_idx:
            return 0.0

        start_price = df['close'].iloc[start_idx]
        end_price = df['close'].iloc[end_idx]
        return (end_price - start_price) / start_price * 100

    def _check_macd_divergence(self, df: pd.DataFrame, dip_a_start: int, dip_a_end: int,
                                dip_c_start: int, dip_c_end: int) -> Tuple[bool, float, float, float]:
        """
        计算两个下跌阶段的 MACD 值并比较

        条件：
        A 处的 MACD 值明显大于 C 处的值（如 1.5 倍）

        Returns:
            (是否满足条件，A 区 MACD 值，C 区 MACD 值，置信度)
        """
        macd_a_values = df['MACD_Hist'].iloc[dip_a_start:dip_a_end + 1]
        macd_c_values = df['MACD_Hist'].iloc[dip_c_start:dip_c_end + 1]

        macd_a_value = macd_a_values.min()
        macd_c_value = macd_c_values.min()

        # A 处的值明显大于 C 处的值（如 1.5 倍）
        # 注意：MACD 柱为负值时，绝对值越大表示下跌动能越强
        # 所以当 A 的 MACD 值 > C 的 MACD 值时，说明 A 的下跌动能弱于 C
        is_macd_greater = macd_a_value > macd_c_value * 1.5

        if is_macd_greater:
            macd_diff = abs(macd_a_value - macd_c_value)
            confidence = min(100, 50 + macd_diff * 100)
            return True, macd_a_value, macd_c_value, confidence

        return False, macd_a_value, macd_c_value, 0.0

    def detect(self, stock_code: str, end_date: Optional[str] = None, days: int = 250, verbose: bool = False) -> Optional[DivergenceResult]:
        """
        检测 MACD 底背离

        Args:
            stock_code: 股票代码
            end_date: 结束日期，可选，默认最新日期
            days: K 线天数，默认 250 天
            verbose: 是否打印详细诊断信息

        Returns:
            DivergenceResult 或 None
        """
        raw_data = self.fetcher.fetch_kline_data(stock_code, days, end_date)

        if not raw_data or len(raw_data) < 100:
            logger.warning(f"{stock_code} 数据不足")
            return DivergenceResult(
                code=stock_code,
                divergence_date=end_date or "",
                is_divergence=False,
                message="数据不足，至少需要 100 个交易日"
            )

        df = pd.DataFrame(raw_data)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)

        df = df.rename(columns={
            'open_px': 'open',
            'close_px': 'close',
            'high_px': 'high',
            'low_px': 'low',
            'turnover_volume': 'volume'
        })

        df = self._calculate_macd(df)

        n = len(df)
        latest_idx = n - 1

        if verbose:
            print(f"\n{'='*60}")
            print(f"开始检测 MACD 底背离：{stock_code}")
            print(f"分析日期：{df['date'].iloc[latest_idx].strftime('%Y-%m-%d')}")
            print(f"数据范围：{df['date'].iloc[0].strftime('%Y-%m-%d')} ~ {df['date'].iloc[latest_idx].strftime('%Y-%m-%d')}")
            print(f"{'='*60}")

        dip_a = self._find_consecutive_dip(
            df, latest_idx, 'backward',
            self.DIP_A_MIN_DAYS, self.DIP_A_MAX_DAYS,
            self.DIP_A_MIN_AMPLITUDE, self.DIP_A_MAX_AMPLITUDE,
            verbose=verbose, label="A"
        )

        if not dip_a:
            if verbose:
                print(f"\n[失败] 步骤 1: 未找到符合条件的近期下跌段 A")
                print(f"  条件：连续下跌{self.DIP_A_MIN_DAYS}-{self.DIP_A_MAX_DAYS}天，跌幅{self.DIP_A_MIN_AMPLITUDE}%-{self.DIP_A_MAX_AMPLITUDE}%")
            return DivergenceResult(
                code=stock_code,
                divergence_date=df['date'].iloc[latest_idx].strftime('%Y-%m-%d'),
                is_divergence=False,
                message="未找到符合条件的近期下跌段 A"
            )

        dip_a_start, dip_a_end = dip_a
        if verbose:
            print(f"\n[成功] 步骤 1: 找到下跌段 A")
            print(f"  日期：{df['date'].iloc[dip_a_start].strftime('%Y-%m-%d')} ~ {df['date'].iloc[dip_a_end].strftime('%Y-%m-%d')}")
            print(f"  收盘价：{df['close'].iloc[dip_a_start-1]:.2f} -> {df['close'].iloc[dip_a_end]:.2f}")

        a1_idx = self._find_first_up_day(df, dip_a_end, 'forward')
        if a1_idx is None:
            if verbose:
                print(f"\n[失败] 步骤 2: 未找到下跌段 A 后的收阳线 A1")
            return DivergenceResult(
                code=stock_code,
                divergence_date=df['date'].iloc[latest_idx].strftime('%Y-%m-%d'),
                is_divergence=False,
                message="未找到下跌段 A 后的收阳线 A1"
            )

        if verbose:
            print(f"\n[成功] 步骤 2: 找到收阳线 A1: {df['date'].iloc[a1_idx].strftime('%Y-%m-%d')}")

        change_a1_to_latest = self._calculate_period_change(df, a1_idx, latest_idx)
        if not (self.A1_TO_LATEST_MIN <= change_a1_to_latest <= self.A1_TO_LATEST_MAX):
            if verbose:
                print(f"\n[失败] 步骤 2: A1 到最新涨跌幅{change_a1_to_latest:.2f}%不在{self.A1_TO_LATEST_MIN}%到{self.A1_TO_LATEST_MAX}%范围内")
            return DivergenceResult(
                code=stock_code,
                divergence_date=df['date'].iloc[latest_idx].strftime('%Y-%m-%d'),
                is_divergence=False,
                message=f"A1 到最新涨跌幅{change_a1_to_latest:.2f}%不在{self.A1_TO_LATEST_MIN}%到{self.A1_TO_LATEST_MAX}%范围内"
            )

        if verbose:
            print(f"[成功] 步骤 2: A1 到最新涨跌幅：{change_a1_to_latest:.2f}% (符合条件)")

        b_idx = self._find_first_up_day(df, dip_a_start, 'backward')
        if b_idx is None:
            if verbose:
                print(f"\n[失败] 步骤 3: 未找到下跌段 A 前的收阳线 B")
            return DivergenceResult(
                code=stock_code,
                divergence_date=df['date'].iloc[latest_idx].strftime('%Y-%m-%d'),
                is_divergence=False,
                message="未找到下跌段 A 前的收阳线 B"
            )

        if verbose:
            print(f"\n[成功] 步骤 3: 找到收阳线 B: {df['date'].iloc[b_idx].strftime('%Y-%m-%d')}")

        dip_c = self._find_consecutive_dip(
            df, b_idx, 'backward',
            self.DIP_C_MIN_DAYS, self.DIP_C_MAX_DAYS,
            self.DIP_C_MIN_AMPLITUDE, self.DIP_C_MAX_AMPLITUDE,
            verbose=verbose, label="C"
        )

        if not dip_c:
            if verbose:
                print(f"\n[失败] 步骤 4: 未找到符合条件的早期下跌段 C")
                print(f"  条件：连续下跌{self.DIP_C_MIN_DAYS}-{self.DIP_C_MAX_DAYS}天，跌幅{self.DIP_C_MIN_AMPLITUDE}%-{self.DIP_C_MAX_AMPLITUDE}%")
                print(f"  从日期 {df['date'].iloc[b_idx].strftime('%Y-%m-%d')} 往前查找")
            return DivergenceResult(
                code=stock_code,
                divergence_date=df['date'].iloc[latest_idx].strftime('%Y-%m-%d'),
                is_divergence=False,
                message="未找到符合条件的早期下跌段 C"
            )

        dip_c_start, dip_c_end = dip_c
        if verbose:
            print(f"\n[成功] 步骤 4: 找到下跌段 C")
            print(f"  日期：{df['date'].iloc[dip_c_start].strftime('%Y-%m-%d')} ~ {df['date'].iloc[dip_c_end].strftime('%Y-%m-%d')}")
            print(f"  收盘价：{df['close'].iloc[dip_c_start-1]:.2f} -> {df['close'].iloc[dip_c_end]:.2f}")

        c1_idx = self._find_first_up_day(df, dip_c_end, 'forward')
        if c1_idx is None:
            if verbose:
                print(f"\n[失败] 步骤 5: 未找到下跌段 C 后的收阳线 C1")
            return DivergenceResult(
                code=stock_code,
                divergence_date=df['date'].iloc[latest_idx].strftime('%Y-%m-%d'),
                is_divergence=False,
                message="未找到下跌段 C 后的收阳线 C1"
            )

        if verbose:
            print(f"\n[成功] 步骤 5: 找到收阳线 C1: {df['date'].iloc[c1_idx].strftime('%Y-%m-%d')}")
            print(f"  C1 日期：{df['date'].iloc[c1_idx].strftime('%Y-%m-%d')}, 收盘价：{df['close'].iloc[c1_idx]:.2f}")
            print(f"  B 日期：{df['date'].iloc[b_idx].strftime('%Y-%m-%d')}, 收盘价：{df['close'].iloc[b_idx]:.2f}")

        change_c1_to_b = self._calculate_period_change(df, c1_idx, b_idx)
        if not (self.C1_TO_B_MIN <= change_c1_to_b <= self.C1_TO_B_MAX):
            if verbose:
                print(f"\n[失败] 步骤 5: C1 到 B 涨跌幅{change_c1_to_b:.2f}%不在{self.C1_TO_B_MIN}%到{self.C1_TO_B_MAX}%范围内")
            return DivergenceResult(
                code=stock_code,
                divergence_date=df['date'].iloc[latest_idx].strftime('%Y-%m-%d'),
                is_divergence=False,
                message=f"C1 到 B 涨跌幅{change_c1_to_b:.2f}%不在{self.C1_TO_B_MIN}%到{self.C1_TO_B_MAX}%范围内"
            )

        if verbose:
            print(f"[成功] 步骤 5: C1 到 B 涨跌幅：{change_c1_to_b:.2f}% (符合条件)")

        is_divergence, macd_a_value, macd_c_value, confidence = self._check_macd_divergence(
            df, dip_a_start, dip_a_end, dip_c_start, dip_c_end
        )

        if verbose:
            print(f"\n[步骤 6] 计算两个下跌阶段 MACD:")
            print(f"  下跌阶段 A({df['date'].iloc[dip_a_start].strftime('%Y-%m-%d')}~{df['date'].iloc[dip_a_end].strftime('%Y-%m-%d')}) - MACD 值：{macd_a_value:.4f}")
            print(f"  下跌阶段 C({df['date'].iloc[dip_c_start].strftime('%Y-%m-%d')}~{df['date'].iloc[dip_c_end].strftime('%Y-%m-%d')}) - MACD 值：{macd_c_value:.4f}")
            print(f"  A 处 MACD 值明显大于 C 处 (1.5 倍): {'是' if macd_a_value > macd_c_value * 1.5 else '否'} (A={macd_a_value:.4f} vs C={macd_c_value:.4f})")
            print(f"  阶段 A 出现背离：{'是' if is_divergence else '否'}")

        # 步骤 7: 从 C 继续往前查找首次出现阳线的日期 C2，统计 250 天内涨幅大于 9% 的次数
        c2_idx = self._find_first_up_day(df, dip_c_end, 'forward')
        large_gain_count = 0
        if c2_idx is not None:
            large_gain_count = self._count_large_gains(df, c2_idx, days=250, threshold=9.0)
        
        if verbose:
            if c2_idx is not None:
                print(f"\n[步骤 7] 统计 C2 后 250 天内涨幅大于 9% 的次数:")
                print(f"  C2 日期：{df['date'].iloc[c2_idx].strftime('%Y-%m-%d')}")
                print(f"  涨幅大于 9% 的次数：{large_gain_count}")
            else:
                print(f"\n[步骤 7] 未找到 C2（C 后的第一个收阳线）")

        # 综合判断：步骤 6 背离条件 + 步骤 7 涨幅次数条件
        is_final_divergence = is_divergence and (large_gain_count >= 3)

        if is_final_divergence:
            message = f"检测到 MACD 底背离，置信度{confidence:.1f}%"
            if verbose:
                print(f"\n[成功] 检测到 MACD 底背离! 置信度：{confidence:.1f}%")
        else:
            if not is_divergence:
                message = "未检测到 MACD 底背离"
                if verbose:
                    print(f"\n[失败] 未检测到 MACD 底背离")
            else:
                message = f"MACD 背离但涨幅次数不足 (次数={large_gain_count})"
                if verbose:
                    print(f"\n[失败] MACD 背离但涨幅次数不足 (次数={large_gain_count}, 要求>=3)")

        return DivergenceResult(
            code=stock_code,
            divergence_date=df['date'].iloc[latest_idx].strftime('%Y-%m-%d'),
            is_divergence=is_final_divergence,
            confidence=confidence,
            dip_a_start=df['date'].iloc[dip_a_start].strftime('%Y-%m-%d'),
            dip_a_end=df['date'].iloc[dip_a_end].strftime('%Y-%m-%d'),
            dip_c_start=df['date'].iloc[dip_c_start].strftime('%Y-%m-%d'),
            dip_c_end=df['date'].iloc[dip_c_end].strftime('%Y-%m-%d'),
            macd_a_value=macd_a_value,
            macd_c_value=macd_c_value,
            message=message
        )


def detect_bull_macd_divergence(stock_code: str, end_date: Optional[str] = None, days: int = 250, verbose: bool = False) -> Optional[Dict]:
    """
    便捷函数：检测 MACD 底背离

    Args:
        stock_code: 股票代码
        end_date: 结束日期，可选
        days: K 线天数，默认 250 天
        verbose: 是否打印详细诊断信息

    Returns:
        检测结果字典
    """
    detector = BullMACDDivergenceDetector()
    result = detector.detect(stock_code, end_date, days, verbose=verbose)
    return result.to_dict() if result else None


def batch_detect_from_csv(csv_path: str, end_date: Optional[str] = None, days: int = 250, verbose: bool = False) -> List[Dict]:
    """
    从 stock_limitup.csv 文件批量检测 MACD 底背离

    Args:
        csv_path: stock_limitup.csv 文件路径
        end_date: 结束日期，可选
        days: K 线天数，默认 250 天
        verbose: 是否打印详细诊断信息

    Returns:
        检测结果列表
    """
    try:
        reader = StockLimitupCSVReader(csv_path)
        stock_list = reader.get_stock_list()
        
        if not stock_list:
            logger.warning(f"CSV 文件为空或读取失败: {csv_path}")
            return []
        
        print(f"[信息] 从 {csv_path} 加载 {len(stock_list)} 只股票")
        
        results = []
        total = len(stock_list)
        
        for idx, stock_info in enumerate(stock_list):
            stock_code = stock_info.code
            stock_name = stock_info.name
            sector = stock_info.sector
            
            print(f"\n[{idx+1}/{total}] 检测：{stock_code} - {stock_name}")
            
            result = detect_bull_macd_divergence(stock_code, end_date, days, verbose=verbose)
            if result and result['is_divergence']:
                result['stock_name'] = stock_name
                result['sector'] = sector
                results.append(result)
                print(f"  [OK] 符合条件！")
            else:
                print(f"  [--] 不符合条件")
        
        return results
    except Exception as e:
        logger.error(f"读取 CSV 文件失败: {e}")
        import traceback
        traceback.print_exc()
        return []

def generate_markdown_content(results: List[Dict]) -> str:
    """
    生成 markdown 格式的检测报告内容

    Args:
        results: 检测结果列表（已过滤，只包含符合条件的股票）

    Returns:
        markdown 内容字符串
    """
    from datetime import datetime
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 生成 markdown 内容
    content = f"# MACD 底背离选股报告\n\n"
    content += f"生成日期：{today}\n\n"
    content += "| 股票代码 | 股票名称 | 关联板块 | MACD A值 | MACD C值 | 下跌阶段A | 下跌阶段C | 置信度 |\n"
    content += "|---------|---------|---------|---------|---------|---------|---------|---------|\n"
    
    for result in results:
        row = f"| {result['code']} | {result.get('stock_name', '')} | {result.get('sector', '')} | {result['macd_a_value']} | {result['macd_c_value']} | {result['dip_a_start']} ~ {result['dip_a_end']} | {result['dip_c_start']} ~ {result['dip_c_end']} | {result['confidence']}% |\n"
        content += row
    
    return content


def upload_to_gitee(content: str, remote_dir: str = "xg") -> bool:
    """
    将报告上传到 Gitee

    Args:
        content: markdown 内容
        remote_dir: Gitee 远程目录，默认为 xg

    Returns:
        bool: 上传是否成功
    """
    from datetime import datetime
    
    try:
        # 导入 GiteeClient
        import sys
        import os
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        
        from src.gitee_client import GiteeClient
        
        # 初始化 Gitee 客户端
        client = GiteeClient()
        
        # 生成文件名
        today = datetime.now().strftime("%Y-%m-%d")
        filename = f"MACD底背离选股_{today}.md"
        remote_path = f"{remote_dir}/{filename}"
        
        # 上传到 Gitee
        success = client.upload_content(content, remote_path, message=f"更新 MACD 底背离选股报告 {today}")
        
        if success:
            print(f"✅ 报告已上传到 Gitee: {remote_path}")
        else:
            print(f"❌ 上传到 Gitee 失败")
        
        return success
    
    except Exception as e:
        logger.error(f"上传到 Gitee 失败: {e}")
        return False


def main():
    """
    主函数：支持两种模式
    1. 单个股票检测
    2. 从 CSV 文件批量检测并上传到 Gitee（默认使用 sources/stock_limitup.csv）
    """
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description="MACD 底背离检测工具")
    parser.add_argument('--stock', type=str, help='股票代码，如 000020.SZ')
    parser.add_argument('--csv', type=str, default='sources/stock_limitup.csv', help='stock_limitup.csv 文件路径，默认为 sources/stock_limitup.csv')
    parser.add_argument('--end-date', type=str, help='结束日期，如 2026-03-13')
    parser.add_argument('--days', type=int, default=250, help='K 线天数')
    parser.add_argument('--verbose', action='store_true', help='打印详细信息')
    parser.add_argument('--remote-dir', type=str, default='xg', help='Gitee 远程目录，默认为 xg')
    parser.add_argument('--no-upload', action='store_true', help='不上传到 Gitee，仅本地生成报告')
    
    args = parser.parse_args()
    
    if args.stock:
        # 单个股票检测模式
        result = detect_bull_macd_divergence(args.stock, args.end_date, args.days, args.verbose)
        if result:
            print(f"\n股票代码：{result['code']}")
            print(f"分析日期：{result['divergence_date']}")
            print(f"是否背离：{result['is_divergence']}")
            print(f"置信度：{result['confidence']}%")
            print(f"消息：{result['message']}")
            if result['is_divergence']:
                print(f"下跌段 A: {result['dip_a_start']} ~ {result['dip_a_end']}")
                print(f"下跌段 C: {result['dip_c_start']} ~ {result['dip_c_end']}")
                print(f"MACD A 值：{result['macd_a_value']}")
                print(f"MACD C 值：{result['macd_c_value']}")
    
    else:
        # 批量检测模式（默认）
        csv_path = args.csv
        if not os.path.exists(csv_path):
            print(f"[错误] CSV 文件不存在：{csv_path}")
            return
        
        print(f"[信息] 使用 CSV 文件：{csv_path}")
        results = batch_detect_from_csv(csv_path, args.end_date, args.days, args.verbose)
        
        if results:
            # 生成 markdown 内容
            content = generate_markdown_content(results)
            
            if args.no_upload:
                # 仅本地生成报告
                from datetime import datetime
                today = datetime.now().strftime("%Y-%m-%d")
                filename = f"MACD底背离选股_{today}.md"
                os.makedirs('output', exist_ok=True)
                filepath = os.path.join('output', filename)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"\n{'='*80}")
                print(f"批量检测完成！")
                print(f"检测到 {len(results)} 只符合条件的股票")
                print(f"报告已生成：{filepath}")
                print(f"{'='*80}")
            else:
                # 上传到 Gitee
                success = upload_to_gitee(content, args.remote_dir)
                if success:
                    print(f"\n{'='*80}")
                    print(f"批量检测完成！")
                    print(f"检测到 {len(results)} 只符合条件的股票")
                    print(f"报告已上传到 Gitee 目录：{args.remote_dir}")
                    print(f"{'='*80}")
                else:
                    print(f"\n[错误] 上传到 Gitee 失败")
        else:
            print("未检测到符合条件的股票，不上传到 Gitee")


if __name__ == "__main__":
    main()
