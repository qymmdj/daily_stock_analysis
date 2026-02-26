"""
趋势买点分析器
根据趋势买点分析.md需求实现（更新版）
"""
import sys
import os
# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta

class TrendAnalyzer:
    """趋势分析器 - 根据最新需求实现"""

    def __init__(self):
        pass

    def analyze_trend_support_point(self, stock_code: str, kline_data: List[Dict]) -> Optional[Dict]:
        """
        根据新需求分析趋势支撑点：
        1. 从最近的时间开始判断，如果是金叉，在查看前一天是否MA10 >= MA20，如果是继续往前查找
        2. 直到MA10 < MA20,则返回这一天的下标
        3. 从第二天开始分析，直到数据结束或ma10<ma20终止
        4. 判断股价每次最接近10或20日均线的某一天时，成交量是否大于前一日，且涨幅较大
        5. 只统计出现这种情况的次数
        6. 输出接近均线的总次数和满足放量大涨条件的次数

        Args:
            stock_code: 股票代码
            kline_data: K线数据

        Returns:
            包含分析结果的字典
        """
        if not kline_data:
            return None

        # 按时间正序排列（最早的在前面）
        sorted_data = sorted(kline_data, key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'))

        # 从最近的时间开始判断，如果是金叉，在查看前一天是否MA10 >= MA20，如果是继续往前查找
        # 直到MA10 < MA20,则返回这一天的下标
        start_analysis_index = self._find_start_index(sorted_data)
        
        if start_analysis_index is None:
            print(f"股票 {stock_code} 无法确定分析起始位置")
            return None

        # 从找到的那一天的第二天开始分析
        analysis_start_index = start_analysis_index + 1

        # 从确定的日期开始分析，直到数据结束或ma10<ma20
        analysis_data = []
        if analysis_start_index < len(sorted_data):
            for i in range(analysis_start_index, len(sorted_data)):
                current_data = sorted_data[i]
                ma10 = current_data.get('ma10')
                ma20 = current_data.get('ma20')
                if ma10 is None or ma20 is None:
                    analysis_data.append(current_data)
                    continue
                if ma10 < ma20:
                    break
                analysis_data.append(current_data)

        # 当金叉逻辑分析区间过短或为空时，回退为分析最近90天（需求：只统计最近3个月）
        ANALYSIS_DAYS = 90
        if len(analysis_data) < 30:
            start_idx = max(0, len(sorted_data) - ANALYSIS_DAYS)
            analysis_data = []
            for i in range(start_idx, len(sorted_data)):
                d = sorted_data[i]
                if d.get('ma10') is not None and d.get('ma20') is not None:
                    analysis_data.append(d)

        if len(analysis_data) < 2:  # 至少需要2天数据，因为需要前一天的数据进行对比
            print(f"股票 {stock_code} 有效数据不足，无法进行分析")
            return None

        # 分析接近均线的交易日
        near_10 = []  # 存储接近10日均线的日期
        near_20 = []  # 存储接近20日均线的日期

        for i in range(1, len(analysis_data)):  # 从第2天开始，因为需要前一天的数据
            current_data = analysis_data[i]
            prev_data = analysis_data[i-1]

            close_px = current_data.get('close_px')
            open_px = current_data.get('open_px')
            low_px = current_data.get('low_px')  # 当日最低价
            volume = current_data.get('turnover_volume')
            prev_volume = prev_data.get('turnover_volume')
            ma10_val = current_data.get('ma10')  # 直接使用API返回的10日均线
            ma20_val = current_data.get('ma20')  # 直接使用API返回的20日均线

            if not all([close_px, open_px, low_px, volume, prev_volume]):
                continue

            # 计算涨幅百分比（使用开盘价作为基准）
            if open_px != 0:
                change_pct = ((close_px - open_px) / open_px) * 100
            else:
                continue

            # 分别计算最低价与10日均线和20日均线的偏离度
            deviation_ma10 = None
            deviation_ma20 = None
            
            if ma10_val is not None and ma10_val != 0:
                deviation_ma10 = ((low_px - ma10_val) / ma10_val) * 100
            
            if ma20_val is not None and ma20_val != 0:
                deviation_ma20 = ((low_px - ma20_val) / ma20_val) * 100
            
            # 选择偏离度绝对值最小的那个均线
            closest_ma_type = None
            closest_deviation = None
            
            if deviation_ma10 is not None and deviation_ma20 is not None:
                # 比较绝对值，选择更接近的均线
                if abs(deviation_ma10) <= abs(deviation_ma20):
                    closest_ma_type = '10日均线'
                    closest_deviation = deviation_ma10
                    closest_ma_value = ma10_val
                else:
                    closest_ma_type = '20日均线'
                    closest_deviation = deviation_ma20
                    closest_ma_value = ma20_val
            elif deviation_ma10 is not None:
                closest_ma_type = '10日均线'
                closest_deviation = deviation_ma10
                closest_ma_value = ma10_val
            elif deviation_ma20 is not None:
                closest_ma_type = '20日均线'
                closest_deviation = deviation_ma20
                closest_ma_value = ma20_val
            else:
                continue  # 如果两个均线都没有有效数据，跳过

            # 检查最接近的均线偏离度是否在合理范围内（需求文档-1~1点，放宽至±3.5%以提高命中率）
            if -3.5 <= closest_deviation <= 3.5:  # 接近均线：最低价与均线偏差在±3.5%以内
                # 计算第二天的涨幅
                next_day_change_pct = None
                if i + 1 < len(analysis_data):  # 确保有下一天的数据
                    next_data = analysis_data[i + 1]
                    next_close_px = next_data.get('close_px')
                    next_open_px = next_data.get('open_px')
                    
                    if next_close_px and next_open_px and next_open_px != 0:
                        next_day_change_pct = ((next_close_px - next_open_px) / next_open_px) * 100
                
                # 检查是否满足放量大涨条件（成交量必须是昨日的1.2倍以上）
                is_large_volumn = volume >= prev_volume * 1.2 and self._is_strong_increase(change_pct, stock_code)
                
                # 根据均线类型添加到相应列表
                day_entry = {
                    'day': current_data['date'],
                    'rate': round(change_pct, 2),
                    'next_rate': round(next_day_change_pct, 2) if next_day_change_pct is not None else None,
                    'is_large_volumn': is_large_volumn
                }
                
                if closest_ma_type == '10日均线':
                    near_10.append(day_entry)
                elif closest_ma_type == '20日均线':
                    near_20.append(day_entry)

        # 提取股票代码部分（去掉交易所后缀）
        stock_code_clean = stock_code.split('.')[0]
        
        # 构建结果
        result = {
            'code': stock_code_clean,
            'near_10': near_10,
            'near_20': near_20
        }

        return result

    def _find_start_index(self, sorted_data: List[Dict]) -> Optional[int]:
        """
        从最近的时间开始判断，如果是金叉，在查看前一天是否MA10 >= MA20，如果是继续往前查找
        直到MA10 < MA20,则返回这一天的下标
        """
        # 从最近的数据开始往前查找
        for i in range(len(sorted_data) - 1, -1, -1):
            current_data = sorted_data[i]
            ma10 = current_data.get('ma10')
            ma20 = current_data.get('ma20')
            
            # 检查是否MA10 >= MA20
            if ma10 is not None and ma20 is not None:
                if ma10 >= ma20:
                    # 如果MA10 >= MA20，继续往前找
                    continue
                else:
                    # 如果MA10 < MA20，返回当前索引
                    return i
            else:
                # 如果数据缺失，继续往前找
                continue
        
        # 如果遍历完所有数据都满足MA10 >= MA20，返回0
        return 0

    def _is_strong_increase(self, change_pct: float, stock_code: str) -> bool:
        """
        判断是否为强涨幅
        创业板 > 6%, 主板 > 4%
        """
        # 根据股票代码判断板块（API使用.SS表示上海，.SZ表示深圳）
        code_base = stock_code.split('.')[0]
        if stock_code.endswith('.SZ') and code_base.startswith('300'):  # 创业板
            return change_pct > 6.0
        elif stock_code.endswith(('.SH', '.SS')) or (stock_code.endswith('.SZ') and code_base.startswith(('000', '001', '002', '003'))):  # 主板/科创板
            return change_pct > 4.0
        else:
            # 默认按主板处理（含688科创板等）
            return change_pct > 4.0


if __name__ == "__main__":
    # 这里可以添加测试代码
    print("趋势分析器已准备就绪")