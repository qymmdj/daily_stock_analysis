#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===================================
Gitee API 客户端模块
===================================

功能：
1. 提供统一的 Gitee API 操作接口
2. 支持文件上传、下载、更新等操作
"""

import os
import json
import requests
import base64
from typing import Optional


class GiteeClient:
    """
    Gitee API 客户端类
    用于处理与 Gitee 仓库的各种交互操作
    """

    def __init__(self, token: Optional[str] = None, repo: Optional[str] = None):
        """
        初始化 Gitee 客户端
        
        Args:
            token: Gitee 访问令牌，默认从环境变量 GITEE_TOKEN 获取
            repo: Gitee 仓库名称，默认格式为 "username/repo"
        """
        self.token = token or os.getenv("GITEE_TOKEN", "862a28ae7934e3e9963b5d4f76a07013")
        self.repo = repo or os.getenv("GITEE_REPO", "qymmdj/stockdb")
        self.base_url = "https://gitee.com/api/v5"

    def upload_file(self, file_path: str, remote_path: str, branch: str = "master", message: str = None) -> bool:
        """
        上传文件到 Gitee 仓库
        
        Args:
            file_path: 本地文件路径
            remote_path: 远程文件路径（相对于仓库根目录）
            branch: 分支名称，默认为 master
            message: 提交消息
            
        Returns:
            bool: 上传是否成功
        """
        try:
            # 读取文件内容
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            if not message:
                message = f"更新文件: {os.path.basename(file_path)}"
            
            # 构建 API URL
            upload_url = f"{self.base_url}/repos/{self.repo}/contents/{remote_path}"
            
            # 构建请求数据
            data = {
                "access_token": self.token,
                "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),  # 内容需要base64编码
                "message": message,
                "branch": branch
            }
            
            # 设置请求头
            headers = {
                "Content-Type": "application/json"
            }
            
            # 首先尝试获取文件信息，如果存在则获取SHA值用于更新
            file_info_url = f"{self.base_url}/repos/{self.repo}/contents/{remote_path}?access_token={self.token}&ref={branch}"
            file_response = requests.get(file_info_url)
                        
            # 根据文件是否存在决定使用哪种方法
            if file_response.status_code == 200:
                # 文件已存在，获取SHA值用于更新
                file_info_response = file_response.json()
                # 检查返回的是单个文件还是文件列表
                sha = ''
                if isinstance(file_info_response, dict):
                    # 单个文件
                    sha = file_info_response.get('sha', '')
                elif isinstance(file_info_response, list) and len(file_info_response) > 0:
                    # 文件列表，查找匹配的文件
                    for item in file_info_response:
                        if item.get('name') == os.path.basename(remote_path):
                            sha = item.get('sha', '')
                            break
                            
                if sha:
                    data['sha'] = sha
                    # 使用PUT请求更新现有文件
                    response = requests.put(upload_url, json=data, headers=headers, timeout=60)
                else:
                    # 如果没有获取到SHA但文件响应是200，可能有其他情况，使用POST创建
                    response = requests.post(upload_url, json=data, headers=headers, timeout=60)
            else:
                # 文件不存在，使用POST创建新文件
                response = requests.post(upload_url, json=data, headers=headers, timeout=60)
            
            # 打印详细的响应信息以便调试
            print(f"📡 Gitee API 响应状态码: {response.status_code}")
            if response.status_code != 201 and response.status_code != 200:
                print(f"📡 Gitee API 响应内容: {response.text}")
            
            # 处理可能的错误
            if response.status_code == 404:
                print(f"❌ Gitee仓库或路径不存在: {self.repo}/{remote_path}")
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
            elif response.status_code in [200, 201]:
                print(f"✅ 文件已上传到Gitee: {self.repo}/{remote_path}")
                return True
            else:
                print(f"❌ 上传失败，状态码: {response.status_code}")
                return False
                
        except FileNotFoundError:
            print(f"❌ 本地文件不存在: {file_path}")
            return False
        except Exception as e:
            print(f"❌ 上传到Gitee失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def upload_content(self, content: str, remote_path: str, branch: str = "master", message: str = None) -> bool:
        """
        直接上传内容到 Gitee 仓库
        
        Args:
            content: 要上传的内容
            remote_path: 远程文件路径（相对于仓库根目录）
            branch: 分支名称，默认为 master
            message: 提交消息
            
        Returns:
            bool: 上传是否成功
        """
        try:
            if not message:
                message = f"更新内容: {remote_path}"
            
            # 构建 API URL
            upload_url = f"{self.base_url}/repos/{self.repo}/contents/{remote_path}"
            
            # 构建请求数据
            data = {
                "access_token": self.token,
                "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),  # 内容需要base64编码
                "message": message,
                "branch": branch
            }
            
            # 设置请求头
            headers = {
                "Content-Type": "application/json"
            }
            
            # 发送请求
            response = requests.put(upload_url, json=data, headers=headers, timeout=60)
            
            # 打印详细的响应信息以便调试
            print(f"📡 Gitee API 响应状态码: {response.status_code}")
            if response.status_code != 201 and response.status_code != 200:
                print(f"📡 Gitee API 响应内容: {response.text}")
            
            # 处理可能的错误
            if response.status_code == 404:
                print(f"❌ Gitee仓库或路径不存在: {self.repo}/{remote_path}")
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
            elif response.status_code in [200, 201]:
                print(f"✅ 内容已上传到Gitee: {self.repo}/{remote_path}")
                return True
            else:
                print(f"❌ 上传失败，状态码: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ 上传到Gitee失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def file_exists(self, remote_path: str, branch: str = "master") -> bool:
        """
        检查远程文件是否存在
        
        Args:
            remote_path: 远程文件路径
            branch: 分支名称
            
        Returns:
            bool: 文件是否存在
        """
        try:
            url = f"{self.base_url}/repos/{self.repo}/contents/{remote_path}?access_token={self.token}&ref={branch}"
            response = requests.get(url, timeout=30)
            
            return response.status_code == 200
        except Exception:
            return False

    def get_file_content(self, remote_path: str, branch: str = "master") -> Optional[str]:
        """
        获取远程文件内容
            
        Args:
            remote_path: 远程文件路径
            branch: 分支名称
            
        Returns:
            Optional[str]: 文件内容，如果失败则返回 None
        """
        try:
            url = f"{self.base_url}/repos/{self.repo}/contents/{remote_path}?access_token={self.token}&ref={branch}"
            response = requests.get(url, timeout=30)
                
            if response.status_code == 200:
                data = response.json()
                if 'content' in data:
                    content = base64.b64decode(data['content']).decode('utf-8')
                    return content
            return None
        except Exception as e:
            print(f"❌ 获取文件内容失败: {e}")
            return None
    
    def download_file(self, remote_path: str, repo: str = None, branch: str = "master") -> Optional[str]:
        """
        下载远程文件内容
            
        Args:
            remote_path: 远程文件路径
            repo: 仓库名称，如果不提供则使用默认仓库
            branch: 分支名称
            
        Returns:
            Optional[str]: 文件内容，如果失败则返回 None
        """
        try:
            # 临时切换仓库（如果提供了新的仓库名称）
            original_repo = self.repo
            if repo:
                self.repo = repo
                
            url = f"{self.base_url}/repos/{self.repo}/contents/{remote_path}?access_token={self.token}&ref={branch}"
            response = requests.get(url, timeout=30)
                
            # 恢复原来的仓库设置
            self.repo = original_repo
                
            if response.status_code == 200:
                data = response.json()
                if 'content' in data:
                    content = base64.b64decode(data['content']).decode('utf-8')
                    return content
                else:
                    print(f"❌ 响应中没有文件内容: {remote_path}")
                    return None
            else:
                print(f"❌ 下载失败，状态码: {response.status_code}, URL: {url}")
                return None
        except Exception as e:
            print(f"❌ 下载文件失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    

def upload_to_gitee(file_path: str, file_name: str, remote_path: str = "hotsubject", repo: str = "qymmdj/stockdb", token: str = None) -> bool:
    """
    便捷函数：将文件上传到Gitee仓库
    
    Args:
        file_path: 本地文件路径
        file_name: 文件名
        remote_path: 远程路径
        repo: 仓库名称
        token: 访问令牌
        
    Returns:
        bool: 上传是否成功
    """
    client = GiteeClient(token=token, repo=repo)
    full_remote_path = f"{remote_path}/{file_name}" if remote_path else file_name
    return client.upload_file(file_path, full_remote_path)


if __name__ == "__main__":
    # 测试代码
    client = GiteeClient()
    print("Gitee Client 初始化完成")