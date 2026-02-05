"""
趋势买点分析器
根据趋势买点分析.md需求实现（更新版）
"""
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
        
        print(f"股票 {stock_code} 的分析起始位置是第 {sorted_data[start_analysis_index]} 天")
        if start_analysis_index is None:
            print(f"股票 {stock_code} 无法确定分析起始位置")
            return None

        # 从找到的那一天的第二天开始分析
        analysis_start_index = start_analysis_index + 1
        if analysis_start_index >= len(sorted_data):
            print(f"股票 {stock_code} 有效数据不足，无法进行分析")
            return None

        # 从确定的日期开始分析，直到数据结束或ma10<ma20
        analysis_data = []
        for i in range(analysis_start_index, len(sorted_data)):
            current_data = sorted_data[i]
            
            # 检查ma10是否仍然大于等于ma20
            ma10 = current_data.get('ma10')
            ma20 = current_data.get('ma20')
            
            if ma10 is None or ma20 is None:
                # 如果均线数据缺失，继续下一个
                analysis_data.append(current_data)
                continue
                
            if ma10 < ma20:
                # 如果ma10<ma20，停止分析
                break
                
            analysis_data.append(current_data)

        if len(analysis_data) < 2:  # 至少需要2天数据，因为需要前一天的数据进行对比
            print(f"股票 {stock_code} 有效数据不足，无法进行分析")
            return None

        # 分析接近均线的交易日
        near_ma_dates = []  # 存储接近均线的日期
        strong_signals = []  # 存储满足放量大涨条件的日期

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

            # 检查最接近的均线偏离度是否在-2到2范围内
            if -2 <= closest_deviation <= 2:  # 接近最近的均线（最低价与最近均线偏差在-2到2个点之间）
                # 计算第二天的涨幅
                next_day_change_pct = None
                if i + 1 < len(analysis_data):  # 确保有下一天的数据
                    next_data = analysis_data[i + 1]
                    next_close_px = next_data.get('close_px')
                    next_open_px = next_data.get('open_px')
                    
                    if next_close_px and next_open_px and next_open_px != 0:
                        next_day_change_pct = ((next_close_px - next_open_px) / next_open_px) * 100
                
                near_ma_dates.append({
                    'date': current_data['date'],
                    'ma_type': closest_ma_type,
                    'price': close_px,
                    'ma_value': closest_ma_value,
                    'volume': volume,
                    'prev_volume': prev_volume,
                    'change_pct': change_pct,
                    'next_day_change_pct': next_day_change_pct  # 添加第二天的涨幅
                })

                # 检查是否满足放量大涨条件（成交量必须是昨日的1.2倍以上）
                if volume >= prev_volume * 1.2 and self._is_strong_increase(change_pct, stock_code):
                    # 计算第二天的涨幅
                    next_day_change_pct = None
                    if i + 1 < len(analysis_data):  # 确保有下一天的数据
                        next_data = analysis_data[i + 1]
                        next_close_px = next_data.get('close_px')
                        next_open_px = next_data.get('open_px')
                        
                        if next_close_px and next_open_px and next_open_px != 0:
                            next_day_change_pct = ((next_close_px - next_open_px) / next_open_px) * 100
                    
                    strong_signals.append({
                        'date': current_data['date'],
                        'ma_type': closest_ma_type,
                        'change_pct': change_pct,
                        'volume': volume,
                        'prev_volume': prev_volume,
                        'next_day_change_pct': next_day_change_pct  # 添加第二天的涨幅
                    })

        # 过滤连续的日期，只保留每组连续日期中最接近的一条
        filtered_near_ma_dates = self._filter_consecutive_dates(near_ma_dates)
        filtered_strong_signals = self._filter_consecutive_dates_strong_signals(strong_signals)

        # 计算第二天上涨的次数
        near_ma_next_day_up_count = sum(1 for item in filtered_near_ma_dates if item['next_day_change_pct'] is not None and item['next_day_change_pct'] > 0)
        strong_signal_next_day_up_count = sum(1 for item in filtered_strong_signals if item['next_day_change_pct'] is not None and item['next_day_change_pct'] > 0)

        # 构建结果
        result = {
            'stock_code': stock_code,
            'near_ma_count': len(filtered_near_ma_dates),  # 接近均线的总次数（过滤后）
            'near_ma_next_day_up_count': near_ma_next_day_up_count,  # 接近均线第二天上涨次数
            'strong_signal_count': len(filtered_strong_signals),  # 满足放量大涨的次数（过滤后）
            'strong_signal_next_day_up_count': strong_signal_next_day_up_count,  # 满足放量大涨第二天上涨次数
            'near_ma_dates': [item['date'] + '(' + item['ma_type'] + ')' for item in filtered_near_ma_dates],
            'strong_signal_dates': [item['date'] + '(' + item['ma_type'] + ')' for item in filtered_strong_signals],
            'strong_signals_with_next_day_change': [
                {
                    'date': signal['date'],
                    'ma_type': signal['ma_type'],
                    'signal_day_change': signal['change_pct'],
                    'next_day_change': signal['next_day_change_pct']
                } 
                for signal in filtered_strong_signals
            ]
        }

        return result

    def _filter_consecutive_dates(self, dates_list: List[Dict]) -> List[Dict]:
        """
        过滤连续的日期，只保留每组连续日期中最接近的一条
        """
        if not dates_list:
            return []

        # 按日期排序（最新的在前面）
        sorted_dates = sorted(dates_list, key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'), reverse=True)
        
        filtered_dates = []
        i = 0
        while i < len(sorted_dates):
            current = sorted_dates[i]
            filtered_dates.append(current)
            
            # 查找连续的日期
            j = i + 1
            while j < len(sorted_dates):
                current_date = datetime.strptime(current['date'], '%Y-%m-%d')
                next_date = datetime.strptime(sorted_dates[j]['date'], '%Y-%m-%d')
                
                # 检查是否为连续日期，且均线类型相同
                if (current_date - next_date).days == 1 and current['ma_type'] == sorted_dates[j]['ma_type']:
                    # 这是连续的日期，跳过
                    j += 1
                else:
                    # 不再是连续日期，跳出循环
                    break
            
            # 更新i的位置
            i = j

        return filtered_dates

    def _filter_consecutive_dates_strong_signals(self, signals_list: List[Dict]) -> List[Dict]:
        """
        过滤连续的强信号日期，只保留每组连续日期中最接近的一条
        """
        if not signals_list:
            return []

        # 按日期排序（最新的在前面）
        sorted_signals = sorted(signals_list, key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'), reverse=True)
        
        filtered_signals = []
        i = 0
        while i < len(sorted_signals):
            current = sorted_signals[i]
            filtered_signals.append(current)
            
            # 查找连续的日期
            j = i + 1
            while j < len(sorted_signals):
                current_date = datetime.strptime(current['date'], '%Y-%m-%d')
                next_date = datetime.strptime(sorted_signals[j]['date'], '%Y-%m-%d')
                
                # 检查是否为连续日期，且均线类型相同
                if (current_date - next_date).days == 1 and current['ma_type'] == sorted_signals[j]['ma_type']:
                    # 这是连续的日期，跳过
                    j += 1
                else:
                    # 不再是连续日期，跳出循环
                    break
            
            # 更新i的位置
            i = j

        return filtered_signals

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
        # 根据股票代码判断板块
        if stock_code.endswith('.SZ') and stock_code.startswith('300'):  # 创业板
            return change_pct > 6.0
        elif stock_code.endswith('.SH') or (stock_code.endswith('.SZ') and stock_code.startswith(('000', '600', '601', '603', '605'))):  # 主板
            return change_pct > 4.0
        else:
            # 默认按主板处理
            return change_pct > 4.0


if __name__ == "__main__":
    # 这里可以添加测试代码
    print("趋势分析器已准备就绪")