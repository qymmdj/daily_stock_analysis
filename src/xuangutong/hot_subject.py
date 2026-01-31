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
import base64
from datetime import datetime

# 配置项
API_URL = "https://flash-api.xuangubao.com.cn/api/surge_stock/stocks?normal=true&uplimit=true"
GITEE_REPO = "qymmdj/stockdb"
GITEE_PATH = "hotsubject"
GITEE_TOKEN = os.getenv("GITEE_TOKEN", "")


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


def upload_to_gitee(file_path: str, file_name: str) -> bool:
    """
    将文件上传到Gitee仓库
    
    Args:
        file_path: 本地文件路径
        file_name: 文件名
    
    Returns:
        bool: 上传是否成功
    """
    try:
        # 读取文件内容
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Gitee API 上传文件接口
        upload_url = f"https://gitee.com/api/v5/repos/{GITEE_REPO}/contents/{GITEE_PATH}/{file_name}"
        
        # 构建请求数据
        data = {
            "access_token": GITEE_TOKEN,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),  # 内容需要base64编码
            "message": f"更新热点题材数据: {file_name}",
            "branch": "master"  # 指定分支
        }
        
        # 发送请求
        headers = {
            "Content-Type": "application/json"
        }
        
        # 尝试上传（如果路径不存在，Gitee API会自动创建）
        response = requests.post(upload_url, json=data, headers=headers, timeout=60)
        
        # 打印详细的响应信息以便调试
        print(f"📡 Gitee API 响应状态码: {response.status_code}")
        print(f"📡 Gitee API 响应内容: {response.text}")
        
        # 处理可能的错误
        if response.status_code == 404:
            print(f"❌ Gitee仓库或路径不存在: {GITEE_REPO}/{GITEE_PATH}")
            print("请检查：")
            print("1. Gitee仓库是否存在")
            print("2. Token是否有正确的权限")
            print("3. 路径格式是否正确")
            return False
        elif response.status_code == 401:
            print("❌ Gitee Token无效或权限不足")
            return False
        elif response.status_code == 422:
            print("❌ Gitee API 请求参数错误")
            return False
        
        response.raise_for_status()
        
        print(f"✅ 数据已上传到Gitee: {GITEE_REPO}/{GITEE_PATH}/{file_name}")
        return True
        
    except Exception as e:
        print(f"❌ 上传到Gitee失败: {e}")
        import traceback
        traceback.print_exc()
        return False


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
        success = upload_to_gitee(file_path, file_name)
        
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
