# 个股分时数据获取器使用说明

## 简介
`stock_miner.py` 是一个基于选股宝API的个股分时数据获取工具，可以获取股票的实时分时交易数据。

## 主要功能

### 1. 核心类 - StockMiner
```python
from src.qym.stock_miner import StockMiner

# 创建实例
miner = StockMiner()

# 获取分时数据
data = miner.get_minutely_data("601969.SS")
print(data)

# 获取最新价格
latest_price = miner.get_latest_price("601969.SS")
print(latest_price)

# 获取价格变动信息
price_change = miner.get_price_change("601969.SS")
print(price_change)

# 关闭连接
miner.close()
```

### 2. 便捷函数
```python
from src.qym.stock_miner import (
    get_stock_minutely_data,
    get_stock_latest_price,
    get_stock_price_change
)

# 获取完整分时数据
data = get_stock_minutely_data("601969.SS")

# 获取最新价格
price = get_stock_latest_price("601969.SS")

# 获取价格变动
change_info = get_stock_price_change("601969.SS")
```

## 返回数据格式

### 分时数据格式
```python
{
    'code': '601969.SS',           # 股票代码
    'name': '601969.SS',           # 股票名称
    'data': [                      # 分时数据列表
        {
            'time': 1770255000,    # 时间戳
            'datetime': '2024-01-01 09:30:00',  # 时间字符串
            'open': 13.52,         # 开盘价
            'high': 13.53,         # 最高价
            'low': 13.51,          # 最低价
            'close': 13.52,        # 收盘价
            'volume': 0,           # 成交量
            'amount': 0,           # 成交额
            'avg_price': 13.52,    # 均价
            'change': 0,           # 价格变动
            'change_rate': 0       # 涨跌幅(%)
        }
    ],
    'pre_close': 13.52,            # 昨收价
    'total_points': 241            # 数据点总数
}
```

### 价格变动格式
```python
{
    'current_price': 12.61,        # 当前价格
    'pre_close': 12.55,            # 昨收价
    'change': 0.06,                # 价格变动
    'change_rate': 0.48            # 涨跌幅(%)
}
```

## 使用示例

### 基础使用
```python
# 简单获取最新价格
from src.qym.stock_miner import get_stock_latest_price

price = get_stock_latest_price("601969.SS")
print(f"最新价格: {price}")
```

### 批量获取多只股票数据
```python
from src.qym.stock_miner import get_stock_price_change

stocks = ["601969.SS", "000001.SZ", "600036.SH"]
for stock in stocks:
    change_info = get_stock_price_change(stock)
    if change_info:
        print(f"{stock}: {change_info['change_rate']:.2f}%")
```

### 获取详细分时数据进行分析
```python
from src.qym.stock_miner import get_stock_minutely_data

# 获取分时数据
data = get_stock_minutely_data("601969.SS")

if data:
    # 分析交易量变化
    volumes = [point['volume'] for point in data['data']]
    avg_volume = sum(volumes) / len(volumes)
    
    # 分析价格波动
    prices = [point['close'] for point in data['data']]
    max_price = max(prices)
    min_price = min(prices)
    
    print(f"平均成交量: {avg_volume:.0f}")
    print(f"最高价: {max_price}")
    print(f"最低价: {min_price}")
```

## 注意事项

1. **股票代码格式**：使用标准格式如 "601969.SS"、"000001.SZ"
2. **网络依赖**：需要网络连接访问选股宝API
3. **频率限制**：避免过于频繁的请求
4. **错误处理**：建议使用try-except处理可能的网络异常
5. **会话管理**：使用StockMiner类时记得调用close()方法

## 错误处理示例
```python
from src.qym.stock_miner import get_stock_latest_price

try:
    price = get_stock_latest_price("601969.SS")
    if price is not None:
        print(f"价格: {price}")
    else:
        print("获取价格失败")
except Exception as e:
    print(f"发生错误: {e}")
```