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
 1.
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