#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===================================
股票分时数据采集模块
===================================

功能：
1. 从 stock.csv 获取股票列表
2. 调用东方财富接口获取分时数据
3. 解析数据并生成指定格式的 JSON
4. 上传到 Gitee 仓库
"""

import os
import csv
import json
import requests
from datetime import datetime
from typing import List, Dict, Any
from urllib.parse import urlencode
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

import sys
import os
# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

try:
    from ..gitee_client import GiteeClient
except ImportError:
    from src.gitee_client import GiteeClient

# 全局变量用于限流控制
SUCCESS_COUNT = 0
MAX_SUCCESS_BEFORE_SLEEP = 100
def get_random_sleep_time():
    """获取随机休眠时间"""
    return random.randint(0, 5)

SLEEP_TIME = get_random_sleep_time()

# 东方财富服务器地址列表，用于轮询
EM_SERVERS = ['72', '74', '75', '76']
CURRENT_SERVER_INDEX = 0


def get_stock_list(stock_file: str = "../../sources/stock.csv", include_st: bool = True) -> List[Dict[str, str]]:
    """
    从 CSV 文件读取股票列表
    
    Args:
        stock_file: 股票列表文件路径
        include_st: 是否包含ST股，默认为True
        
    Returns:
        股票列表，每个元素包含 code 和 name
    """
    stocks = []
    abs_path = os.path.join(os.path.dirname(__file__), stock_file)
    with open(abs_path, 'r', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            if len(row) >= 2:
                code_with_suffix = row[0].strip()
                name = row[1].strip()
                # 提取纯股票代码
                code = code_with_suffix.replace('.SS', '').replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
                
                # 根据include_st参数决定是否过滤ST股
                is_st_stock = 'ST' in name or '*' in name  # 包含ST或*的股票通常为ST股
                
                if include_st or not is_st_stock:
                    stocks.append({
                        'code': code,
                        'name': name,
                        'code_with_suffix': code_with_suffix
                    })
    return stocks


def get_secid(code: str) -> str:
    """
    根据股票代码生成 secid
    
    Args:
        code: 纯股票代码
        
    Returns:
        secid 格式为 market.code
    """
    market = '1' if code.startswith('6') else '0'
    return f"{market}.{code}"


def fetch_stock_trend(secid: str) -> Dict[str, Any]:
    """
    调用东方财富接口获取股票分时数据（SSE流式接口）
    
    Args:
        secid: 股票标识符，格式为 market.code
        
    Returns:
        接口返回的 JSON 数据
    """
    global SUCCESS_COUNT, CURRENT_SERVER_INDEX, SLEEP_TIME
    
    params = {
        'fields1': 'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13,f17',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58',
        'mpi': '1000',
        'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
        'secid': secid,
        'ndays': '1',
        'iscr': '1',
        'iscca': '0',
        'wbp2u': '|0|0|0|web'
    }
    
    # 检查是否需要休眠以遵守限流规则
    if SUCCESS_COUNT >= MAX_SUCCESS_BEFORE_SLEEP:
        print(f"⏳ 达到 {MAX_SUCCESS_BEFORE_SLEEP} 次成功请求，休眠 {SLEEP_TIME} 秒...")
        time.sleep(SLEEP_TIME)
        SLEEP_TIME = get_random_sleep_time()  # 重置为新的随机休眠时间
        SUCCESS_COUNT = 0  # 重置计数器
    
    # 创建一个 session 来保持连接和 cookies
    with requests.Session() as session:
        # 设置请求头，模拟浏览器请求
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://quote.eastmoney.com/',
            'Origin': 'https://quote.eastmoney.com',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        }
        session.headers.update(headers)
        
        # 设置 cookies，模拟真实浏览器（动态生成时间相关字段）
        current_time = datetime.now().strftime('%m-%d %H:%M:%S')
        current_timestamp = int(datetime.now().timestamp() * 1000)  # 毫秒时间戳
        
        cookies = {
            'qgqp_b_id': '820136620dde35d4a6c945daa067e717',
            'st_nvi': 'GoVIGqItgHb0W-hK8e0im3143',
            'nid18': '0d5ade1b857e70b05b317936f9c6fdbf',
            'nid18_create_time': str(current_timestamp - 86400000),  # 一天前的时间戳
            'gviem': '5ZJYgmh93PMmquf98jnU6c97d',
            'gviem_create_time': str(current_timestamp - 86400000),  # 一天前的时间戳
            'ct': 'O7Mn9Bm9QUEnyVYwBCQEuVvnPtKpYfh7W1hKmCN151La4sxpsjaI3sgZjs5Muge7hAhCU0WbO4Raaa-njsmqaJdkYUdNvm0ycXmDBCyra5mwQlb3DBv8WCaC3if4b-itK_KAlLS6HdxXhfHf59K5NWgmEJ8QUXpCM1s08hjPh1Q',
            'ut': 'FobyicMgeV5mv3_J9jItPJvNHbAxfZ4lzNz3DZ1a8fFNYnjKkLRSWDoojp5znOY5bleq5XG_Kcdmgtl829iH0qyMOvsu99-DF_LNsVoNam7rTovjK9Wf-xemztNlC1r7HoSK1nt30iUXtFOYNcyDQ-_IPPXeaKw09iZTFnFVm6Ti8ljt7xHGoi57ZRwD1t5HT9W4BOFNWa_XqoPvVsGVFfPu_qBpcByjKL0akZ-jfDTGXLGPP7V0Q64D7c9Tf_dwOjj0d4nD9DhSk6TxgupRkQ',
            'EMFUND9': f'{current_time}@#$%u6C38%u8D62%u79D1%u6280%u667A%u9009%u6DF7%u5408%u53D1%u8D77A@%23%24022364',  # 使用当前时间
            'emshistory': '%5B%22%E5%8C%96%E5%B7%A5%22%2C%22%E5%9B%BE%E7%BB%B4%E7%A7%91%E6%8A%80%22%5D',
            'st_si': '41860741402522',
            'fullscreengg': '1',
            'fullscreengg2': '1',
            'st_asi': 'delete',
            'st_pvi': '13250660090205',
            'st_sp': '2025-12-07%2011%3A46%3A52',
            'st_inirUrl': 'https%3A%2F%2Fwww.eastmoney.com%2F',
            'st_sn': '8',
            'st_psi': f'{current_timestamp}-113200301201-9382295628'  # 使用当前时间戳
        }
        session.cookies.update(cookies)
        
        # 尝试轮询不同的服务器地址
        for i in range(len(EM_SERVERS)):
            # 获取当前服务器地址
            server_num = EM_SERVERS[CURRENT_SERVER_INDEX]
            base_url = f"https://{server_num}.push2.eastmoney.com/api/qt/stock/trends2/sse"
            url = f"{base_url}?{urlencode(params)}"
            
            try:
                # 使用 session 发送流式请求处理 SSE 接口
                response = session.get(url, stream=True, timeout=30)
                response.raise_for_status()
                
                # 逐行读取 SSE 数据
                for line in response.iter_lines(decode_unicode=True):
                    if line:
                        # SSE 数据通常以 data: 开头，但这里可能直接返回 JSON
                        line = line.strip()
                        if line.startswith('data: '):
                            line = line[6:]  # 移除 'data: ' 前缀
                        elif line.startswith(':'):  # 忽略注释行
                            continue
                        
                        if line.startswith('{') and line.endswith('}'):
                            try:
                                json_data = json.loads(line)
                                SUCCESS_COUNT += 1  # 成功获取数据，增加计数器
                                
                                # 成功后切换到下一个服务器
                                CURRENT_SERVER_INDEX = (CURRENT_SERVER_INDEX + 1) % len(EM_SERVERS)
                                
                                return json_data
                            except json.JSONDecodeError:
                                continue
                
                # 如果当前服务器无数据，尝试下一个服务器
                print(f"⚠️ 服务器 {server_num} 无响应，尝试下一个服务器")
                CURRENT_SERVER_INDEX = (CURRENT_SERVER_INDEX + 1) % len(EM_SERVERS)
                
            except Exception as e:
                print(f"⚠️ 服务器 {server_num} 请求失败: {e}，尝试下一个服务器")
                CURRENT_SERVER_INDEX = (CURRENT_SERVER_INDEX + 1) % len(EM_SERVERS)
    
    # 所有服务器都尝试过了还是失败
    print("❌ 所有服务器都尝试过了，请求失败")
    # 重置计数器，避免因错误影响后续请求
    SUCCESS_COUNT = 0
    return {}


def parse_trend_data(trend_str: str) -> Dict[str, Any]:
    """
    解析单条分时数据字符串
    
    Args:
        trend_str: 分时数据字符串，格式为 "YYYY-MM-DD HH:MM,open,high,low,close,volume,turnover,avgPrice"
        
    Returns:
        解析后的数据字典
    """
    parts = trend_str.split(',')
    if len(parts) < 8:
        return {}
    
    # 按照接口返回格式: date, open, close, high, low, volume, turnover, avgPrice
    # 根据文档，只需要 close, volume, turnover, avgPrice 四个字段
    date_time, open_price, close, high, low, volume, turnover, avg_price = parts[0:8]
    
    return {
        "close": float(close) if close != "None" else 0.0,
        "volume": int(volume) if volume != "None" else 0,
        "turnover": float(turnover) if turnover != "None" else 0.0,
        "avgPrice": float(avg_price) if avg_price != "None" else 0.0
    }


def process_stock_data(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理单个股票的原始数据，提取有用信息
    
    Args:
        raw_data: 从接口获取的原始数据
        
    Returns:
        处理后的股票数据
    """
    if not raw_data.get('data'):
        return {}
        
    data = raw_data['data']
    result = {
        "code": data.get("code", ""),
        "name": data.get("name", ""),
        "preClose": data.get("preClose", 0.0),
    }
    
    # 解析分时数据，根据文档要求处理集合竞价数据
    trends = data.get("trends", [])
    if trends and len(trends) > 1:
        # 查找时间为9:26的数据作为9:25集合竞价结果
        trend_925 = None
        for trend in trends:
            # 检查时间部分是否为9:26（可能是 09:26 或 9:26）
            if ' 09:26,' in trend or ' 9:26,' in trend:
                trend_925 = parse_trend_data(trend)
                break
        
        # 如果没找到9:26的数据，则使用第二条数据作为备用
        if not trend_925:
            trend_925 = parse_trend_data(trends[1])
        
        if trend_925:
            result["925"] = trend_925
    
    return result


def get_processed_stocks_from_gitee(filename: str) -> List[Dict[str, Any]]:
    """
    从 Gitee 获取已处理的股票数据
    
    Args:
        filename: 文件名
        
    Returns:
        已处理的股票数据列表
    """
    try:
        client = GiteeClient()
        remote_path = f"klines/{filename}"
        content = client.get_file_content(remote_path)
        
        if content:
            data = json.loads(content)
            print(f"✅ 从 Gitee 获取到 {len(data)} 条已处理的股票数据")
            return data
        else:
            print("⚠️ Gitee 上未找到历史数据，将重新开始处理")
            return []
    except Exception as e:
        print(f"⚠️ 从 Gitee 获取历史数据失败: {e}，将重新开始处理")
        return []


def collect_all_stocks_trends(stocks: List[Dict[str, str]], processed_stocks: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    收集所有股票的分时数据
    
    Args:
        stocks: 股票列表
        processed_stocks: 已处理的股票数据列表（用于断点续传）
        
    Returns:
        所有股票的分时数据列表
    """
    results = []
    # 如果提供了已处理的数据，则先添加这些数据
    if processed_stocks:
        results.extend(processed_stocks)
        print(f"📊 已加载 {len(processed_stocks)} 条已处理的数据")
    
    # 找出尚未处理的股票
    processed_codes = {stock['code'] for stock in processed_stocks or []}
    remaining_stocks = [stock for stock in stocks if stock['code'] not in processed_codes]
    
    total = len(remaining_stocks)
    if total == 0:
        print("✅ 所有股票均已处理完毕")
        return results
    
    print(f"📊 需要处理 {total} 只未处理的股票")
    
    # 按股票代码首位数字分组
    grouped_stocks = {}
    for stock in remaining_stocks:
        first_digit = stock['code'][0] if stock['code'] else '0'
        if first_digit not in grouped_stocks:
            grouped_stocks[first_digit] = []
        grouped_stocks[first_digit].append(stock)
    
    print(f"📊 按首位数字分组完成，共 {len(grouped_stocks)} 个分组")
    
    # 创建锁和共享数据结构用于线程间通信
    import threading
    results_lock = threading.Lock()
    all_results = []
    upload_counter = {'count': 0}  # 使用字典便于在嵌套函数中修改
    
    def process_stock_group_with_upload(stocks_group: List[Dict[str, str]], group_name: str, client: GiteeClient):
        """
        处理单个股票分组并实时上传数据
        
        Args:
            stocks_group: 股票分组
            group_name: 分组名称（用于显示）
            client: Gitee客户端实例
        """
        group_results = []
        
        for i, stock in enumerate(stocks_group):
            print(f"[{group_name}] 🔄 正在获取 {stock['name']} ({stock['code']}) 分时数据 [{i+1}/{len(stocks_group)}]")
            
            secid = get_secid(stock['code'])
            raw_data = fetch_stock_trend(secid)
            
            if raw_data:
                processed_data = process_stock_data(raw_data)
                if processed_data:
                    group_results.append(processed_data)
                    print(f"[{group_name}] ✅ {stock['name']} 数据获取成功")
                    
                    # 将数据添加到共享结果列表
                    with results_lock:
                        all_results.append(processed_data)
                        upload_counter['count'] += 1
                        
                        # 每达到100条数据就上传一次Gitee
                        if upload_counter['count'] >= 100:
                            print(f"📈 已累计 {upload_counter['count']} 条数据，上传到Gitee...")
                            current_date = datetime.now().strftime("%Y%m%d")
                            temp_filename = f"{current_date}_集合竞价_临时_{upload_counter['count']}.json"
                            temp_file_path = save_to_json(all_results.copy(), temp_filename)
                            
                            temp_remote_path = f"klines/{temp_filename}"
                            client.upload_file(temp_file_path, temp_remote_path, message=f"临时保存分时数据: {temp_filename}")
                            print(f"💾 已成功保存 {upload_counter['count']} 条临时数据到 Gitee")
                            
                            # 重置计数器
                            upload_counter['count'] = 0
                else:
                    print(f"[{group_name}] ⚠️ {stock['name']} 数据处理失败")
            else:
                print(f"[{group_name}] ❌ {stock['name']} 数据获取失败")
        
        return group_results
    
    # 为每个分组启动线程
    with ThreadPoolExecutor(max_workers=len(grouped_stocks)) as executor:
        client = GiteeClient()  # 创建Gitee客户端实例
        
        futures = {}
        for digit, stocks_group in grouped_stocks.items():
            future = executor.submit(process_stock_group_with_upload, stocks_group, digit, client)
            futures[future] = digit
        
        # 处理完成的任务和异常
        for future in as_completed(futures):
            digit = futures[future]
            try:
                group_results = future.result()
                print(f"✅ 分组 {digit} 处理完成")
            except Exception as e:
                print(f"⚠️ 分组 {digit} 处理过程中发生错误: {e}")
                
                # 出现异常时，立即上传已有的数据
                with results_lock:
                    if all_results:
                        print(f"🚨 发生异常，立即上传已处理的 {len(all_results)} 条数据到Gitee...")
                        current_date = datetime.now().strftime("%Y%m%d")
                        temp_filename = f"{current_date}_集合竞价_异常保存_{len(all_results)}.json"
                        temp_file_path = save_to_json(all_results.copy(), temp_filename)
                        
                        temp_remote_path = f"klines/{temp_filename}"
                        client.upload_file(temp_file_path, temp_remote_path, message=f"异常保存分时数据: {temp_filename}")
                        print(f"💾 已成功保存 {len(all_results)} 条异常数据到 Gitee")
                
                # 休眠1分钟后再继续
                print("⏳ 发生异常，休眠1分钟...")
                time.sleep(60)
    
    # 添加剩余数据（少于100条的部分）
    results.extend(all_results)
    
    return results


def extract_st_stocks_data(all_stocks_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    从所有股票数据中提取ST股票的数据
    
    Args:
        all_stocks_data: 所有股票的数据列表
        
    Returns:
        ST股票的数据列表
    """
    st_stocks = []
    for stock_data in all_stocks_data:
        name = stock_data.get('name', '')
        # 判断是否为ST股票（名称中包含ST或*）
        if 'ST' in name or '*' in name:
            st_stocks.append(stock_data)
    
    print(f"筛选出 {len(st_stocks)} 只ST股票数据")
    return st_stocks


def save_to_json(data: List[Dict[str, Any]], filename: str):
    """
    将数据保存为 JSON 文件
    
    Args:
        data: 要保存的数据
        filename: 文件名
    """
    # 创建保存目录
    save_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "klines")
    os.makedirs(save_dir, exist_ok=True)
    
    file_path = os.path.join(save_dir, filename)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 数据已保存到: {file_path}")
    return file_path


def main():
    """
    主函数
    """
    print("=" * 60)
    print("📊 开始采集股票分时数据")
    print("=" * 60)
    
    try:
        # 1. 生成文件名（使用当前日期）
        current_date = datetime.now().strftime("%Y%m%d")
        filename = f"{current_date}_集合竞价.json"
        st_filename = f"{current_date}_ST集合竞价.json"
        
        # 2. 尝试从 Gitee 获取已处理的数据（断点续传）
        print("🔄 检查 Gitee 上的已处理数据...")
        existing_data = get_processed_stocks_from_gitee(filename)
        
        # 3. 获取股票列表
        print("📋 正在读取股票列表...")
        stocks = get_stock_list(include_st=True)  # 只获取ST股票
        print(f"✅ 共获取到 {len(stocks)} 只股票")
        
        # 4. 收集所有股票的分时数据（支持断点续传）
        print("🔄 正在收集分时数据...")
        all_stocks_data = collect_all_stocks_trends(stocks, existing_data)
        
        # 5. 提取ST股票数据
        print("🔍 正在提取ST股票数据...")
        st_stocks_data = extract_st_stocks_data(all_stocks_data)
        
        # 6. 保存所有股票数据到本地
        file_path = save_to_json(all_stocks_data, filename)
        
        # 7. 保存ST股票数据到本地
        if st_stocks_data:
            st_file_path = save_to_json(st_stocks_data, st_filename)
            
        # 8. 上传到 Gitee
        print("📤 正在上传到 Gitee 仓库...")
        client = GiteeClient()
        remote_path = f"klines/{filename}"
        success = client.upload_file(file_path, remote_path, message=f"更新分时数据: {filename}")
        
        # 上传ST股票数据到 Gitee
        if st_stocks_data:
            st_remote_path = f"klines/{st_filename}"
            st_success = client.upload_file(st_file_path, st_remote_path, message=f"更新ST股票分时数据: {st_filename}")
        
        if success:
            print("=" * 60)
            print("🎉 任务完成！分时数据已成功上传到 Gitee")
            print("=" * 60)
        else:
            print("=" * 60)
            print("⚠️ 任务完成，但上传到 Gitee 失败")
            print("=" * 60)
        
        return 0
    
    except Exception as e:
        print(f"=" * 60)
        print(f"❌ 任务失败: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 60)
        return 1


if __name__ == "__main__":
    exit(main())
