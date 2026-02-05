"""
获取股票历史K线数据的工具类
根据API说明.md中的接口实现
"""
from operator import le
import requests
from typing import Dict, List, Optional
import json
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.DEBUG)
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True

class KLineFetcher:
    """K线数据获取器"""
    
    def __init__(self):
        self.base_url = "https://api-ddc-wscn.xuangubao.com.cn/market/kline"
        
    def fetch_kline_data(self, stock_code: str, days: int = 180) -> Optional[List[Dict]]:
        """
        获取指定股票的历史K线数据
        
        Args:
            stock_code: 股票代码，如 "603212.SS"
            days: 查询天数，默认180天（半年）
            
        Returns:
            K线数据列表，每个元素包含开盘价、收盘价、最高价、最低价等信息
        """
        # 根据API说明构建请求参数
        params = {
            'tick_count': days,
            'prod_code': stock_code,
            'adjust_price_type': 'forward',
            'period_type': 86400,  # 日K线
            'fields': 'tick_at,open_px,close_px,high_px,low_px,turnover_volume,turnover_value,turnover_ratio,average_px,px_change,px_change_rate,avg_px,business_amount,business_balance,ma5,ma10,ma20,ma60'
        }
        
        try:
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()

           # print(f"获取数据成功: {data}")
            
            if data.get('code') != 20000:
                print(f"获取数据失败: {data.get('message')}")
                return None
                
            candle_data = data.get('data', {}).get('candle', {}).get(stock_code, {})

            lines = candle_data.get('lines', [])
            fields = data.get('data', {}).get('fields', [])
            
            # 将数据转换为字典格式，便于处理
            result = []
            for line in lines:
                if len(line) == len(fields):
                    kline_dict = {}
                    for i, field in enumerate(fields):
                        kline_dict[field] = line[i]
                    
                    # 将时间戳转换为日期格式
                    if 'tick_at' in kline_dict:
                        timestamp = kline_dict['tick_at']
                        # 时间戳可能是秒级或毫秒级，需要判断
                        if timestamp > 1e10:  # 毫秒级时间戳
                            timestamp /= 1000
                        kline_dict['date'] = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
                    
                    result.append(kline_dict)
                
            return result
            
        except Exception as e:
            print(f"获取K线数据时发生错误: {str(e)}")
            return None


if __name__ == "__main__":
    # 测试获取数据
    fetcher = KLineFetcher()
    data = fetcher.fetch_kline_data("601969.SS", 30)
    if data:
        print(f"获取到 {len(data)} 条数据")
        for i, kline in enumerate(data[:5]):  # 显示前5条数据
            print(f"第{i+1}条: {kline}")
    else:
        print("未能获取数据")