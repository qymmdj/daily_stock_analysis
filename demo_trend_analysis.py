"""
趋势买点分析演示
基于趋势买点分析.md需求实现（更新版）
"""
import sys
import os
# 添加项目根目录到路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.qym.trend_analysis.main_analyzer import analyze_stock_trend_support


def demo_with_mock_data():
    """
    使用模拟数据演示趋势买点分析功能
    """
    print("="*60)
    print("趋势买点分析功能演示（更新版）")
    print("根据 趋势买点分析.md 需求文档实现")
    print("="*60)
    
    print("\n新功能说明:")
    print("1. 判断股价每次最接近10或20日均线的某一天时，成交量是否大于前一日")
    print("2. 同时股价涨幅较大（创业板大于6个点，主板大于4个点）")
    print("3. 只统计最近3个月的出现这种情况的次数")
    print("4. 输出：接近均线总次数，满足放量大涨条件的次数")
    
    print("\n" + "-"*60)
    print("实际调用示例（需要网络连接获取真实数据）:")
    print("-"*60)
    
    # 示例股票代码
    sample_stocks = ["301486.SZ"]
    
    for stock_code in sample_stocks:
        print(f"\n正在分析股票: {stock_code}")
        print("调用函数: analyze_stock_trend_support()")
        print("输入: 股票代码")
        print("处理:")
        print("  - 获取历史K线数据")
        print("  - 计算10日、20日均线")
        print("  - 寻找接近均线的交易日")
        print("  - 检查是否满足放量大涨条件")
        result = analyze_stock_trend_support(stock_code)
        
        if result:
            print(f"✅ 结果: {result}")
        else:
            print("⚠️  未找到符合条件的趋势支撑点")
            print("   原因可能是：数据不足 或 无符合条件的交易日")
    
    print(f"\n{'='*60}")
    print("核心算法逻辑:")
    print(f"{'='*60}")
    print("""
1. 获取股票历史K线数据（近半年）
2. 筛选出最近3个月的数据
3. 计算10日和20日移动平均线
4. 对于每一天，检查股价是否接近均线（偏差在-1到1个点之间）
5. 如果接近均线，进一步检查是否满足放量大涨条件：
   - 成交量大于前一日成交量
   - 涨幅大于阈值（创业板>6%，主板>4%）
6. 统计接近均线的总次数和满足放量大涨的次数
    """)

    print(f"\n{'='*60}")
    print("文件结构说明:")
    print(f"{'='*60}")
    print("""
src/
└── qym/
    └── trend_analysis/          # 趋势分析模块
        ├── __init__.py          # 包初始化
        ├── kline_fetcher.py     # K线数据获取器
        ├── trend_analyzer.py    # 趋势分析器（新算法）
        └── main_analyzer.py     # 主分析函数入口
    """)
    
    print(f"\n{'='*60}")
    print("函数接口:")
    print(f"{'='*60}")
    print("""
# 主要函数
def analyze_stock_trend_support(stock_code: str) -> Optional[Dict]:
    '''
    趋势买点分析主函数
    输入: 股票代码
    输出: {
        'stock_code': '股票代码',
        'near_ma_count': '接近均线总次数',
        'strong_signal_count': '满足放量大涨次数',
        'near_ma_dates': '接近均线的日期列表',
        'strong_signal_dates': '放量大涨日期列表'
    }
    '''
    """)
    
    print("\n演示完成!")


if __name__ == "__main__":
    demo_with_mock_data()