#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===================================
每日涨停数据抓取模块
===================================

功能：
1. 从 Gitee limitup 目录查询最近一次采集时间
2. 从选股宝接口获取每日历史涨停数据
3. 将响应报文转换成中文字段描述的JSON格式
4. 每日采集完成后 zip 压缩并上传到 Gitee limitup 目录，格式：年月日.zip（如 20260203.zip），压缩包内文件名为年月日.json

接口：
http://flash-api.xuangubao.cn/api/pool/detail?pool_name=limit_up&date=YYYY-MM-DD
"""

import zipfile
import json
import os
import re
import sys
import tempfile
import requests
from datetime import datetime, timedelta
from typing import Any

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
try:
    from gitee_client import GiteeClient
except ImportError:
    GiteeClient = None

# 配置项
API_BASE_URL = "http://flash-api.xuangubao.cn/api/pool/detail"
LIMITUP_REMOTE = "limitup"
DEFAULT_START_DATE = datetime(2022, 1, 1)
FILENAME_PATTERN = re.compile(r"^(\d{8})\.zip$")

# 英文字段到中文字段的映射
FIELD_MAPPING = {
    "symbol": "股票代码",
    "stock_chi_name": "股票中文名称",
    "is_new_stock": "是否新股",
    "listed_date": "上市日期",
    "issue_price": "发行价格",
    "price": "当前价格",
    "prev_close_price": "前收盘价",
    "change_percent": "涨跌幅",
    "break_limit_up_times": "打开涨停次数",
    "break_limit_down_times": "打开跌停次数",
    "limit_up_days": "连续涨停天数",
    "limit_down_days": "连续跌停天数",
    "first_break_limit_up": "首次打开涨停时间",
    "first_break_limit_down": "首次打开跌停时间",
    "first_limit_up": "首次涨停时间",
    "first_limit_down": "首次跌停时间",
    "last_break_limit_up": "最后打开涨停时间",
    "last_break_limit_down": "最后打开跌停时间",
    "last_limit_up": "最后涨停时间",
    "last_limit_down": "最后跌停时间",
    "yesterday_break_limit_up_times": "昨日打开涨停次数",
    "yesterday_first_limit_up": "昨日首次涨停时间",
    "yesterday_last_limit_up": "昨日最后涨停时间",
    "yesterday_limit_up_days": "昨日连续涨停天数",
    "yesterday_limit_down_days": "昨日连续跌停天数",
    "total_capital": "总股本",
    "non_restricted_capital": "流通股本",
    "turnover_ratio": "换手率",
    "volume_bias_ratio": "量比",
    "buy_lock_volume_ratio": "买入锁仓比例",
    "sell_lock_volume_ratio": "卖出锁仓比例",
    "new_stock_acc_pcp": "新股累计涨跌幅",
    "new_stock_break_limit_up": "新股打开涨停次数",
    "new_stock_limit_up_days": "新股连续涨停天数",
    "new_stock_limit_up_price_before_broken": "新股开板前价格",
    "nearly_new_acc_pcp": "次新股累计涨跌幅",
    "nearly_new_break_days": "次新股开板天数",
    "m_days_n_boards_days": "M天N板_天数M",
    "m_days_n_boards_boards": "M天N板_板数N",
    "mtm": "动量指标",
}

# 需要将时间戳转换为可读文本的字段
TIMESTAMP_FIELDS = {
    "listed_date",
    "first_break_limit_up",
    "first_break_limit_down",
    "first_limit_up",
    "first_limit_down",
    "last_break_limit_up",
    "last_break_limit_down",
    "last_limit_up",
    "last_limit_down",
    "yesterday_first_limit_up",
    "yesterday_last_limit_up",
}


def _timestamp_to_text(value: Any) -> str:
    """将时间戳转换为可读文本，0 或 None 返回空字符串"""
    if value is None or value == 0:
        return ""
    try:
        ts = int(value)
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError):
        return str(value)


def _convert_surge_reason(surge_reason: dict | None) -> tuple[str, str, str]:
    """
    从 surge_reason 中提取个股涨停原因、关联板块名称、板块上涨原因
    返回: (个股涨停原因, 关联板块名称, 板块上涨原因)
    """
    if not surge_reason:
        return "", "", ""

    stock_reason = surge_reason.get("stock_reason", "") or ""
    related_plates = surge_reason.get("related_plates", []) or []

    plate_names = []
    plate_reasons = []
    for plate in related_plates:
        if isinstance(plate, dict):
            plate_names.append(plate.get("plate_name", ""))
            plate_reasons.append(plate.get("plate_reason", ""))

    return (
        stock_reason,
        "; ".join(filter(None, plate_names)),
        "; ".join(filter(None, plate_reasons)),
    )


def convert_to_chinese_format(item: dict) -> dict:
    """
    将单条涨停数据的英文字段转换为中文字段格式

    Args:
        item: 接口返回的单条涨停数据（英文字段）

    Returns:
        dict: 中文字段格式的数据
    """
    result = {}

    for en_key, zh_key in FIELD_MAPPING.items():
        value = item.get(en_key)

        if en_key in TIMESTAMP_FIELDS:
            result[zh_key] = _timestamp_to_text(value)
        else:
            result[zh_key] = value

    # 处理 surge_reason 中的嵌套字段
    surge_reason = item.get("surge_reason")
    stock_reason, plate_names, plate_reasons = _convert_surge_reason(surge_reason)
    result["个股涨停原因"] = stock_reason
    result["关联板块名称"] = plate_names
    result["板块上涨原因"] = plate_reasons

    return result


def fetch_limit_up_data(date: str) -> dict:
    """
    从选股宝接口获取指定日期的涨停数据

    Args:
        date: 日期，格式 YYYY-MM-DD，如 2025-11-06

    Returns:
        dict: 接口返回的原始JSON数据
    """
    params = {"pool_name": "limit_up", "date": date}
    try:
        response = requests.get(API_BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 20000:
            raise ValueError(f"接口返回错误: {data.get('message', '未知错误')}")
        return data
    except requests.RequestException as e:
        raise RuntimeError(f"请求涨停数据失败: {e}") from e


def fetch_and_convert(date: str | None = None) -> list[dict]:
    """
    获取每日涨停数据并转换为中文字段格式

    Args:
        date: 日期，格式 YYYY-MM-DD。不传则使用当前日期

    Returns:
        list[dict]: 中文字段格式的涨停数据列表
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    raw_data = fetch_limit_up_data(date)
    items = raw_data.get("data", [])

    if not isinstance(items, list):
        return []

    converted = [convert_to_chinese_format(item) for item in items]
    print(f"[OK] 成功获取 {date} 涨停数据，共 {len(converted)} 条")
    return converted


def get_latest_collection_date(client: GiteeClient) -> datetime | None:
    """
    从 Gitee limitup 目录查询最近一次采集的日期

    Returns:
        最近日期，格式为 datetime；若无文件则返回 None
    """
    files = client.list_directory(LIMITUP_REMOTE)
    dates = []
    for f in files:
        name = f.get("name", "")
        m = FILENAME_PATTERN.match(name)
        if m:
            try:
                dt = datetime.strptime(m.group(1), "%Y%m%d")
                dates.append(dt)
            except ValueError:
                pass
    return max(dates) if dates else None


def determine_collection_range(client: GiteeClient) -> tuple[datetime, datetime]:
    """
    确定采集的日期范围

    Returns:
        (start_date, end_date)：均为 datetime，含首尾
    """
    end_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    latest = get_latest_collection_date(client)
    if latest is None:
        start_date = DEFAULT_START_DATE
        print(f"limitup 目录无历史数据，从 {start_date.strftime('%Y-%m-%d')} 开始采集")
    else:
        start_date = latest + timedelta(days=1)
        print(f"最近采集日期: {latest.strftime('%Y-%m-%d')}，从 {start_date.strftime('%Y-%m-%d')} 开始采集")
    return start_date, end_date


def collect_and_upload_single_day(
    client: GiteeClient,
    dt: datetime,
) -> bool:
    """
    采集单日涨停数据，zip 压缩后上传到 Gitee。
    压缩包格式：年月日.zip，内含年月日.json。

    Returns:
        是否成功
    """
    date_str = dt.strftime("%Y-%m-%d")
    file_date = dt.strftime("%Y%m%d")
    remote_filename = f"{file_date}.zip"
    inner_json_name = f"{file_date}.json"

    try:
        data = fetch_and_convert(date_str)
    except Exception as e:
        print(f"[WARN] {date_str} 采集失败: {e}，跳过")
        return False

    if not data:
        print(f"[SKIP] {date_str} 数据为空，不生成文件")
        return True  # 视为成功跳过，不计入失败

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".zip",
            delete=False,
        ) as f:
            temp_path = f.name

        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            zf.writestr(inner_json_name, json_bytes)

        remote_path = f"{LIMITUP_REMOTE}/{remote_filename}"
        success = client.upload_binary_file(temp_path, remote_path, message=f"涨停数据 {date_str}")
        return success
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def run_collection_cycle(repo: str = "qymmdj/stockdb") -> int:
    """
    执行完整采集流程：查询 Gitee 确定范围，逐日采集并上传

    Returns:
        0 成功，1 失败
    """
    if GiteeClient is None:
        print("[ERROR] 无法导入 GiteeClient，请检查 gitee_client 模块")
        return 1

    client = GiteeClient(repo=repo)
    start_date, end_date = determine_collection_range(client)

    if start_date > end_date:
        print("无需采集，数据已是最新")
        return 0

    total = 0
    success = 0
    current = start_date
    while current <= end_date:
        total += 1
        if collect_and_upload_single_day(client, current):
            success += 1
        current += timedelta(days=1)

    print("=" * 60)
    print(f"采集完成: 共 {total} 天，成功 {success} 天")
    print("=" * 60)
    return 0 if success == total else 1


def main():
    """主函数：执行涨停数据采集并上传到 Gitee"""
    print("=" * 60)
    print("每日涨停数据抓取")
    print("=" * 60)

    # 支持命令行指定单日模式（兼容旧用法）
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print("用法: python limit_up.py [日期]")
        print("  无参数: 从 Gitee 查询最近采集时间，增量采集并上传")
        print("  日期: 仅采集指定日期并输出 JSON，格式 YYYY-MM-DD")
        return 0

    if len(sys.argv) > 1:
        # 单日模式：仅采集并输出 JSON
        date = sys.argv[1]
        try:
            result = fetch_and_convert(date)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except Exception as e:
            print(f"[ERROR] 失败: {e}")
            return 1

    # 默认：增量采集并上传
    try:
        return run_collection_cycle()
    except Exception as e:
        print(f"[ERROR] 失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
