# 获取日K线历史数据
- 接口地址
https://api-ddc-wscn.xuangubao.com.cn/market/kline?tick_count=1&prod_code=601969.SS&adjust_price_type=forward&period_type=2592000&fields=tick_at,open_px,close_px,high_px,low_px,turnover_volume,turnover_value,turnover_ratio,average_px,px_change,px_change_rate,avg_px,business_amount,business_balance,ma5,ma10,ma20,ma60

 入参说明:
 股票代码prod_code=601969.SS
 tick_count:要查询的天数，比如半年 180

 出差格式:
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