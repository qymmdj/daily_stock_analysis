# 获取日K线历史数据
- 接口地址
https://api-ddc-wscn.xuangubao.com.cn/market/kline?tick_count=1&prod_code=601969.SS&adjust_price_type=forward&period_type=2592000&fields=tick_at,open_px,close_px,high_px,low_px,turnover_volume,turnover_value,turnover_ratio,average_px,px_change,px_change_rate,avg_px,business_amount,business_balance,ma5,ma10,ma20,ma60

 入参说明:
 股票代码prod_code=601969.SS
 tick_count:要查询的天数，比如半年 180

 出参格式:
 {
    "code": 20000,
    "message": "OK",
    "data": {
        "candle": {
            "601969.SS": {
                "lines": [
                    [
                        11.99,
                        12.61,
                        12.77,
                        10.68,
                        0,
                        0.7299999999999986,
                        6.144781144781133,
                        943616020,
                        10968687487,
                        1769558400,
                        0,
                        10.898,
                        9.142,
                        7.847499999999999,
                        3.1245499374168744
                    ]
                ],
                "market_type": "mdc",
                "pre_close_px": 0,
                "securities_type": "stock"
            }
        },
        "fields": [
            "open_px",
            "close_px",
            "high_px",
            "low_px",
            "average_px",
            "px_change",
            "px_change_rate",
            "turnover_volume",
            "turnover_value",
            "tick_at",
            "avg_px",
            "ma5",
            "ma10",
            "ma20",
            "turnover_ratio"
        ]
    }
}

# 获取个股分时数据
- 接口地址:
https://api-ddc-wscn.xuangubao.com.cn/market/trend?fields=tick_at,close_px,avg_px,turnover_volume,turnover_value,open_px,high_px,low_px,px_change,px_change_rate&prod_code=603317.SS

 - 入参说明:
 1. 股票代码 prod_code=601969.SS
 - 出参格式:

```json
{
    "code": 20000,
    "message": "OK",
    "data": {
        "candle": {
            "603317.SS": {
                "lines": [
                    [
                        1770255000,
                        13.52,
                        13.52,
                        0,
                        0,
                        13.52,
                        13.53,
                        13.51,
                        0,
                        0
                    ],
                    [
                        1770255060,
                        13.49,
                        13.505516458569806,
                        163800,
                        2212024,
                        13.51,
                        13.52,
                        13.48,
                        -0.02999999999999936,
                        -0.22189349112425563
                    ]
                ],
                "market_close": 0,
                "market_open": 0,
                "market_type": "mdc",
                "midday_break": 0,
                "pre_close_px": 13.52,
                "securities_type": "stock",
                "sub_type": "",
                "total": 241
            }
        },
        "fields": [
            "tick_at",
            "close_px",
            "avg_px",
            "turnover_volume",
            "turnover_value",
            "open_px",
            "high_px",
            "low_px",
            "px_change",
            "px_change_rate"
        ]
    }
}
```

# 获取每日历史涨停数据
- 接口地址
http://flash-api.xuangubao.cn/api/pool/detail?pool_name=limit_up&date=2025-11-06
入参说明:
1. date 为要查询的日期
1. 响应报文格式:
```json
{
    "code": 20000,
    "message": "OK",
    "data": [
        {
            "break_limit_down_times": 0,
            "break_limit_up_times": 1,
            "buy_lock_volume_ratio": 0.027760226,
            "change_percent": 0.1,
            "first_break_limit_down": 0,
            "first_break_limit_up": 1762392674,
            "first_limit_down": 0,
            "first_limit_up": 1762392641,
            "is_new_stock": false,
            "issue_price": 29.93,
            "last_break_limit_down": 0,
            "last_break_limit_up": 1762392674,
            "last_limit_down": 0,
            "last_limit_up": 1762392788,
            "limit_down_days": 0,
            "limit_timeline": null,
            "limit_up_days": 1,
            "listed_date": 1502035200,
            "m_days_n_boards_boards": 0,
            "m_days_n_boards_days": 0,
            "mtm": 0,
            "nearly_new_acc_pcp": 0,
            "nearly_new_break_days": 0,
            "new_stock_acc_pcp": 0.0694954895,
            "new_stock_break_limit_up": 0,
            "new_stock_limit_up_days": 0,
            "new_stock_limit_up_price_before_broken": 0,
            "non_restricted_capital": 6757128510.99,
            "prev_close_price": 29.1,
            "price": 32.01,
            "sell_lock_volume_ratio": 0,
            "stock_chi_name": "深圳新星",
            "surge_reason": {
                "symbol": "603978.SS",
                "stock_reason": "全球头部铝晶粒细化剂制造商；公司主要从事铝晶粒细化剂等合金材料及锂电池材料的研发与生产制造",
                "related_plates": [
                    {
                        "plate_name": "有色 · 铝",
                        "plate_reason": "行业产能逼近上限，电解铝价格持续上涨"
                    }
                ]
            },
            "symbol": "603978.SS",
            "total_capital": 6757128510.99,
            "turnover_ratio": 0.0537966021,
            "volume_bias_ratio": 0.5997277075,
            "yesterday_break_limit_up_times": 0,
            "yesterday_first_limit_up": 0,
            "yesterday_last_limit_up": 0,
            "yesterday_limit_down_days": 0,
            "yesterday_limit_up_days": 0
        },
        {
            "break_limit_down_times": 0,
            "break_limit_up_times": 0,
            "buy_lock_volume_ratio": 0.0155344374,
            "change_percent": 0.0999567287,
            "first_break_limit_down": 0,
            "first_break_limit_up": 0,
            "first_limit_down": 0,
            "first_limit_up": 1762410021,
            "is_new_stock": false,
            "issue_price": 34.6,
            "last_break_limit_down": 0,
            "last_break_limit_up": 0,
            "last_limit_down": 0,
            "last_limit_up": 1762410021,
            "limit_down_days": 0,
            "limit_timeline": null,
            "limit_up_days": 1,
            "listed_date": 1580832000,
            "m_days_n_boards_boards": 0,
            "m_days_n_boards_days": 0,
            "mtm": 0,
            "nearly_new_acc_pcp": 0,
            "nearly_new_break_days": 0,
            "new_stock_acc_pcp": 1.2040462428,
            "new_stock_break_limit_up": 0,
            "new_stock_limit_up_days": 0,
            "new_stock_limit_up_price_before_broken": 0,
            "non_restricted_capital": 8072805814.8,
            "prev_close_price": 69.33,
            "price": 76.26,
            "sell_lock_volume_ratio": 0,
            "stock_chi_name": "博杰股份",
            "surge_reason": {
                "symbol": "002975.SZ",
                "stock_reason": "1、公司研发人形机器人IMU传感器测试平台、camera与力传感器检测技术，布局人形机器人测试板块\n2、公司自研液冷散热方案已植入GPU测试设备，面向英伟达、微软、阿里等全球头部服务器厂商供货，并推进从设备向零部件供应的战略转型，公司三季报净利润同比增长6760.54%",
                "related_plates": [
                    {
                        "plate_name": "机器人",
                        "plate_reason": "小鹏新一代人形机器人IRON亮相"
                    }
                ]
            },
            "symbol": "002975.SZ",
            "total_capital": 12224675742.18,
            "turnover_ratio": 0.1087838745,
            "volume_bias_ratio": 1.1700714901,
            "yesterday_break_limit_up_times": 0,
            "yesterday_first_limit_up": 0,
            "yesterday_last_limit_up": 0,
            "yesterday_limit_down_days": 0,
            "yesterday_limit_up_days": 0
        }
    ]
}
```
    2. 英文的字段对应的中文含义可以在下面找到
    股票代码     TEXT    NOT NULL,
    股票中文名称   TEXT,
    是否新股     BOOLEAN,
    上市日期     TEXT,
    发行价格     REAL,
    当前价格     REAL,
    前收盘价     REAL,
    涨跌幅      REAL,
    打开涨停次数   INTEGER,
    打开跌停次数   INTEGER,
    连续涨停天数   INTEGER,
    连续跌停天数   INTEGER,
    首次打开涨停时间 TEXT,
    首次打开跌停时间 TEXT,
    首次涨停时间   TEXT,
    首次跌停时间   TEXT,
    最后打开涨停时间 TEXT,
    最后打开跌停时间 TEXT,
    最后涨停时间   TEXT,
    最后跌停时间   TEXT,
    昨日打开涨停次数 INTEGER,
    昨日首次涨停时间 TEXT,
    昨日最后涨停时间 TEXT,
    昨日连续涨停天数 INTEGER,
    昨日连续跌停天数 INTEGER,
    总股本      REAL,
    流通股本     REAL,
    换手率      REAL,
    量比       REAL,
    买入锁仓比例   REAL,
    卖出锁仓比例   REAL,
    新股累计涨跌幅  REAL,
    新股打开涨停次数 INTEGER,
    新股连续涨停天数 INTEGER,
    新股开板前价格  REAL,
    次新股累计涨跌幅 REAL,
    次新股开板天数  INTEGER,
    M天N板_天数M INTEGER,
    M天N板_板数N INTEGER,
    动量指标     REAL,
    个股涨停原因   TEXT,
    关联板块名称   TEXT,
    板块上涨原因   TEXT