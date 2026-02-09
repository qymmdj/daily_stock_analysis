#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===================================
热点题材数据采集与上传模块
===================================

功能：
1. 从选股宝接口获取热点题材数据
2. 将数据保存为JSON文件
3. 上传到Gitee仓库

接口：
https://flash-api.xuangubao.com.cn/api/surge_stock/stocks?normal=true&uplimit=true

上传路径：
qymmdj1211/stockdb/hotsubject/YYYYMMDD.json
"""

import os
import json
import requests
from datetime import datetime

# 配置项
API_URL = "https://flash-api.xuangubao.com.cn/api/surge_stock/stocks?normal=true&uplimit=true"


def fetch_hot_subject_data() -> dict:
    """
    从选股宝接口获取热点题材数据
    
    Returns:
        dict: 接口返回的JSON数据
    """
    try:
        response = requests.get(API_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        print(f"✅ 成功获取热点题材数据，共 {len(data.get('data', {}).get('items', []))} 条")
        return data
    except Exception as e:
        print(f"❌ 获取热点题材数据失败: {e}")
        raise


def generate_file_name(data: dict) -> str:
    """
    生成文件名，格式为 YYYYMMDD.json
    从数据中的 enter_time 时间戳获取日期
    
    Args:
        data: 接口返回的JSON数据
    
    Returns:
        str: 文件名
    """
    try:
        items = data.get('data', {}).get('items', [])
        if items and len(items) > 0:
            enter_time = items[0][6]
            file_date = datetime.fromtimestamp(enter_time).strftime("%Y%m%d")
            return f"{file_date}.json"
        else:
            today = datetime.now().strftime("%Y%m%d")
            return f"{today}.json"
    except Exception as e:
        print(f"⚠️ 从 enter_time 生成文件名失败，使用当前日期: {e}")
        today = datetime.now().strftime("%Y%m%d")
        return f"{today}.json"


def save_to_local(data: dict, file_name: str) -> str:
    """
    将数据保存到本地JSON文件
    
    Args:
        data: 要保存的数据
        file_name: 文件名
    
    Returns:
        str: 保存的文件路径
    """
    # 创建保存目录
    save_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "hotsubject")
    os.makedirs(save_dir, exist_ok=True)
    
    # 保存文件
    file_path = os.path.join(save_dir, file_name)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 数据已保存到本地: {file_path}")
    return file_path


import sys
import os
# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

try:
    from ..gitee_client import upload_to_gitee
except ImportError:
    from gitee_client import upload_to_gitee


def main():
    """
    主函数
    """
    print("=" * 60)
    print("📊 热点题材数据采集与上传")
    print("=" * 60)
    
    try:
        # 1. 获取数据
        data = fetch_hot_subject_data()
        
        # 2. 生成文件名（从 enter_time 时间戳获取日期）
        file_name = generate_file_name(data)
        
        # 3. 保存到本地
        file_path = save_to_local(data, file_name)
        
        # 4. 上传到Gitee
        success = upload_to_gitee(file_path, file_name, remote_path="hotsubject", repo="qymmdj/stockdb")
        
        if success:
            print("=" * 60)
            print("🎉 任务完成！热点题材数据已成功上传到Gitee")
            print("=" * 60)
        else:
            print("=" * 60)
            print("⚠️ 任务完成，但上传到Gitee失败")
            print("=" * 60)
            
    except Exception as e:
        print(f"=" * 60)
        print(f"❌ 任务失败: {e}")
        print("=" * 60)
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
