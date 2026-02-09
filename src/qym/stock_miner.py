# -*- coding: utf-8 -*-
"""
===================================
个股分时数据获取器
===================================

功能：
1. 获取个股实时分时数据
2. 解析分时数据格式
3. 提供便捷的数据访问接口

基于选股宝API: https://api-ddc-wscn.xuangubao.com.cn/market/trend
"""

import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
import requests

logger = logging.getLogger(__name__)


class StockMiner:
    """
    个股分时数据获取器
    
    用于获取和解析个股的分时交易数据
    """
    
    # API配置
    BASE_URL = "https://api-ddc-wscn.xuangubao.com.cn/market/trend"
    DEFAULT_FIELDS = [
        "tick_at",          # 时间戳
        "close_px",         # 收盘价
        "avg_px",           # 均价
        "turnover_volume",  # 成交量
        "turnover_value",   # 成交额
        "open_px",          # 开盘价
        "high_px",          # 最高价
        "low_px",           # 最低价
        "px_change",        # 价格变动
        "px_change_rate"    # 涨跌幅
    ]
    
    # 请求配置
    TIMEOUT = 30
    RETRY_TIMES = 3
    RETRY_DELAY = 1
    
    def __init__(self):
        """初始化分时数据获取器"""
        self.session = requests.Session()
        # 设置请求头
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        })
    
    def get_minutely_data(self, stock_code: str, fields: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """
        获取个股分时数据
        
        Args:
            stock_code: 股票代码，如 "601969.SS"
            fields: 需要获取的字段列表，默认获取全部字段
            
        Returns:
            分时数据字典，格式如下：
            {
                'code': 股票代码,
                'name': 股票名称,
                'data': [
                    {
                        'time': 时间戳,
                        'datetime': 时间字符串,
                        'open': 开盘价,
                        'high': 最高价,
                        'low': 最低价,
                        'close': 收盘价,
                        'volume': 成交量,
                        'amount': 成交额,
                        'avg_price': 均价,
                        'change': 价格变动,
                        'change_rate': 涨跌幅
                    },
                    ...
                ],
                'pre_close': 昨收价,
                'total_points': 数据点总数
            }
            如果获取失败返回 None
        """
        if not stock_code:
            logger.error("股票代码不能为空")
            return None
            
        # 使用默认字段
        if fields is None:
            fields = self.DEFAULT_FIELDS
            
        # 构建请求参数
        params = {
            'prod_code': stock_code,
            'fields': ','.join(fields)
        }
        
        # 重试机制
        for attempt in range(self.RETRY_TIMES):
            try:
                logger.info(f"正在获取 {stock_code} 分时数据 (尝试 {attempt + 1}/{self.RETRY_TIMES})")
                
                response = self.session.get(
                    self.BASE_URL,
                    params=params,
                    timeout=self.TIMEOUT
                )
                
                # 检查响应状态
                response.raise_for_status()
                
                # 解析JSON响应
                data = response.json()
                
                if data.get('code') != 20000:
                    logger.error(f"API返回错误: {data.get('message', '未知错误')}")
                    return None
                
                # 解析数据
                parsed_data = self._parse_minutely_response(data, stock_code)
                
                if parsed_data:
                    logger.info(f"成功获取 {stock_code} 分时数据，共 {parsed_data['total_points']} 个数据点")
                    return parsed_data
                else:
                    logger.error(f"解析 {stock_code} 分时数据失败")
                    return None
                    
            except requests.exceptions.RequestException as e:
                logger.warning(f"请求失败 (尝试 {attempt + 1}/{self.RETRY_TIMES}): {str(e)}")
                if attempt < self.RETRY_TIMES - 1:
                    time.sleep(self.RETRY_DELAY)
                else:
                    logger.error(f"获取 {stock_code} 分时数据失败: {str(e)}")
                    return None
            except Exception as e:
                logger.error(f"处理 {stock_code} 分时数据时发生错误: {str(e)}")
                return None
        
        return None
    
    def _parse_minutely_response(self, response_data: Dict, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        解析分时数据响应
        
        Args:
            response_data: API返回的原始数据
            stock_code: 股票代码
            
        Returns:
            解析后的数据字典
        """
        try:
            # 提取核心数据
            candle_data = response_data.get('data', {}).get('candle', {})
            stock_data = candle_data.get(stock_code, {})
            
            if not stock_data:
                logger.warning(f"未找到股票 {stock_code} 的数据")
                return None
            
            lines = stock_data.get('lines', [])
            fields = response_data.get('data', {}).get('fields', [])
            pre_close_px = stock_data.get('pre_close_px', 0)
            
            if not lines or not fields:
                logger.warning(f"股票 {stock_code} 数据为空")
                return None
            
            # 解析每个数据点
            parsed_lines = []
            field_mapping = {field: idx for idx, field in enumerate(fields)}
            
            for line in lines:
                try:
                    # 提取各字段值
                    data_point = {}
                    
                    # 时间信息
                    if 'tick_at' in field_mapping:
                        timestamp = line[field_mapping['tick_at']]
                        data_point['time'] = timestamp
                        data_point['datetime'] = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                    
                    # 价格信息
                    if 'open_px' in field_mapping:
                        data_point['open'] = float(line[field_mapping['open_px']])
                    if 'high_px' in field_mapping:
                        data_point['high'] = float(line[field_mapping['high_px']])
                    if 'low_px' in field_mapping:
                        data_point['low'] = float(line[field_mapping['low_px']])
                    if 'close_px' in field_mapping:
                        data_point['close'] = float(line[field_mapping['close_px']])
                    
                    # 成交量信息
                    if 'turnover_volume' in field_mapping:
                        data_point['volume'] = int(line[field_mapping['turnover_volume']])
                    if 'turnover_value' in field_mapping:
                        data_point['amount'] = float(line[field_mapping['turnover_value']])
                    
                    # 均价
                    if 'avg_px' in field_mapping:
                        data_point['avg_price'] = float(line[field_mapping['avg_px']])
                    
                    # 价格变动
                    if 'px_change' in field_mapping:
                        data_point['change'] = float(line[field_mapping['px_change']])
                    if 'px_change_rate' in field_mapping:
                        data_point['change_rate'] = float(line[field_mapping['px_change_rate']])
                    
                    parsed_lines.append(data_point)
                    
                except (IndexError, ValueError, TypeError) as e:
                    logger.warning(f"解析数据点时出错: {str(e)}")
                    continue
            
            if not parsed_lines:
                logger.error("未解析到有效数据点")
                return None
            
            # 构建返回结果
            result = {
                'code': stock_code,
                'name': stock_code,  # API未返回股票名称，暂时用代码代替
                'data': parsed_lines,
                'pre_close': float(pre_close_px) if pre_close_px else 0,
                'total_points': len(parsed_lines)
            }
            
            return result
            
        except Exception as e:
            logger.error(f"解析分时数据响应时出错: {str(e)}")
            return None
    
    def get_latest_price(self, stock_code: str) -> Optional[float]:
        """
        获取个股最新价格
        
        Args:
            stock_code: 股票代码
            
        Returns:
            最新价格，如果获取失败返回 None
        """
        data = self.get_minutely_data(stock_code, ['tick_at', 'close_px'])
        if data and data['data']:
            # 返回最新的收盘价
            return data['data'][-1]['close']
        return None
    
    def get_price_change(self, stock_code: str) -> Optional[Dict[str, float]]:
        """
        获取个股价格变动信息
        
        Args:
            stock_code: 股票代码
            
        Returns:
            价格变动信息字典：
            {
                'current_price': 当前价格,
                'pre_close': 昨收价,
                'change': 价格变动,
                'change_rate': 涨跌幅(%)
            }
        """
        data = self.get_minutely_data(stock_code, ['tick_at', 'close_px', 'px_change', 'px_change_rate'])
        if data and data['data'] and data['pre_close']:
            latest = data['data'][-1]
            return {
                'current_price': latest['close'],
                'pre_close': data['pre_close'],
                'change': latest['change'],
                'change_rate': latest['change_rate']
            }
        return None
    
    def get_trading_volume(self, stock_code: str) -> Optional[int]:
        """
        获取个股最新成交量
        
        Args:
            stock_code: 股票代码
            
        Returns:
            最新成交量，如果获取失败返回 None
        """
        data = self.get_minutely_data(stock_code, ['tick_at', 'turnover_volume'])
        if data and data['data']:
            return data['data'][-1]['volume']
        return None
    
    def close(self):
        """关闭会话"""
        if self.session:
            self.session.close()


def get_stock_minutely_data(stock_code: str) -> Optional[Dict[str, Any]]:
    """
    便捷函数：获取个股分时数据
    
    Args:
        stock_code: 股票代码，如 "601969.SS"
        
    Returns:
        分时数据字典，详见 StockMiner.get_minutely_data 方法说明
    """
    miner = StockMiner()
    try:
        return miner.get_minutely_data(stock_code)
    finally:
        miner.close()


def get_stock_latest_price(stock_code: str) -> Optional[float]:
    """
    便捷函数：获取个股最新价格
    
    Args:
        stock_code: 股票代码
        
    Returns:
        最新价格
    """
    miner = StockMiner()
    try:
        return miner.get_latest_price(stock_code)
    finally:
        miner.close()


def get_stock_price_change(stock_code: str) -> Optional[Dict[str, float]]:
    """
    便捷函数：获取个股价格变动信息
    
    Args:
        stock_code: 股票代码
        
    Returns:
        价格变动信息字典
    """
    miner = StockMiner()
    try:
        return miner.get_price_change(stock_code)
    finally:
        miner.close()


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)
    
    print("个股分时数据获取器测试")
    print("=" * 50)
    
    # 测试股票代码
    test_codes = ["601969.SS", "000001.SZ"]
    
    for code in test_codes:
        print(f"\n测试股票: {code}")
        print("-" * 30)
        
        # 获取完整分时数据
        data = get_stock_minutely_data(code)
        if data:
            print(f"数据点数量: {data['total_points']}")
            print(f"昨收价: {data['pre_close']}")
            if data['data']:
                latest = data['data'][-1]
                print(f"最新价格: {latest['close']}")
                print(f"最新时间: {latest['datetime']}")
                if 'change_rate' in latest:
                    print(f"涨跌幅: {latest['change_rate']:.2f}%")
        else:
            print("获取数据失败")