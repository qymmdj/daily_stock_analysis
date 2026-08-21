#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===================================
消息题材采集分析模块
===================================

功能：
1. 从东方财富"东方视点"、华尔街见闻（美股/要闻/A股）等渠道采集消息
2. 大模型分析消息价值，只保留重要消息
3. 整理消息题材，形成消息题材库（重复消息合并为一条）
4. 找出消息关联个股，并用✨标注关联强度（最高5星，最低1星）
5. 结果以 JSON 格式上传到 Gitee news 目录

消息来源：
1. 东方财富 东方视点 https://finance.eastmoney.com/a/cdfsd.html
   （列表接口 np-listapi.eastmoney.com，栏目ID 366）
2. 华尔街见闻 美股 https://wallstreetcn.com/live/us-stock
3. 华尔街见闻 华尔街要闻 https://wallstreetcn.com/live/global
4. 华尔街见闻 A股 https://wallstreetcn.com/live/a-stock
   （快讯接口 api-one-wscn.awtmt.com）

Gitee 存储（qymmdj/stockdb 仓库 news 目录）：
- YYYYMMDDHHMM_new_subjects.json  题材文件（单一当前文件，文件名为最后生成时间）
  下次采集时先从 Gitee news 目录获取最近文件，以其时间作为采集起点；
  当前文件超过 500KB 时归档旧文件并新开
"""

import os
import sys
import re
import json
import glob
import time
import difflib
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# Windows 控制台/管道默认 GBK，emoji 输出会触发 UnicodeEncodeError，强制 UTF-8
for _stream in (sys.stdout, sys.stderr):
    if _stream and _stream.encoding and _stream.encoding.lower().replace('-', '') != 'utf8':
        try:
            _stream.reconfigure(encoding='utf-8')
        except Exception:
            pass

# 添加项目根目录到路径（src/qym/eastmoney/news -> 项目根需向上 4 级）
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
sys.path.insert(0, _PROJECT_ROOT)

try:
    from src.config import get_config
    from src.gitee_client import GiteeClient
except ImportError:
    from config import get_config
    from gitee_client import GiteeClient

# ===================================
# 常量配置
# ===================================

# 数据保存目录：项目根/data/news_subject
DATA_DIR = os.path.join(_PROJECT_ROOT, 'data', 'news_subject')

# Gitee 存储：qymmdj/stockdb 仓库 news 目录
GITEE_REPO = 'qymmdj/stockdb'
NEWS_REMOTE = 'news'
FILENAME_PATTERN = re.compile(r'^(\d{12})_new_subjects\.json$')

# 东方财富 东方视点列表接口（栏目ID 366 = cdfsd 东方视点）
EM_NEWS_API = (
    'https://np-listapi.eastmoney.com/comm/web/getNewsByColumns'
    '?client=web&biz=web_news_col&column=366&order=1'
    '&needInteractData=0&page_index={page}&page_size=20&req_trace={trace}'
)
EM_SOURCE_NAME = '东方财富-东方视点'

# 华尔街见闻快讯接口（频道：美股 / 华尔街要闻 / A股）
WSCN_NEWS_API = 'https://api-one-wscn.awtmt.com/apiv1/content/lives'
WSCN_CHANNELS = [
    ('us-stock-channel', '华尔街见闻-美股新闻'),
    ('global-channel', '华尔街见闻-华尔街要闻'),
    ('a-stock-channel', '华尔街见闻-A股新闻'),
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}

# 首次运行时默认只采集最近 24 小时内的消息
FIRST_RUN_HOURS = 24
# 每个来源最多翻页数
MAX_PAGES = 3
# 标题相似度阈值：达到该值视为不同渠道的相同消息
TITLE_SIMILAR_THRESHOLD = 0.75
# 题材文件后缀（文件名：YYYYMMDDHHMM_new_subjects.json，日期为最后生成时间）
SUBJECT_FILE_SUFFIX = '_new_subjects.json'
# 题材文件大小上限（远程文件超过则归档旧文件并新开）
FILE_MAX_SIZE = 500 * 1024
# LLM 单批分析的消息条数
LLM_BATCH_SIZE = 8
# 内容截断长度（控制 token 消耗）
CONTENT_MAX_LEN = 300
# 来源请求间隔（秒），防止限流
REQUEST_INTERVAL = 1.0
# 请求失败重试间隔（秒）
REQUEST_RETRY_DELAY = 3.0


# ===================================
# 通用工具
# ===================================

def _now_str() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _parse_time(time_str: str) -> Optional[datetime]:
    """解析 'YYYY-MM-DD HH:MM:SS' 格式时间"""
    try:
        return datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return None


def _strip_html(text: str) -> str:
    """去除 HTML 标签与多余空白"""
    import re
    text = re.sub(r'<[^>]+>', '', text or '')
    return text.strip()


def make_stars(strength: int) -> str:
    """将 1-5 的关联强度转换为✨标注"""
    try:
        strength = int(strength)
    except (ValueError, TypeError):
        strength = 1
    strength = max(1, min(5, strength))
    return '✨' * strength


def normalize_title(title: str) -> str:
    """标题归一化：去除标点、空白，用于相似度比较"""
    import re
    return re.sub(r'[^\w\u4e00-\u9fa5]', '', (title or ''))


def title_similarity(title_a: str, title_b: str) -> float:
    """计算两个标题的相似度（0-1）"""
    a, b = normalize_title(title_a), normalize_title(title_b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


# ===================================
# 消息采集
# ===================================

def _request_json(url: str, params: Dict[str, Any] = None, retries: int = 2):
    """带重试的 GET 请求（应对瞬时连接重置/限流），返回 JSON"""
    last_error = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(REQUEST_RETRY_DELAY)
    raise last_error


def fetch_eastmoney_news(max_pages: int = MAX_PAGES) -> List[Dict[str, Any]]:
    """
    采集东方财富"东方视点"消息列表

    Returns:
        消息列表，每条包含 title/content/publish_time/source/url
    """
    news_list = []
    for page in range(1, max_pages + 1):
        url = EM_NEWS_API.format(page=page, trace=int(time.time() * 1000))
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            items = ((data.get('data') or {}).get('list')) or []
            if not items:
                print(f"⚠️ 东方视点第 {page} 页无数据，停止翻页")
                break
            for it in items:
                publish_time = it.get('showTime') or ''
                news_list.append({
                    'title': _strip_html(it.get('title') or ''),
                    'content': _strip_html(it.get('summary') or '')[:2000],
                    'publish_time': publish_time,
                    'source': EM_SOURCE_NAME,
                    'url': it.get('uniqueUrl') or '',
                })
            print(f"✅ 东方视点第 {page} 页采集 {len(items)} 条")
            time.sleep(REQUEST_INTERVAL)
        except Exception as e:
            print(f"⚠️ 东方视点第 {page} 页采集失败: {e}")
            break
    return news_list


def fetch_wallstreetcn_news(channel: str, source_name: str,
                            max_pages: int = MAX_PAGES) -> List[Dict[str, Any]]:
    """
    采集华尔街见闻快讯（cursor 翻页）

    Args:
        channel: 频道标识（如 a-stock-channel）
        source_name: 来源名称（如 华尔街见闻-A股新闻）

    Returns:
        消息列表，每条包含 title/content/publish_time/source/url
    """
    news_list = []
    cursor = ''
    for page in range(1, max_pages + 1):
        params = {'channel': channel, 'client': 'pc', 'limit': 50}
        if cursor:
            params['cursor'] = cursor
        try:
            data = _request_json(WSCN_NEWS_API, params=params).get('data') or {}
            items = data.get('items') or []
            if not items:
                print(f"⚠️ {source_name}第 {page} 页无数据，停止翻页")
                break
            for it in items:
                # display_time 为秒级时间戳
                display_time = it.get('display_time')
                publish_time = ''
                if display_time:
                    try:
                        publish_time = datetime.fromtimestamp(
                            int(display_time)).strftime('%Y-%m-%d %H:%M:%S')
                    except (ValueError, OSError):
                        publish_time = ''
                content = _strip_html(it.get('content_text') or '')[:2000]
                # 快讯常无标题：取内容首行作为标题
                title = _strip_html(it.get('title_text') or '') \
                    or content.split('\n')[0][:80]
                news_list.append({
                    'title': title,
                    'content': content,
                    'publish_time': publish_time,
                    'source': it.get('source_name') or source_name,
                    'url': it.get('uri') or '',
                })
            print(f"✅ {source_name}第 {page} 页采集 {len(items)} 条")
            cursor = data.get('next_cursor') or ''
            if not cursor:
                print(f"ℹ️ {source_name}无更多数据，停止翻页")
                break
            time.sleep(REQUEST_INTERVAL)
        except Exception as e:
            print(f"⚠️ {source_name}第 {page} 页采集失败: {e}")
            break
    return news_list


def collect_all_news() -> List[Dict[str, Any]]:
    """采集所有来源的消息（东方视点 + 华尔街见闻美股/要闻/A股）"""
    all_news = []
    all_news.extend(fetch_eastmoney_news())
    for channel, name in WSCN_CHANNELS:
        all_news.extend(fetch_wallstreetcn_news(channel, name))
    print(f"📊 共采集原始消息 {len(all_news)} 条")
    return all_news


# ===================================
# Gitee 远程题材文件（代替本地 state.json 作为采集状态）
# ===================================

def fetch_latest_remote_news(client: GiteeClient) -> Dict[str, Any]:
    """
    从 Gitee news 目录获取最近的题材文件

    下次采集时先获取最近的文件，然后从该时间开始采集

    Returns:
        {'name': 最近文件名或 None, 'library': 题材列表, 'size': 内容字节数,
         'error': 错误信息或 None}
        error 非 None 表示远端有文件但读取失败（应中止运行，防止误删远端数据）
    """
    try:
        files = client.list_directory(NEWS_REMOTE)
    except Exception as e:
        print(f"⚠️ 列出 Gitee {NEWS_REMOTE} 目录失败: {e}")
        return {'name': None, 'library': [], 'size': 0, 'error': None}

    names = [f.get('name', '') for f in files
             if isinstance(f, dict) and FILENAME_PATTERN.match(f.get('name', ''))]
    if not names:
        return {'name': None, 'library': [], 'size': 0, 'error': None}

    latest = max(names)
    try:
        content = client.get_file_content(f"{NEWS_REMOTE}/{latest}")
    except Exception as e:
        return {'name': latest, 'library': [], 'size': 0,
                'error': f"下载远程题材文件失败: {latest}（{e}）"}

    if content is None:
        return {'name': latest, 'library': [], 'size': 0,
                'error': f"下载远程题材文件失败: {latest}"}

    try:
        library = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return {'name': latest, 'library': [], 'size': 0,
                'error': f"远程题材文件内容解析失败: {latest}"}
    if not isinstance(library, list):
        return {'name': latest, 'library': [], 'size': 0,
                'error': f"远程题材文件格式异常（非列表）: {latest}"}

    return {'name': latest, 'library': library,
            'size': len(content.encode('utf-8')), 'error': None}


def remote_name_to_collect_time(name: str) -> str:
    """
    从文件名 YYYYMMDDHHMM_new_subjects.json 解析生成时间作为采集起点

    Returns:
        'YYYY-MM-DD HH:MM:SS'，解析失败返回空串
    """
    m = FILENAME_PATTERN.match(name or '')
    if not m:
        return ''
    try:
        return datetime.strptime(m.group(1), '%Y%m%d%H%M') \
            .strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        return ''


def upload_news_to_gitee(client: GiteeClient, file_path: str) -> bool:
    """
    上传题材文件到 Gitee news 目录（参考 limit_up.py 的上传实现）

    Returns:
        是否成功（失败不影响本地结果）
    """
    try:
        filename = os.path.basename(file_path)
        remote_path = f"{NEWS_REMOTE}/{filename}"
        return client.upload_binary_file(
            file_path, remote_path, message=f"消息题材 {filename}")
    except Exception as e:
        print(f"⚠️ 上传到 Gitee 失败: {e}")
        return False


def delete_remote_news_file(client: GiteeClient, filename: str) -> bool:
    """
    删除 Gitee news 目录下的旧文件（合并场景：新文件已包含旧文件全部内容）

    Returns:
        是否成功（失败容忍，仅多留一个文件，不影响正确性）
    """
    try:
        return client.delete_file(
            f"{NEWS_REMOTE}/{filename}", message=f"归档合并消息题材: {filename}")
    except Exception as e:
        print(f"⚠️ 删除远程旧文件失败（不影响结果）: {e}")
        return False


# ===================================
# 消息去重
# ===================================

def filter_new_news(all_news: List[Dict[str, Any]], last_time_str: str = '',
                    known_news: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """
    过滤出新消息：
    1. 发布时间晚于上次采集时间（首次运行默认最近24小时）
    2. URL 不在已知消息中（远程题材库）
    3. 标题与已知消息不相似
    4. 本批次内跨渠道去重（相同消息只保留一条，来源合并）

    Args:
        all_news: 本次采集的全部消息
        last_time_str: 上次采集时间（来自 Gitee 最近文件名）
        known_news: 已知消息（远程题材库条目，含 urls/title）

    Returns:
        去重后的新消息列表
    """
    last_time = _parse_time(last_time_str or '')
    if last_time is None:
        last_time = datetime.now() - timedelta(hours=FIRST_RUN_HOURS)
        print(f"ℹ️ 首次运行，默认采集 {FIRST_RUN_HOURS} 小时内的消息")

    # 已知消息关键信息：URL 集合 + 标题列表
    known_news = known_news or []
    known_urls = set()
    known_titles = []
    for entry in known_news:
        if not isinstance(entry, dict):
            continue
        urls = entry.get('urls') or ([entry['url']] if entry.get('url') else [])
        known_urls.update(u for u in urls if u)
        if entry.get('title'):
            known_titles.append(entry['title'])

    result: List[Dict[str, Any]] = []
    for news in all_news:
        title = news.get('title') or ''
        if not title:
            continue

        # 1. 判断是否为新消息（按发布时间）
        pub_time = _parse_time(news.get('publish_time') or '')
        if pub_time is None or pub_time <= last_time:
            continue

        # 2. URL 去重（历史）
        if news.get('url') and news['url'] in known_urls:
            continue

        # 3. 标题相似去重（历史）
        if any(title_similarity(title, t) >= TITLE_SIMILAR_THRESHOLD for t in known_titles if t):
            continue

        # 4. 本批次内跨渠道去重：相同消息合并来源
        merged = False
        for exist in result:
            same_url = news.get('url') and news['url'] == exist.get('url')
            if same_url or title_similarity(title, exist.get('title') or '') >= TITLE_SIMILAR_THRESHOLD:
                # 合并来源与链接，保留较早发布时间和较长内容
                if news['source'] not in exist.get('sources', [exist.get('source')]):
                    exist.setdefault('sources', [exist.get('source')]).append(news['source'])
                if news.get('url') and news['url'] not in exist.get('urls', [exist.get('url')]):
                    exist.setdefault('urls', [exist.get('url')]).append(news['url'])
                exist_time = _parse_time(exist.get('publish_time') or '')
                if pub_time and (exist_time is None or pub_time < exist_time):
                    exist['publish_time'] = news['publish_time']
                if len(news.get('content') or '') > len(exist.get('content') or ''):
                    exist['content'] = news['content']
                merged = True
                break
        if not merged:
            item = dict(news)
            item['sources'] = [news['source']]
            item['urls'] = [news.get('url')] if news.get('url') else []
            result.append(item)

    print(f"📊 过滤后新增消息 {len(result)} 条（原始 {len(all_news)} 条）")
    return result


# ===================================
# 大模型分析
# ===================================

class NewsAnalyzer:
    """
    消息价值分析器

    职责：
    1. 调用大模型（Gemini 优先，OpenAI 兼容 API 备选）
    2. 判断消息价值，是否值得采集
    3. 提取消息题材
    4. 找出消息关联个股及关联强度（1-5）
    """

    SYSTEM_PROMPT = """你是一位资深的A股市场消息面分析师，负责对财经新闻消息进行价值评估和题材提取。

分析原则：
1. 高价值消息：可能影响股价走势的消息，如政策利好、行业突破、重大订单、业绩大增、
   涨停潮驱动因素、海外映射（如美股大涨的A股对标板块）、资金大幅流入等
2. 低价值消息：与A股个股/板块关联度弱、纯海外宏观、八卦娱乐、重复炒作的旧闻等
3. 题材：消息所属的炒作题材/板块概念，如"创新药"、"机器人"、"黄金概念"、"固态电池"等
   尽量使用市场通用的简短题材名称
4. 关联个股：仅对高价值消息找出直接受益或直接相关的A股个股（2-8只），
   优先选择消息中明确提及的、业务直接相关的个股
5. 关联强度（1-5）：5=消息直接利好该股（如订单、业绩、点名提及），1=业务沾边、
   关联较弱

你必须且只能输出 JSON，格式如下：
{
  "results": [
    {
      "index": 1,
      "worth_collecting": true,
      "value_level": "高",
      "subject": "创新药",
      "reason": "一句话说明判断理由",
      "related_stocks": [
        {"name": "沃森生物", "code": "300142", "strength": 5, "reason": "mRNA疫苗研发布局"}
      ]
    }
  ]
}

要求：
- results 数组必须覆盖输入的每一条消息，index 与输入编号一致
- 低价值消息 worth_collecting=false，value_level 填"低"，related_stocks 为空数组
- value_level 只能是"高"、"中"、"低"之一
- strength 为 1-5 的整数
- 不确定股票代码时 name 必须准确，code 可留空字符串"""

    def __init__(self):
        self._model = None
        self._openai_client = None
        self._current_model_name = None
        self._use_openai = False
        self._init_llm()

    def _init_llm(self) -> None:
        """初始化大模型客户端：Gemini 优先，OpenAI 兼容 API 备选"""
        config = get_config()

        gemini_key = config.gemini_api_key
        if gemini_key and not gemini_key.startswith('your_') and len(gemini_key) > 10:
            try:
                import google.generativeai as genai
                genai.configure(api_key=gemini_key)
                model_name = config.gemini_model
                try:
                    self._model = genai.GenerativeModel(
                        model_name=model_name,
                        system_instruction=self.SYSTEM_PROMPT,
                    )
                    self._current_model_name = model_name
                except Exception:
                    # 尝试备选模型
                    self._model = genai.GenerativeModel(
                        model_name=config.gemini_model_fallback,
                        system_instruction=self.SYSTEM_PROMPT,
                    )
                    self._current_model_name = config.gemini_model_fallback
                print(f"✅ LLM 初始化成功 (Gemini: {self._current_model_name})")
                return
            except Exception as e:
                print(f"⚠️ Gemini 初始化失败: {e}")

        self._init_openai_fallback()

    def _init_openai_fallback(self) -> None:
        """初始化 OpenAI 兼容 API 作为备选"""
        config = get_config()
        key = config.openai_api_key
        if not (key and not key.startswith('your_') and len(key) > 10):
            return
        try:
            from openai import OpenAI
            client_kwargs = {"api_key": key}
            if config.openai_base_url and config.openai_base_url.startswith('http'):
                client_kwargs["base_url"] = config.openai_base_url
            self._openai_client = OpenAI(**client_kwargs)
            self._current_model_name = config.openai_model
            self._use_openai = True
            print(f"✅ LLM 初始化成功 (OpenAI 兼容: {self._current_model_name})")
        except Exception as e:
            print(f"⚠️ OpenAI 兼容 API 初始化失败: {e}")

    def is_available(self) -> bool:
        """LLM 是否可用"""
        return self._model is not None or self._openai_client is not None

    def _call_llm(self, prompt: str) -> str:
        """调用 LLM（带重试），返回响应文本"""
        config = get_config()
        max_retries = config.gemini_max_retries
        base_delay = config.gemini_retry_delay
        last_error = None

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    delay = min(base_delay * (2 ** (attempt - 1)), 60)
                    print(f"⏳ LLM 第 {attempt + 1} 次重试，等待 {delay:.1f} 秒...")
                    time.sleep(delay)

                if self._use_openai:
                    response = self._openai_client.chat.completions.create(
                        model=self._current_model_name,
                        messages=[
                            {"role": "system", "content": self.SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.3,
                    )
                    text = response.choices[0].message.content
                else:
                    response = self._model.generate_content(
                        prompt,
                        generation_config={"temperature": 0.3},
                        request_options={"timeout": 120},
                    )
                    text = response.text

                if text:
                    return text
                raise ValueError("LLM 返回空响应")
            except Exception as e:
                last_error = e
                print(f"⚠️ LLM 调用失败，第 {attempt + 1}/{max_retries} 次尝试: {str(e)[:100]}")

        raise last_error or Exception("LLM 调用失败")

    def _parse_llm_json(self, response_text: str) -> List[Dict[str, Any]]:
        """从 LLM 响应中解析 JSON 结果列表"""
        cleaned = response_text
        if '```json' in cleaned:
            cleaned = cleaned.replace('```json', '').replace('```', '')
        elif '```' in cleaned:
            cleaned = cleaned.replace('```', '')

        start, end = cleaned.find('{'), cleaned.rfind('}')
        if start < 0 or end <= start:
            return []
        try:
            data = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            return []

        results = data.get('results') or []
        if isinstance(results, list):
            return [r for r in results if isinstance(r, dict)]
        return []

    def analyze_batch(self, news_batch: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
        """
        分析一批消息

        Args:
            news_batch: 消息列表

        Returns:
            {index_in_batch: 分析结果dict}
        """
        lines = []
        for i, news in enumerate(news_batch, start=1):
            content = (news.get('content') or '')[:CONTENT_MAX_LEN]
            lines.append(
                f"[{i}] 标题：{news['title']}\n"
                f"内容：{content}\n"
                f"发布时间：{news.get('publish_time')}\n"
                f"来源：{news.get('source')}"
            )
        prompt = (
            "请分析以下财经消息，判断每条消息的采集价值、所属题材，"
            "并为高价值消息找出关联A股个股及关联强度：\n\n"
            + '\n\n'.join(lines)
            + "\n\n请输出 JSON。"
        )

        response = self._call_llm(prompt)
        parsed = self._parse_llm_json(response)

        result_map = {}
        for item in parsed:
            try:
                idx = int(item.get('index'))
            except (ValueError, TypeError):
                continue
            if 1 <= idx <= len(news_batch):
                result_map[idx - 1] = item
        return result_map


def analyze_news(news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    对新消息进行大模型分析（分批调用）

    Args:
        news_list: 新消息列表

    Returns:
        附加了分析字段的消息列表：
        subject/value_level/worth_collecting/reason/related_stocks/analyzed
    """
    analyzer = NewsAnalyzer()
    if not analyzer.is_available():
        print("⚠️ 未配置可用的 LLM API Key，消息将不做价值分析直接保留")
        for news in news_list:
            news.update({
                'analyzed': False,
                'worth_collecting': True,
                'value_level': '未分析',
                'subject': '',
                'reason': '',
                'related_stocks': [],
            })
        return news_list

    config = get_config()
    request_delay = config.gemini_request_delay

    result_list = []
    total_batches = (len(news_list) + LLM_BATCH_SIZE - 1) // LLM_BATCH_SIZE
    for batch_idx in range(total_batches):
        batch = news_list[batch_idx * LLM_BATCH_SIZE:(batch_idx + 1) * LLM_BATCH_SIZE]
        print(f"🤖 LLM 分析第 {batch_idx + 1}/{total_batches} 批（{len(batch)} 条）...")
        try:
            result_map = analyzer.analyze_batch(batch)
        except Exception as e:
            print(f"⚠️ 本批分析失败: {e}，本批消息标记为未分析")
            result_map = {}

        for i, news in enumerate(batch):
            analysis = result_map.get(i)
            if analysis is None:
                news.update({
                    'analyzed': False,
                    'worth_collecting': True,
                    'value_level': '未分析',
                    'subject': '',
                    'reason': '',
                    'related_stocks': [],
                })
            else:
                stocks = []
                for s in analysis.get('related_stocks') or []:
                    if not isinstance(s, dict) or not s.get('name'):
                        continue
                    strength = s.get('strength', 1)
                    try:
                        strength = max(1, min(5, int(strength)))
                    except (ValueError, TypeError):
                        strength = 1
                    stocks.append({
                        'name': str(s.get('name', '')).strip(),
                        'code': str(s.get('code', '') or '').strip(),
                        'strength': strength,
                        'stars': make_stars(strength),
                        'reason': str(s.get('reason', '') or ''),
                    })
                news.update({
                    'analyzed': True,
                    'worth_collecting': bool(analysis.get('worth_collecting')),
                    'value_level': str(analysis.get('value_level', '中')),
                    'subject': str(analysis.get('subject', '') or '').strip(),
                    'reason': str(analysis.get('reason', '') or ''),
                    'related_stocks': stocks,
                })
            result_list.append(news)

        # 批间延时，防止限流
        if request_delay > 0 and batch_idx < total_batches - 1:
            time.sleep(request_delay)

    analyzed_count = sum(1 for n in result_list if n.get('analyzed'))
    print(f"📊 LLM 分析完成：{analyzed_count}/{len(result_list)} 条成功")
    return result_list


# ===================================
# 消息题材文件（单一当前文件，超 500KB 归档新开）
# ===================================

def find_subject_file() -> Optional[str]:
    """
    查找当前活跃的题材文件（修改时间最新的 *_new_subjects.json）

    Returns:
        文件路径，不存在时返回 None
    """
    if not os.path.isdir(DATA_DIR):
        return None
    files = glob.glob(os.path.join(DATA_DIR, f'*{SUBJECT_FILE_SUFFIX}'))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def load_library(file_path: str) -> List[Dict[str, Any]]:
    """加载题材文件内容（JSON 列表），损坏时返回空列表"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception as e:
        print(f"⚠️ 读取题材文件失败: {e}")
    return []


def save_subject_file(library: List[Dict[str, Any]],
                      prev_file: Optional[str] = None) -> str:
    """
    保存题材文件

    文件名为最后生成时间（YYYYMMDDHHMM_new_subjects.json）；
    续写场景下删除旧文件（重命名语义），目录内始终只有一个当前文件
    （已归档的超限文件不受影响）
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    library.sort(key=lambda x: x.get('publish_time') or '', reverse=True)
    filename = f"{datetime.now().strftime('%Y%m%d%H%M')}{SUBJECT_FILE_SUFFIX}"
    file_path = os.path.join(DATA_DIR, filename)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(library, f, ensure_ascii=False, indent=2)
    size_kb = os.path.getsize(file_path) // 1024
    print(f"💾 题材文件已保存（{len(library)} 条，{size_kb}KB）: {filename}")
    if prev_file and os.path.exists(prev_file) \
            and os.path.abspath(prev_file) != os.path.abspath(file_path):
        os.remove(prev_file)
    return file_path


def merge_into_library(library: List[Dict[str, Any]], news_list: List[Dict[str, Any]]) -> int:
    """
    将值得采集的消息合并进题材库

    去重规则：URL 相同或标题相似（不同来源渠道相同消息只保留一条，合并来源）

    Returns:
        新增的题材条数
    """
    added = 0
    for news in news_list:
        if not news.get('worth_collecting'):
            continue

        title = news.get('title') or ''
        url = news.get('url') or ''

        # 在库中查找相同消息
        matched = None
        for lib in library:
            lib_urls = lib.get('urls') or ([lib['url']] if lib.get('url') else [])
            if url and url in lib_urls:
                matched = lib
                break
            if title_similarity(title, lib.get('title') or '') >= TITLE_SIMILAR_THRESHOLD:
                matched = lib
                break

        entry = {
            'title': title,
            'content': news.get('content') or '',
            'publish_time': news.get('publish_time') or '',
            'sources': list(news.get('sources') or [news.get('source')]),
            'urls': list(news.get('urls') or ([url] if url else [])),
            'subject': news.get('subject') or '',
            'value_level': news.get('value_level') or '',
            'reason': news.get('reason') or '',
            'related_stocks': news.get('related_stocks') or [],
            'analyzed': news.get('analyzed', False),
            'collect_time': _now_str(),
        }

        if matched:
            # 相同消息：合并来源与链接，保留最强关联个股
            for src in entry['sources']:
                if src not in matched['sources']:
                    matched['sources'].append(src)
            for u in entry['urls']:
                if u and u not in matched['urls']:
                    matched['urls'].append(u)
            if len(entry['content']) > len(matched.get('content') or ''):
                matched['content'] = entry['content']
            if entry.get('subject') and not matched.get('subject'):
                matched['subject'] = entry['subject']
            if entry.get('value_level') and not matched.get('value_level'):
                matched['value_level'] = entry['value_level']
            # 个股合并：同名取更强关联
            merged_stocks = {s['name']: dict(s) for s in matched.get('related_stocks') or []}
            for s in entry['related_stocks']:
                old = merged_stocks.get(s['name'])
                if old is None or s['strength'] > old['strength']:
                    merged_stocks[s['name']] = s
            matched['related_stocks'] = list(merged_stocks.values())
        else:
            library.append(entry)
            added += 1

    return added


# ===================================
# 主流程
# ===================================

def run() -> int:
    """
    消息题材采集分析主流程

    1. 从 Gitee news 目录获取最近题材文件，以其时间作为采集起点
    2. 从消息来源采集消息列表（东方视点 + 华尔街见闻）
    3. 提取标题、内容、发布时间、来源
    4. 按发布时间判断新消息，去重（重复消息合并为一条）
    5. 大模型判断消息价值，只保留重要消息
    6. 重要消息找出关联个股（✨标注强度）
    7. 合并进题材文件 YYYYMMDDHHMM_new_subjects.json（超500KB归档新开）
    8. 上传到 Gitee news 目录
    """
    print("=" * 60)
    print("📰 消息题材采集分析开始")
    print("=" * 60)

    try:
        # 0. 初始化 Gitee 客户端
        client = GiteeClient(repo=GITEE_REPO)

        # 1. 从 Gitee news 目录获取最近题材文件，确定采集起点
        remote = fetch_latest_remote_news(client)
        if remote['error']:
            # 远端有文件但读取失败：中止，防止误删远端数据
            print(f"❌ {remote['error']}")
            return 1
        remote_name = remote['name']
        library: List[Dict[str, Any]] = remote['library']
        remote_size = remote['size']
        rolled = False
        if remote_name:
            last_collect_time = remote_name_to_collect_time(remote_name)
            if remote_size > FILE_MAX_SIZE:
                # 当前文件超 500KB：归档旧文件，从空库新开
                rolled = True
                print(f"📦 远程题材文件已超 {FILE_MAX_SIZE // 1024}KB"
                      f"（{remote_size // 1024}KB），归档 {remote_name} 并新开")
                library = []
            else:
                print(f"🕐 Gitee 最近文件: {remote_name}"
                      f"（{len(library)} 条，{remote_size // 1024}KB），"
                      f"采集起点 {last_collect_time}")
        else:
            last_collect_time = ''
            print("🕐 Gitee news 目录无历史文件，首次运行默认采集最近 24 小时")

        # 2-3. 采集消息并提取关键信息
        all_news = collect_all_news()
        if not all_news:
            print("⚠️ 未采集到任何消息")

        # 4. 过滤新消息（时间判断 + 去重，重复消息合并为一条）
        new_news = filter_new_news(all_news, last_collect_time, library)

        file_path = None
        new_count = len(new_news)
        worth_count = 0

        if new_news:
            # 5-6. 大模型分析价值与关联个股，只保留重要消息
            analyzed_news = analyze_news(new_news)
            worth_news = [n for n in analyzed_news if n.get('worth_collecting')]
            worth_count = len(worth_news)

            # 7. 合并进题材文件并保存本地
            if worth_news:
                added = merge_into_library(library, worth_news)
                # 合并场景：本地旧文件删除（重命名语义）；归档场景：保留
                local_prev = None if rolled else find_subject_file()
                file_path = save_subject_file(library, local_prev)
                print(f"📚 题材新增 {added} 条，当前文件共 {len(library)} 条")

                # 8. 上传到 Gitee news 目录
                if upload_news_to_gitee(client, file_path):
                    print(f"📤 结果已上传到 Gitee: "
                          f"{NEWS_REMOTE}/{os.path.basename(file_path)}")
                    # 合并场景删除远程旧文件（同分钟重跑文件同名，不删）
                    if not rolled and remote_name \
                            and remote_name != os.path.basename(file_path) \
                            and delete_remote_news_file(client, remote_name):
                        print(f"🗑️ 已删除远程旧文件: {remote_name}")
                else:
                    print("⚠️ 上传 Gitee 失败（本地结果已保存）")
            else:
                print("ℹ️ 本次无值得采集的重要消息")
        else:
            print("✅ 无新消息，本次不更新题材文件")

        print("=" * 60)
        print(f"🎉 任务完成！本次新增 {new_count} 条，重要消息 {worth_count} 条")
        print("=" * 60)
        return 0

    except Exception as e:
        print("=" * 60)
        print(f"❌ 任务失败: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 60)
        return 1


def main():
    return run()


if __name__ == "__main__":
    exit(main())
