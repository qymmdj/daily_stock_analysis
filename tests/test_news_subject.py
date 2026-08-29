# -*- coding: utf-8 -*-
"""
===================================
消息题材采集分析模块 - 单元测试
===================================

职责：
1. 验证工具函数（星级标注、标题相似度、时间解析）
2. 验证消息采集解析（东方财富/华尔街见闻接口，mock 网络请求）
3. 验证采集状态管理（上次采集时间、历史消息）
4. 验证新消息过滤与去重（时间/URL/标题相似度/跨渠道合并）
5. 验证大模型分析（JSON 解析、字段处理、降级容错）
6. 验证题材文件（合并去重、单一文件命名、500KB 滚动新开）
7. 验证 Gitee 上传容错
8. 验证主流程（全链路 mock）
"""

import os
import sys
import json
import glob
import time
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# 确保项目根目录可导入
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.qym.eastmoney.news import newsSubject as ns


def make_news(title='测试消息标题', content='测试内容', publish_time='2026-08-20 10:00:00',
              source='测试来源', url='http://test/1'):
    """构造标准消息 dict 的快捷函数"""
    return {
        'title': title,
        'content': content,
        'publish_time': publish_time,
        'source': source,
        'url': url,
    }


def make_analyzed(**kwargs):
    """构造带分析字段的消息 dict 的快捷函数"""
    news = make_news(**{k: v for k, v in kwargs.items()
                        if k in ('title', 'content', 'publish_time', 'source', 'url')})
    news.update({
        'analyzed': kwargs.get('analyzed', True),
        'worth_collecting': kwargs.get('worth_collecting', True),
        'value_level': kwargs.get('value_level', '高'),
        'subject': kwargs.get('subject', '测试题材'),
        'reason': kwargs.get('reason', '测试理由'),
        'related_stocks': kwargs.get('related_stocks', []),
        'sources': kwargs.get('sources', [news['source']]),
        'urls': kwargs.get('urls', [news['url']]),
    })
    return news


class NewsSubjectTestCaseBase(unittest.TestCase):
    """测试基类：提供临时数据目录隔离与通用 patch"""

    def setUp(self) -> None:
        # 临时目录隔离数据文件
        self._temp_dir = tempfile.TemporaryDirectory()
        self._orig_data_dir = ns.DATA_DIR
        ns.DATA_DIR = os.path.join(self._temp_dir.name, 'data')

    def tearDown(self) -> None:
        ns.DATA_DIR = self._orig_data_dir
        self._temp_dir.cleanup()

    def write_json(self, file_path: str, data) -> None:
        """写入 JSON 文件（自动创建目录）"""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

    def read_json(self, file_path: str):
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def subject_files(self):
        """当前数据目录下全部题材文件"""
        return glob.glob(os.path.join(ns.DATA_DIR, f'*{ns.SUBJECT_FILE_SUFFIX}'))


# ===================================
# 1. 工具函数测试
# ===================================

class MakeStarsTestCase(NewsSubjectTestCaseBase):
    """✨ 关联强度星级转换测试"""

    def test_normal_range(self) -> None:
        """1-5 正常强度逐级转换"""
        self.assertEqual(ns.make_stars(1), '✨')
        self.assertEqual(ns.make_stars(2), '✨✨')
        self.assertEqual(ns.make_stars(3), '✨✨✨')
        self.assertEqual(ns.make_stars(4), '✨✨✨✨')
        self.assertEqual(ns.make_stars(5), '✨✨✨✨✨')

    def test_overflow_clamped(self) -> None:
        """超过 5 的强度截断为 5 星，低于 1 提升为 1 星"""
        self.assertEqual(ns.make_stars(99), '✨✨✨✨✨')
        self.assertEqual(ns.make_stars(0), '✨')
        self.assertEqual(ns.make_stars(-3), '✨')

    def test_invalid_input(self) -> None:
        """非法输入（字符串/None/浮点异常）兜底为 1 星"""
        self.assertEqual(ns.make_stars('abc'), '✨')
        self.assertEqual(ns.make_stars(None), '✨')

    def test_numeric_string(self) -> None:
        """数字字符串可正常转换"""
        self.assertEqual(ns.make_stars('3'), '✨✨✨')


class TitleSimilarityTestCase(NewsSubjectTestCaseBase):
    """标题相似度计算测试"""

    def test_identical_titles(self) -> None:
        """完全相同标题相似度为 1.0"""
        self.assertEqual(ns.title_similarity('A股大涨', 'A股大涨'), 1.0)

    def test_punctuation_and_space_ignored(self) -> None:
        """标点与空白不影响相似度判断"""
        self.assertEqual(
            ns.title_similarity('1分钟 30%涨停！创新药引爆', '1分钟30%涨停创新药引爆'), 1.0)
        self.assertEqual(ns.title_similarity('A股大涨', ' A股大涨 '), 1.0)

    def test_different_titles_low_similarity(self) -> None:
        """完全不同题材的标题相似度低于去重阈值"""
        sim = ns.title_similarity('韩国股市熔断 存储芯片巨头大涨超11%',
                                  '王兴兴：机器人两三年内或迎关键突破')
        self.assertLess(sim, ns.TITLE_SIMILAR_THRESHOLD)

    def test_empty_title(self) -> None:
        """空标题相似度为 0"""
        self.assertEqual(ns.title_similarity('', 'A股大涨'), 0.0)
        self.assertEqual(ns.title_similarity('', ''), 0.0)
        self.assertEqual(ns.title_similarity(None, 'A股大涨'), 0.0)

    def test_normalized_title(self) -> None:
        """归一化仅保留中文、字母、数字、下划线"""
        self.assertEqual(ns.normalize_title('A股，大涨！'), 'A股大涨')
        self.assertEqual(ns.normalize_title('abc-123_x'), 'abc123_x')
        self.assertEqual(ns.normalize_title('【重磅】央行降息！'), '重磅央行降息')


class ParseTimeTestCase(NewsSubjectTestCaseBase):
    """时间字符串解析测试"""

    def test_valid_time(self) -> None:
        """标准格式时间解析成功"""
        dt = ns._parse_time('2026-08-20 10:30:00')
        self.assertEqual(dt, datetime(2026, 8, 20, 10, 30, 0))

    def test_invalid_time(self) -> None:
        """非法格式与空值返回 None"""
        self.assertIsNone(ns._parse_time('2026/08/20'))
        self.assertIsNone(ns._parse_time(''))
        self.assertIsNone(ns._parse_time(None))


class StripHtmlTestCase(NewsSubjectTestCaseBase):
    """HTML 清理测试"""

    def test_strip_tags(self) -> None:
        """去除 HTML 标签并保留文本"""
        self.assertEqual(ns._strip_html('<p>正文<b>加粗</b></p>'), '正文加粗')

    def test_none_and_empty(self) -> None:
        """None 与空串安全处理"""
        self.assertEqual(ns._strip_html(None), '')
        self.assertEqual(ns._strip_html('   '), '')


# ===================================
# 2. 消息采集测试（mock 网络）
# ===================================

class MockResponse:
    """模拟 requests.Response"""

    def __init__(self, payload=None, raise_error=None):
        self._payload = payload
        self._raise_error = raise_error

    def raise_for_status(self):
        if self._raise_error:
            raise self._raise_error

    def json(self):
        if self._payload is None:
            raise ValueError('No JSON')
        return self._payload


@patch.object(ns, 'REQUEST_INTERVAL', 0)
@patch.object(ns.requests, 'get')
class FetchEastmoneyNewsTestCase(NewsSubjectTestCaseBase):
    """东方财富东方视点采集测试"""

    @staticmethod
    def _em_item(code='202608203847514885', title='测试新闻', show_time='2026-08-20 10:00:00'):
        return {
            'title': f'<b>{title}</b>',
            'summary': '新闻摘要内容',
            'showTime': show_time,
            'uniqueUrl': f'http://finance.eastmoney.com/a/{code}.html',
        }

    def test_fetch_success(self, mock_get) -> None:
        """正常解析接口返回：提取标题/内容/时间/来源/URL，HTML 标签被清理"""
        mock_get.return_value = MockResponse({'data': {'list': [self._em_item()]}})
        result = ns.fetch_eastmoney_news(max_pages=1)

        self.assertEqual(len(result), 1)
        item = result[0]
        self.assertEqual(item['title'], '测试新闻')
        self.assertEqual(item['content'], '新闻摘要内容')
        self.assertEqual(item['publish_time'], '2026-08-20 10:00:00')
        self.assertEqual(item['source'], ns.EM_SOURCE_NAME)
        self.assertEqual(item['url'], 'http://finance.eastmoney.com/a/202608203847514885.html')

    def test_fetch_empty_list_stops_paging(self, mock_get) -> None:
        """空列表时停止翻页，不继续请求"""
        mock_get.return_value = MockResponse({'data': {'list': []}})
        result = ns.fetch_eastmoney_news(max_pages=3)
        self.assertEqual(result, [])
        self.assertEqual(mock_get.call_count, 1)

    def test_fetch_multiple_pages(self, mock_get) -> None:
        """多页采集逐页累计"""
        page_data = {'data': {'list': [self._em_item()]}}
        mock_get.return_value = MockResponse(page_data)
        result = ns.fetch_eastmoney_news(max_pages=2)
        self.assertEqual(len(result), 2)
        self.assertEqual(mock_get.call_count, 2)

    def test_fetch_request_error_tolerated(self, mock_get) -> None:
        """请求异常时容错返回已采集内容"""
        mock_get.return_value = MockResponse(raise_error=RuntimeError('timeout'))
        result = ns.fetch_eastmoney_news(max_pages=2)
        self.assertEqual(result, [])
        # 异常后停止翻页
        self.assertEqual(mock_get.call_count, 1)

    def test_fetch_bad_json_tolerated(self, mock_get) -> None:
        """JSON 解析失败容错不抛异常"""
        mock_get.return_value = MockResponse(payload=None)
        result = ns.fetch_eastmoney_news(max_pages=1)
        self.assertEqual(result, [])

    def test_fetch_none_fields_default(self, mock_get) -> None:
        """字段缺失时使用空串兜底"""
        mock_get.return_value = MockResponse({'data': {'list': [{'title': None, 'summary': None}]}})
        result = ns.fetch_eastmoney_news(max_pages=1)
        self.assertEqual(result[0]['title'], '')
        self.assertEqual(result[0]['publish_time'], '')


@patch.object(ns, 'REQUEST_INTERVAL', 0)
@patch.object(ns, 'REQUEST_RETRY_DELAY', 0)
@patch.object(ns.requests, 'get')
class FetchWallstreetcnNewsTestCase(NewsSubjectTestCaseBase):
    """华尔街见闻快讯采集测试"""

    @staticmethod
    def _wscn_item(title_text='港股午评：恒指涨1.14%', content_text='恒生指数涨1.14%，科技股领涨。',
                   display_time='1787198438', uri='https://wallstreetcn.com/livenews/1',
                   source_name=None):
        return {
            'title_text': title_text,
            'content_text': content_text,
            'display_time': display_time,
            'uri': uri,
            'source_name': source_name,
        }

    @staticmethod
    def _wscn_page(items, next_cursor=''):
        return {'data': {'items': items, 'next_cursor': next_cursor}}

    def test_fetch_success(self, mock_get) -> None:
        """正常解析：字段提取正确，无 next_cursor 时停止翻页"""
        mock_get.return_value = MockResponse(
            self._wscn_page([self._wscn_item()]))
        result = ns.fetch_wallstreetcn_news('a-stock-channel', '华尔街见闻-A股新闻', max_pages=3)

        self.assertEqual(len(result), 1)
        item = result[0]
        self.assertEqual(item['title'], '港股午评：恒指涨1.14%')
        self.assertEqual(item['content'], '恒生指数涨1.14%，科技股领涨。')
        # 时间戳 1787198438 -> 2026-08-20
        self.assertTrue(item['publish_time'].startswith('2026-08-20'))
        self.assertEqual(item['source'], '华尔街见闻-A股新闻')
        self.assertEqual(item['url'], 'https://wallstreetcn.com/livenews/1')
        # 无 next_cursor，只请求一次
        self.assertEqual(mock_get.call_count, 1)

    def test_fetch_title_fallback_to_content(self, mock_get) -> None:
        """快讯无标题时取内容首行作为标题（截断80字符）"""
        item = self._wscn_item(title_text=None,
                               content_text='央行宣布降准50个基点，释放长期资金约1万亿元\n\n后续内容')
        mock_get.return_value = MockResponse(self._wscn_page([item]))
        result = ns.fetch_wallstreetcn_news('global-channel', '华尔街见闻-华尔街要闻', max_pages=1)

        self.assertEqual(result[0]['title'], '央行宣布降准50个基点，释放长期资金约1万亿元')
        self.assertEqual(result[0]['content'], '央行宣布降准50个基点，释放长期资金约1万亿元\n\n后续内容')

    def test_fetch_source_name_override(self, mock_get) -> None:
        """条目自带 source_name 时优先使用"""
        item = self._wscn_item(source_name='华尔街见闻')
        mock_get.return_value = MockResponse(self._wscn_page([item]))
        result = ns.fetch_wallstreetcn_news('us-stock-channel', '华尔街见闻-美股新闻', max_pages=1)
        self.assertEqual(result[0]['source'], '华尔街见闻')

    def test_fetch_cursor_paging(self, mock_get) -> None:
        """有 next_cursor 时使用 cursor 参数翻页"""
        page1 = self._wscn_page([self._wscn_item(uri='http://w/1')], next_cursor='CURSOR123')
        page2 = self._wscn_page([self._wscn_item(uri='http://w/2')])
        mock_get.side_effect = [MockResponse(page1), MockResponse(page2)]

        result = ns.fetch_wallstreetcn_news('a-stock-channel', '华尔街见闻-A股新闻', max_pages=2)

        self.assertEqual(len(result), 2)
        self.assertEqual(mock_get.call_count, 2)
        # 第二次请求携带 cursor 参数
        second_params = mock_get.call_args_list[1][1]['params'] \
            if 'params' in mock_get.call_args_list[1][1] \
            else mock_get.call_args_list[1][0][1]
        self.assertEqual(second_params.get('cursor'), 'CURSOR123')
        self.assertEqual({n['url'] for n in result}, {'http://w/1', 'http://w/2'})

    def test_fetch_invalid_display_time(self, mock_get) -> None:
        """非法时间戳时发布时间为空串"""
        item = self._wscn_item(display_time='not-a-number')
        mock_get.return_value = MockResponse(self._wscn_page([item]))
        result = ns.fetch_wallstreetcn_news('a-stock-channel', '华尔街见闻-A股新闻', max_pages=1)
        self.assertEqual(result[0]['publish_time'], '')

    def test_fetch_empty_stops_paging(self, mock_get) -> None:
        """空数据停止翻页"""
        mock_get.return_value = MockResponse(self._wscn_page([]))
        result = ns.fetch_wallstreetcn_news('a-stock-channel', '华尔街见闻-A股新闻', max_pages=3)
        self.assertEqual(result, [])
        self.assertEqual(mock_get.call_count, 1)

    def test_fetch_error_tolerated(self, mock_get) -> None:
        """请求持续失败（重试2次）容错返回空列表"""
        mock_get.return_value = MockResponse(raise_error=RuntimeError('network error'))
        self.assertEqual(
            ns.fetch_wallstreetcn_news('us-stock-channel', '华尔街见闻-美股新闻', max_pages=1), [])
        # 默认重试 2 次
        self.assertEqual(mock_get.call_count, 2)

    def test_fetch_retry_success(self, mock_get) -> None:
        """首次请求失败、重试成功：返回正常数据"""
        ok = MockResponse(self._wscn_page([self._wscn_item()]))
        mock_get.side_effect = [MockResponse(raise_error=ConnectionResetError(10054)), ok]

        result = ns.fetch_wallstreetcn_news('global-channel', '华尔街见闻-华尔街要闻', max_pages=1)

        self.assertEqual(len(result), 1)
        self.assertEqual(mock_get.call_count, 2)

    def test_fetch_bad_json_tolerated(self, mock_get) -> None:
        """JSON 解析失败容错"""
        mock_get.return_value = MockResponse(payload=None)
        self.assertEqual(
            ns.fetch_wallstreetcn_news('us-stock-channel', '华尔街见闻-美股新闻', max_pages=1), [])


@patch.object(ns, 'REQUEST_INTERVAL', 0)
class CollectAllNewsTestCase(NewsSubjectTestCaseBase):
    """多来源汇总采集测试"""

    def test_collect_merges_all_sources(self) -> None:
        """东财 + 华尔街见闻3个频道全部采集汇总"""
        with patch.object(ns, 'fetch_eastmoney_news',
                          return_value=[make_news(title='东财消息')]), \
                patch.object(ns, 'fetch_wallstreetcn_news',
                             side_effect=lambda ch, name: [make_news(title=name)]):
            result = ns.collect_all_news()

        self.assertEqual(len(result), 4)
        titles = {n['title'] for n in result}
        self.assertEqual(titles, {'东财消息', '华尔街见闻-美股新闻',
                                  '华尔街见闻-华尔街要闻', '华尔街见闻-A股新闻'})

    def test_collect_source_failure_tolerated(self) -> None:
        """单个来源采集失败（内部容错返回空列表）不影响其他来源"""
        def fake_wscn(channel, name):
            # 模拟 us-stock-channel 渠道请求失败：内部容错后返回空列表
            return [] if channel == 'us-stock-channel' else [make_news(title=name)]

        with patch.object(ns, 'fetch_eastmoney_news',
                          return_value=[make_news(title='东财消息')]), \
                patch.object(ns, 'fetch_wallstreetcn_news', side_effect=fake_wscn):
            result = ns.collect_all_news()

        titles = {n['title'] for n in result}
        self.assertEqual(titles, {'东财消息', '华尔街见闻-华尔街要闻', '华尔街见闻-A股新闻'})


# ===================================
# 3. 采集状态管理测试
# ===================================

class RemoteNameToTimeTestCase(NewsSubjectTestCaseBase):
    """远程文件名解析采集起点测试"""

    def test_valid_name(self) -> None:
        """YYYYMMDDHHMM_new_subjects.json 解析为采集起点时间"""
        self.assertEqual(
            ns.remote_name_to_collect_time('202608202244_new_subjects.json'),
            '2026-08-20 22:44:00')

    def test_invalid_names(self) -> None:
        """非题材文件名/空值返回空串"""
        for name in ('', None, 'state.json', '20260820_news.json',
                     '20260820_new_subjects.json', '202608202244_news.json'):
            self.assertEqual(ns.remote_name_to_collect_time(name), '')


class FetchLatestRemoteNewsTestCase(NewsSubjectTestCaseBase):
    """从 Gitee news 目录获取最近题材文件测试"""

    @staticmethod
    def _client(files=None, content=None, content_error=None):
        """构造 mock GiteeClient"""
        client = MagicMock()
        if content_error:
            client.list_directory.side_effect = content_error
        else:
            client.list_directory.return_value = files or []
        if content is not None:
            client.get_file_content.return_value = content
        return client

    def test_no_remote_file(self) -> None:
        """目录为空/无题材文件：name=None，不报错"""
        for files in ([], [{'name': 'readme.md'}],
                      [{'name': '20260820_news.json'}]):
            client = self._client(files=files)
            remote = ns.fetch_latest_remote_news(client)
            self.assertIsNone(remote['name'])
            self.assertEqual(remote['library'], [])
            self.assertEqual(remote['size'], 0)
            self.assertIsNone(remote['error'])

    def test_picks_latest_file(self) -> None:
        """多个题材文件时选择文件名时间最大的一个"""
        files = [{'name': '20260820110000_new_subjects.json'},
                 {'name': '202608202244_new_subjects.json'},
                 {'name': '20260820150000_new_subjects.json'}]
        client = self._client(files=files, content='[]')
        remote = ns.fetch_latest_remote_news(client)
        self.assertEqual(remote['name'], '202608202244_new_subjects.json')
        # 下载的是最近文件的路径
        client.get_file_content.assert_called_once_with(
            'news/202608202244_new_subjects.json')

    def test_success_loads_library(self) -> None:
        """正常下载解析：返回题材列表与内容大小"""
        library = [{'title': '消息A', 'urls': ['http://a/1']}]
        content = json.dumps(library, ensure_ascii=False)
        client = self._client(
            files=[{'name': '202608202244_new_subjects.json'}], content=content)
        remote = ns.fetch_latest_remote_news(client)
        self.assertEqual(remote['name'], '202608202244_new_subjects.json')
        self.assertEqual(remote['library'], library)
        self.assertEqual(remote['size'], len(content.encode('utf-8')))
        self.assertIsNone(remote['error'])

    def test_list_directory_error_tolerated(self) -> None:
        """列目录异常：视为无历史文件（不报错）"""
        client = self._client(content_error=RuntimeError('network'))
        remote = ns.fetch_latest_remote_news(client)
        self.assertIsNone(remote['name'])
        self.assertIsNone(remote['error'])

    def test_download_failure_returns_error(self) -> None:
        """下载失败：返回 error（调用方应中止，防止误删远端数据）"""
        client = self._client(files=[{'name': '202608202244_new_subjects.json'}])
        client.get_file_content.return_value = None
        remote = ns.fetch_latest_remote_news(client)
        self.assertEqual(remote['name'], '202608202244_new_subjects.json')
        self.assertIsNotNone(remote['error'])
        self.assertIn('下载', remote['error'])

    def test_download_exception_returns_error(self) -> None:
        """下载抛异常：返回 error"""
        client = self._client(files=[{'name': '202608202244_new_subjects.json'}])
        client.get_file_content.side_effect = RuntimeError('boom')
        remote = ns.fetch_latest_remote_news(client)
        self.assertIsNotNone(remote['error'])

    def test_corrupted_content_returns_error(self) -> None:
        """内容解析失败：返回 error"""
        client = self._client(
            files=[{'name': '202608202244_new_subjects.json'}], content='[[[broken')
        remote = ns.fetch_latest_remote_news(client)
        self.assertIsNotNone(remote['error'])
        self.assertIn('解析失败', remote['error'])

    def test_non_list_content_returns_error(self) -> None:
        """内容非列表：返回 error"""
        client = self._client(
            files=[{'name': '202608202244_new_subjects.json'}], content='{"a": 1}')
        remote = ns.fetch_latest_remote_news(client)
        self.assertIsNotNone(remote['error'])
        self.assertIn('格式异常', remote['error'])


# ===================================
# 4. 新消息过滤与去重测试
# ===================================

class FilterNewsTestCase(NewsSubjectTestCaseBase):
    """新消息过滤测试"""

    LAST_TIME = '2026-08-20 08:00:00'

    @staticmethod
    def _known(entries=None):
        """构造已知消息（远程题材库条目）"""
        return entries or []

    def test_filter_by_publish_time(self) -> None:
        """仅保留发布时间晚于上次采集时间的消息"""
        all_news = [
            make_news(title='新消息', publish_time='2026-08-20 09:00:00'),
            make_news(title='旧消息', publish_time='2026-08-20 07:00:00'),
            make_news(title='临界消息', publish_time='2026-08-20 08:00:00'),  # 等于上次时间
        ]
        result = ns.filter_new_news(all_news, self.LAST_TIME)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['title'], '新消息')

    def test_first_run_defaults_24h(self) -> None:
        """首次运行默认采集最近 24 小时内的消息"""
        now = datetime.now()
        fresh = make_news(title='24小时内新消息',
                          publish_time=(now - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S'))
        stale = make_news(title='48小时前旧消息',
                          publish_time=(now - timedelta(hours=48)).strftime('%Y-%m-%d %H:%M:%S'))
        result = ns.filter_new_news([fresh, stale], '')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['title'], '24小时内新消息')

    def test_filter_invalid_publish_time(self) -> None:
        """无法解析发布时间的消息被过滤"""
        all_news = [
            make_news(title='无时间消息', publish_time=''),
            make_news(title='非法时间', publish_time='昨天'),
        ]
        result = ns.filter_new_news(all_news, self.LAST_TIME)
        self.assertEqual(result, [])

    def test_filter_by_known_url(self) -> None:
        """已知消息（远程题材库）URL 命中的消息被过滤"""
        all_news = [make_news(title='已采集消息', url='http://a/1')]
        known = self._known([{'title': '其他标题', 'urls': ['http://a/1']}])
        self.assertEqual(ns.filter_new_news(all_news, self.LAST_TIME, known), [])

    def test_filter_by_known_url_legacy_field(self) -> None:
        """已知消息使用旧版单 url 字段时同样参与去重"""
        all_news = [make_news(title='已采集消息', url='http://a/1')]
        known = self._known([{'title': '其他标题', 'url': 'http://a/1'}])
        self.assertEqual(ns.filter_new_news(all_news, self.LAST_TIME, known), [])

    def test_filter_by_similar_title(self) -> None:
        """与已知消息标题相似的消息被过滤"""
        all_news = [make_news(title='A股大涨！沪指突破4000点', url='http://a/2')]
        known = self._known([{'title': 'A股大涨！沪指突破4000点', 'urls': ['http://a/1']}])
        self.assertEqual(ns.filter_new_news(all_news, self.LAST_TIME, known), [])

    def test_filter_empty_title_skipped(self) -> None:
        """空标题消息直接跳过"""
        all_news = [make_news(title='', url='http://a/1')]
        self.assertEqual(ns.filter_new_news(all_news, self.LAST_TIME), [])

    def test_cross_channel_merge(self) -> None:
        """本批次内跨渠道相同消息合并：来源/链接合并，保留较早时间与较长内容"""
        all_news = [
            make_news(title='mRNA癌症疫苗迎重磅突破', content='短',
                      publish_time='2026-08-20 09:30:00',
                      source='东方财富-东方视点', url='http://em/1'),
            make_news(title='mRNA癌症疫苗迎重磅突破', content='更长的内容' * 10,
                      publish_time='2026-08-20 09:35:00',
                      source='华尔街见闻-美股新闻', url='http://wscn/1'),
        ]
        result = ns.filter_new_news(all_news, self.LAST_TIME)
        self.assertEqual(len(result), 1)
        merged = result[0]
        # 来源与链接合并
        self.assertEqual(len(merged['sources']), 2)
        self.assertEqual(set(merged['urls']), {'http://em/1', 'http://wscn/1'})
        # 保留较早发布时间
        self.assertEqual(merged['publish_time'], '2026-08-20 09:30:00')
        # 保留较长内容
        self.assertTrue(merged['content'].startswith('更长的内容'))

    def test_cross_channel_different_news_kept(self) -> None:
        """本批次内不同消息全部保留"""
        all_news = [
            make_news(title='韩国股市熔断 存储芯片巨头大涨超11%', url='http://a/1'),
            make_news(title='王兴兴：机器人两三年内或迎关键突破', url='http://a/2'),
        ]
        result = ns.filter_new_news(all_news, self.LAST_TIME)
        self.assertEqual(len(result), 2)


# ===================================
# 5. 大模型分析测试
# ===================================

FAKE_LLM_RESPONSE = '''以下是分析结果：

```json
{
  "results": [
    {
      "index": 1,
      "worth_collecting": true,
      "value_level": "高",
      "subject": "创新药",
      "reason": "mRNA疫苗突破引爆板块",
      "related_stocks": [
        {"name": "沃森生物", "code": "300142", "strength": 5, "reason": "mRNA疫苗布局"},
        {"name": "键凯科技", "code": "688356", "strength": 99, "reason": "涨停提及"},
        {"name": "", "code": "000001", "strength": 3, "reason": "无效个股应被过滤"},
        "无效条目"
      ]
    },
    {
      "index": 2,
      "worth_collecting": false,
      "value_level": "低",
      "subject": "海外宏观",
      "reason": "与A股关联弱",
      "related_stocks": []
    },
    {
      "index": 3,
      "worth_collecting": true,
      "value_level": "高",
      "subject": "黄金概念",
      "reason": "金价大涨",
      "related_stocks": [{"name": "山东黄金", "code": "600547", "strength": 4, "reason": "黄金主业"}]
    }
  ]
}
```'''


class ParseLLMJsonTestCase(NewsSubjectTestCaseBase):
    """LLM 响应 JSON 解析测试"""

    def setUp(self) -> None:
        super().setUp()
        # 跳过 __init__ 中的真实 LLM 初始化
        self.analyzer = ns.NewsAnalyzer.__new__(ns.NewsAnalyzer)

    def test_parse_markdown_wrapped(self) -> None:
        """markdown 代码块包裹的 JSON 可正常解析"""
        parsed = self.analyzer._parse_llm_json(FAKE_LLM_RESPONSE)
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0]['subject'], '创新药')
        self.assertTrue(parsed[0]['worth_collecting'])
        self.assertFalse(parsed[1]['worth_collecting'])

    def test_parse_plain_json(self) -> None:
        """纯 JSON 响应可正常解析"""
        parsed = self.analyzer._parse_llm_json('{"results": [{"index": 1}]}')
        self.assertEqual(len(parsed), 1)

    def test_parse_no_json(self) -> None:
        """无 JSON 内容时返回空列表"""
        self.assertEqual(self.analyzer._parse_llm_json('抱歉，我无法回答'), [])

    def test_parse_results_not_list(self) -> None:
        """results 非列表时返回空列表"""
        self.assertEqual(self.analyzer._parse_llm_json('{"results": "oops"}'), [])

    def test_parse_invalid_json(self) -> None:
        """JSON 语法错误时返回空列表（不抛异常）"""
        self.assertEqual(self.analyzer._parse_llm_json('```json\n{"results": [}\n```'), [])

    def test_analyze_batch_index_mapping(self) -> None:
        """analyze_batch 的 index 与批内消息编号一一映射"""
        self.analyzer._call_llm = MagicMock(return_value=FAKE_LLM_RESPONSE)
        batch = [make_news(title=f'消息{i}') for i in range(1, 4)]
        result_map = self.analyzer.analyze_batch(batch)

        self.assertEqual(set(result_map.keys()), {0, 1, 2})
        self.assertEqual(result_map[0]['subject'], '创新药')
        self.assertEqual(result_map[2]['subject'], '黄金概念')
        # prompt 中包含各消息标题
        prompt = self.analyzer._call_llm.call_args[0][0]
        for i in range(1, 4):
            self.assertIn(f'消息{i}', prompt)

    def test_analyze_batch_out_of_range_index_ignored(self) -> None:
        """超出批范围的 index 被忽略"""
        self.analyzer._call_llm = MagicMock(
            return_value='{"results": [{"index": 99}, {"index": 0}, {"index": "x"}]}')
        batch = [make_news(title='消息')]
        result_map = self.analyzer.analyze_batch(batch)
        self.assertEqual(result_map, {})


class AnalyzeNewsTestCase(NewsSubjectTestCaseBase):
    """消息批量分析测试（mock NewsAnalyzer）"""

    FAKE_PARSED = [
        {
            'index': 1, 'worth_collecting': True, 'value_level': '高',
            'subject': '创新药', 'reason': 'mRNA疫苗突破引爆板块',
            'related_stocks': [
                {'name': '沃森生物', 'code': '300142', 'strength': 5, 'reason': 'mRNA疫苗布局'},
                {'name': '键凯科技', 'code': '688356', 'strength': 99, 'reason': '涨停提及'},
                {'name': '', 'code': '000001', 'strength': 3, 'reason': '无效个股应被过滤'},
                '无效条目',
            ],
        },
        {
            'index': 2, 'worth_collecting': False, 'value_level': '低',
            'subject': '海外宏观', 'reason': '与A股关联弱', 'related_stocks': [],
        },
        {
            'index': 3, 'worth_collecting': True, 'value_level': '高',
            'subject': '黄金概念', 'reason': '金价大涨',
            'related_stocks': [{'name': '山东黄金', 'code': '600547',
                                'strength': 4, 'reason': '黄金主业'}],
        },
    ]

    def _fake_analyzer_class(self, available=True, batch_result=None, raise_error=False):
        """构造 Fake Analyzer 类"""

        class FakeAnalyzer:
            def __init__(self):
                self._available = available

            def is_available(self):
                return self._available

            def analyze_batch(self, news_batch):
                if raise_error:
                    raise RuntimeError('LLM error')
                if batch_result is not None:
                    return batch_result
                parsed = AnalyzeNewsTestCase.FAKE_PARSED
                return {i: parsed[i] for i in range(min(len(parsed), len(news_batch)))}

        return FakeAnalyzer

    def test_llm_unavailable_degrades(self) -> None:
        """LLM 不可用时降级：消息保留，标记未分析、默认值得采集"""
        news_list = [make_news()]
        with patch.object(ns, 'NewsAnalyzer', self._fake_analyzer_class(available=False)):
            result = ns.analyze_news(news_list)

        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]['analyzed'])
        self.assertTrue(result[0]['worth_collecting'])
        self.assertEqual(result[0]['value_level'], '未分析')
        self.assertEqual(result[0]['related_stocks'], [])

    def test_analyze_fields_processed(self) -> None:
        """正常分析：字段回填、strength 越界截断、无效个股过滤、星级生成"""
        news_list = [make_news(title='消息1'), make_news(title='消息2'), make_news(title='消息3')]
        with patch.object(ns, 'NewsAnalyzer', self._fake_analyzer_class()), \
                patch.object(ns, 'get_config',
                             return_value=MagicMock(gemini_request_delay=0)):
            result = ns.analyze_news(news_list)

        self.assertEqual(len(result), 3)
        n0 = result[0]
        self.assertTrue(n0['analyzed'])
        self.assertTrue(n0['worth_collecting'])
        self.assertEqual(n0['subject'], '创新药')
        self.assertEqual(n0['value_level'], '高')
        # strength=99 截断为 5；无名个股与无效条目被过滤
        stocks = n0['related_stocks']
        self.assertEqual(len(stocks), 2)
        self.assertEqual(stocks[0]['name'], '沃森生物')
        self.assertEqual(stocks[0]['stars'], '✨✨✨✨✨')
        self.assertEqual(stocks[1]['strength'], 5)
        self.assertEqual(stocks[1]['stars'], '✨✨✨✨✨')
        # 低价值消息
        n1 = result[1]
        self.assertFalse(n1['worth_collecting'])
        self.assertEqual(n1['value_level'], '低')
        self.assertEqual(n1['related_stocks'], [])
        # 4星个股
        self.assertEqual(result[2]['related_stocks'][0]['stars'], '✨✨✨✨')

    def test_batch_failure_degrades(self) -> None:
        """某批 LLM 调用失败时该批消息降级为未分析，不中断整体流程"""
        news_list = [make_news(title=f'消息{i}') for i in range(2)]
        with patch.object(ns, 'NewsAnalyzer',
                          self._fake_analyzer_class(raise_error=True)), \
                patch.object(ns, 'get_config',
                             return_value=MagicMock(gemini_request_delay=0)):
            result = ns.analyze_news(news_list)

        self.assertEqual(len(result), 2)
        self.assertTrue(all(not n['analyzed'] for n in result))
        self.assertTrue(all(n['worth_collecting'] for n in result))

    def test_llm_broken_skips_remaining_batches(self) -> None:
        """LLM 调用不通时熔断：第一批失败后不再调用后续批次"""
        news_list = [make_news(title=f'消息{i}')
                     for i in range(ns.LLM_BATCH_SIZE * 3)]

        analyzer = self._fake_analyzer_class(raise_error=True)
        call_count = {'n': 0}

        class CountingBrokenAnalyzer(analyzer):
            def analyze_batch(self, news_batch):
                call_count['n'] += 1
                return super().analyze_batch(news_batch)

        with patch.object(ns, 'NewsAnalyzer', CountingBrokenAnalyzer), \
                patch.object(ns, 'get_config',
                             return_value=MagicMock(gemini_request_delay=0)):
            result = ns.analyze_news(news_list)

        # 只调用了第一批，后续批次被熔断跳过
        self.assertEqual(call_count['n'], 1)
        self.assertEqual(len(result), len(news_list))
        self.assertTrue(all(not n['analyzed'] for n in result))
        self.assertTrue(all(n['worth_collecting'] for n in result))

    def test_batching(self) -> None:
        """超过单批大小时自动分批调用"""
        news_list = [make_news(title=f'消息{i}')
                     for i in range(ns.LLM_BATCH_SIZE * 2 + 1)]

        analyzer = self._fake_analyzer_class()
        call_count = {'n': 0}

        class CountingAnalyzer(analyzer):
            def analyze_batch(self, news_batch):
                call_count['n'] += 1
                return super().analyze_batch(news_batch)

        with patch.object(ns, 'NewsAnalyzer', CountingAnalyzer), \
                patch.object(ns, 'get_config',
                             return_value=MagicMock(gemini_request_delay=0)):
            result = ns.analyze_news(news_list)

        self.assertEqual(call_count['n'], 3)
        self.assertEqual(len(result), len(news_list))

    def test_strength_invalid_defaults_one(self) -> None:
        """strength 非法值兜底为 1"""
        fake = {'results': [{
            'index': 1, 'worth_collecting': True, 'value_level': '高',
            'subject': '测试', 'reason': 'r',
            'related_stocks': [{'name': '测试股', 'code': '000001',
                                'strength': 'abc', 'reason': 'r'}],
        }]}
        response = json.dumps(fake, ensure_ascii=False)

        class FakeAnalyzer:
            def is_available(self):
                return True

            def analyze_batch(self, news_batch):
                return {0: fake['results'][0]}

        news_list = [make_news()]
        with patch.object(ns, 'NewsAnalyzer', FakeAnalyzer), \
                patch.object(ns, 'get_config',
                             return_value=MagicMock(gemini_request_delay=0)):
            result = ns.analyze_news(news_list)

        stock = result[0]['related_stocks'][0]
        self.assertEqual(stock['strength'], 1)
        self.assertEqual(stock['stars'], '✨')


# ===================================
# 6. 题材文件测试（单一文件 + 500KB 滚动）
# ===================================

class SubjectFileTestCase(NewsSubjectTestCaseBase):
    """题材文件查找/加载/保存测试"""

    def test_find_no_file(self) -> None:
        """无题材文件时返回 None"""
        self.assertIsNone(ns.find_subject_file())

    def test_find_latest_file(self) -> None:
        """多个题材文件时返回修改时间最新的一个"""
        f1 = os.path.join(ns.DATA_DIR, '20260820100000_new_subjects.json')
        f2 = os.path.join(ns.DATA_DIR, '20260820120000_new_subjects.json')
        self.write_json(f1, [])
        self.write_json(f2, [])
        # 确保 f2 的 mtime 更新
        os.utime(f2, (time.time() + 10, time.time() + 10))

        self.assertEqual(ns.find_subject_file(), f2)

    def test_find_ignores_other_files(self) -> None:
        """非题材文件不参与查找"""
        self.write_json(os.path.join(ns.DATA_DIR, 'readme.md'), {})
        self.assertIsNone(ns.find_subject_file())

    def test_load_empty(self) -> None:
        """空列表文件加载正常"""
        f = os.path.join(ns.DATA_DIR, '20260820100000_new_subjects.json')
        self.write_json(f, [])
        self.assertEqual(ns.load_library(f), [])

    def test_load_corrupted(self) -> None:
        """损坏文件容错为空列表"""
        f = os.path.join(ns.DATA_DIR, '20260820100000_new_subjects.json')
        self.write_json(f, '[[[broken')
        self.assertEqual(ns.load_library(f), [])

    def test_load_invalid_type(self) -> None:
        """内容非列表时容错为空列表"""
        f = os.path.join(ns.DATA_DIR, '20260820100000_new_subjects.json')
        self.write_json(f, {'not': 'a list'})
        self.assertEqual(ns.load_library(f), [])

    def test_save_naming_and_sorting(self) -> None:
        """保存：文件名为生成时间 YYYYMMDDHHMM_new_subjects.json，按发布时间倒序"""
        library = [
            {'title': '旧消息', 'publish_time': '2026-08-18 10:00:00'},
            {'title': '新消息', 'publish_time': '2026-08-20 10:00:00'},
        ]
        path = ns.save_subject_file(library)

        expected_name = datetime.now().strftime('%Y%m%d%H%M') + '_new_subjects.json'
        self.assertEqual(os.path.basename(path), expected_name)
        saved = self.read_json(path)
        self.assertEqual([n['title'] for n in saved], ['新消息', '旧消息'])

    def test_save_removes_prev_file(self) -> None:
        """续写场景：保存新文件后删除旧文件（重命名语义）"""
        prev = os.path.join(ns.DATA_DIR, '20260820100000_new_subjects.json')
        self.write_json(prev, [{'title': '旧', 'publish_time': ''}])

        ns.save_subject_file([{'title': '新', 'publish_time': ''}], prev_file=prev)

        self.assertFalse(os.path.exists(prev))
        self.assertEqual(len(self.subject_files()), 1)

    def test_save_same_minute_no_self_delete(self) -> None:
        """同一分钟内重复保存：新旧文件同名，不误删刚写入的文件"""
        prev = os.path.join(
            ns.DATA_DIR, datetime.now().strftime('%Y%m%d%H%M') + '_new_subjects.json')
        self.write_json(prev, [{'title': '旧', 'publish_time': ''}])

        path = ns.save_subject_file(
            [{'title': '新', 'publish_time': ''}], prev_file=prev)

        self.assertTrue(os.path.exists(path))
        saved = self.read_json(path)
        self.assertEqual(saved[0]['title'], '新')

    def test_save_keeps_archived_file(self) -> None:
        """归档场景（prev_file=None）：旧文件保留"""
        archived = os.path.join(ns.DATA_DIR, '20260820100000_new_subjects.json')
        self.write_json(archived, [])

        ns.save_subject_file([{'title': '新', 'publish_time': ''}], prev_file=None)

        self.assertTrue(os.path.exists(archived))
        self.assertEqual(len(self.subject_files()), 2)


class MergeIntoLibraryTestCase(NewsSubjectTestCaseBase):
    """题材条目合并测试"""

    def test_merge_new_entry_added(self) -> None:
        """值得采集的新消息追加进题材库"""
        library = []
        news = make_analyzed(title='新题材消息', related_stocks=[
            {'name': '测试股', 'code': '000001', 'strength': 3, 'stars': '✨✨✨', 'reason': 'r'}])
        added = ns.merge_into_library(library, [news])

        self.assertEqual(added, 1)
        self.assertEqual(len(library), 1)
        entry = library[0]
        self.assertEqual(entry['title'], '新题材消息')
        self.assertEqual(entry['subject'], '测试题材')
        self.assertEqual(entry['related_stocks'][0]['name'], '测试股')
        self.assertIn('collect_time', entry)
        # 输出字段包含需求要求的：标题/内容/发布时间/来源/题材/关联个股强度
        for field in ('title', 'content', 'publish_time', 'sources',
                      'subject', 'value_level', 'related_stocks'):
            self.assertIn(field, entry)

    def test_merge_skips_not_worth(self) -> None:
        """不值得采集的消息不进题材库"""
        library = []
        news = make_analyzed(worth_collecting=False)
        added = ns.merge_into_library(library, [news])
        self.assertEqual(added, 0)
        self.assertEqual(library, [])

    def test_merge_same_url_merges(self) -> None:
        """URL 相同的消息合并：来源/链接合并、内容取长、个股强度取强"""
        lib_entry = {
            'title': '原始消息', 'content': '短', 'publish_time': '2026-08-20 09:00:00',
            'sources': ['东方财富-东方视点'], 'urls': ['http://em/1'],
            'subject': '创新药', 'value_level': '高', 'reason': 'r',
            'related_stocks': [
                {'name': '沃森生物', 'code': '300142', 'strength': 5, 'stars': '✨✨✨✨✨', 'reason': 'a'},
                {'name': '康希诺', 'code': '688185', 'strength': 3, 'stars': '✨✨✨', 'reason': 'b'},
            ],
        }
        library = [lib_entry]
        news = make_analyzed(
            title='不同标题但同 URL', content='更长的内容' * 20, url='http://em/1',
            sources=['华尔街见闻-A股新闻'], urls=['http://em/1'],
            related_stocks=[
                {'name': '沃森生物', 'code': '300142', 'strength': 3, 'stars': '✨✨✨', 'reason': 'c'},
                {'name': '三元基因', 'code': '833457', 'strength': 5, 'stars': '✨✨✨✨✨', 'reason': 'd'},
            ])
        added = ns.merge_into_library(library, [news])

        self.assertEqual(added, 0)  # 未新增，只合并
        self.assertEqual(len(library), 1)
        merged = library[0]
        # 来源合并
        self.assertEqual(merged['sources'], ['东方财富-东方视点', '华尔街见闻-A股新闻'])
        # 内容取长
        self.assertTrue(merged['content'].startswith('更长的内容'))
        # 个股合并：沃森生物保留强度5；新增三元基因；康希诺保留
        stock_map = {s['name']: s for s in merged['related_stocks']}
        self.assertEqual(stock_map['沃森生物']['strength'], 5)
        self.assertEqual(stock_map['三元基因']['strength'], 5)
        self.assertIn('康希诺', stock_map)
        self.assertEqual(len(merged['related_stocks']), 3)

    def test_merge_similar_title_merges(self) -> None:
        """标题相似（URL不同）的消息合并为一条"""
        lib_entry = {
            'title': 'mRNA癌症疫苗迎重磅突破！Moderna单日暴涨177%',
            'content': 'x', 'publish_time': '2026-08-20 09:00:00',
            'sources': ['东方财富-东方视点'], 'urls': ['http://em/1'],
            'subject': '', 'value_level': '', 'reason': '',
            'related_stocks': [],
        }
        library = [lib_entry]
        news = make_analyzed(
            title='mRNA癌症疫苗迎重磅突破！Moderna单日暴涨177%',
            url='http://wscn/1', sources=['华尔街见闻-美股新闻'], urls=['http://wscn/1'],
            subject='创新药', value_level='高')
        added = ns.merge_into_library(library, [news])

        self.assertEqual(added, 0)
        self.assertEqual(len(library), 1)
        merged = library[0]
        # 链接合并；原库空 subject 时补齐
        self.assertEqual(set(merged['urls']), {'http://em/1', 'http://wscn/1'})
        self.assertEqual(merged['subject'], '创新药')
        self.assertEqual(merged['value_level'], '高')

    def test_merge_keeps_existing_analysis(self) -> None:
        """合并时不覆盖已有非空 subject/value_level"""
        lib_entry = {
            'title': '消息', 'content': '', 'publish_time': '',
            'sources': ['A'], 'urls': ['http://a/1'],
            'subject': '原题材', 'value_level': '高', 'reason': '',
            'related_stocks': [],
        }
        library = [lib_entry]
        news = make_analyzed(title='消息', url='http://a/1',
                             subject='新题材', value_level='低')
        ns.merge_into_library(library, [news])
        self.assertEqual(library[0]['subject'], '原题材')
        self.assertEqual(library[0]['value_level'], '高')


class UploadTestCase(NewsSubjectTestCaseBase):
    """Gitee 上传/删除容错测试"""

    def test_upload_success(self) -> None:
        """上传成功：调用 client.upload_binary_file，目标为 news 目录"""
        client = MagicMock()
        client.upload_binary_file.return_value = True

        ok = ns.upload_news_to_gitee(client, 'some/path/20260820120000_new_subjects.json')

        self.assertTrue(ok)
        client.upload_binary_file.assert_called_once()
        args, kwargs = client.upload_binary_file.call_args
        self.assertEqual(args[0], 'some/path/20260820120000_new_subjects.json')
        self.assertEqual(args[1], 'news/20260820120000_new_subjects.json')
        self.assertIn('20260820120000_new_subjects.json', kwargs.get('message', ''))

    def test_upload_failure_tolerated(self) -> None:
        """上传失败（返回 False）不抛异常"""
        client = MagicMock()
        client.upload_binary_file.return_value = False
        self.assertFalse(ns.upload_news_to_gitee(client, 'some/path/f.json'))

    def test_upload_exception_tolerated(self) -> None:
        """上传异常不抛异常，不影响本地结果"""
        client = MagicMock()
        client.upload_binary_file.side_effect = RuntimeError('network')
        self.assertFalse(ns.upload_news_to_gitee(client, 'some/path/f.json'))

    def test_delete_success(self) -> None:
        """删除成功：调用 client.delete_file，目标为 news 目录"""
        client = MagicMock()
        client.delete_file.return_value = True

        ok = ns.delete_remote_news_file(client, '20260820120000_new_subjects.json')

        self.assertTrue(ok)
        args, kwargs = client.delete_file.call_args
        self.assertEqual(args[0], 'news/20260820120000_new_subjects.json')
        self.assertIn('20260820120000_new_subjects.json', kwargs.get('message', ''))

    def test_delete_failure_tolerated(self) -> None:
        """删除失败不抛异常"""
        client = MagicMock()
        client.delete_file.return_value = False
        self.assertFalse(ns.delete_remote_news_file(client, 'f.json'))

    def test_delete_exception_tolerated(self) -> None:
        """删除异常不抛异常"""
        client = MagicMock()
        client.delete_file.side_effect = RuntimeError('boom')
        self.assertFalse(ns.delete_remote_news_file(client, 'f.json'))


# ===================================
# 8. 主流程测试（全链路 mock）
# ===================================

class FakeDatetime(datetime):
    """固定 now() 的 datetime 子类（保留 strptime/fromtimestamp 等原生行为）"""

    @classmethod
    def now(cls, tz=None):
        return cls(2026, 8, 20, 23, 59)


class RunFlowTestCase(NewsSubjectTestCaseBase):
    """run() 主流程测试（全链路 mock Gitee）"""

    @staticmethod
    def _analyzed(news_batch, worth=True):
        """构造带分析字段的消息列表"""
        analyzed = []
        for n in news_batch:
            item = dict(n)
            item.update({
                'analyzed': True, 'worth_collecting': worth,
                'value_level': '高' if worth else '低',
                'subject': '测试题材', 'reason': 'r',
                'related_stocks': [{'name': '测试股', 'code': '000001',
                                    'strength': 4, 'stars': '✨✨✨✨', 'reason': 'r'}],
                'sources': [n['source']], 'urls': [n['url']],
            })
            analyzed.append(item)
        return analyzed

    def _mock_pipeline(self, news_batch, worth=True, remote=None):
        """
        mock 采集/分析/Gitee 链路

        remote 为 None 时模拟 Gitee news 目录无历史文件
        """
        if remote is None:
            remote = {'name': None, 'library': [], 'size': 0, 'error': None}
        analyzed = self._analyzed(news_batch, worth=worth)

        mocks = {}
        mocks['client'] = patch.object(ns, 'GiteeClient', return_value=MagicMock())
        mocks['remote'] = patch.object(ns, 'fetch_latest_remote_news',
                                       return_value=remote)
        mocks['collect'] = patch.object(ns, 'collect_all_news', return_value=list(news_batch))
        mocks['analyze'] = patch.object(ns, 'analyze_news', side_effect=lambda x: analyzed)
        mocks['upload'] = patch.object(ns, 'upload_news_to_gitee', return_value=True)
        mocks['delete'] = patch.object(ns, 'delete_remote_news_file', return_value=True)
        return mocks

    def test_run_first_time_full_flow(self) -> None:
        """首次运行（Gitee 无历史文件）：生成题材文件（仅重要消息）并上传"""
        now = datetime.now()
        news = [
            make_news(title='消息A',
                      publish_time=(now - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S'),
                      url='http://a/1'),
            make_news(title='消息B',
                      publish_time=(now - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S'),
                      url='http://a/2'),
        ]
        mocks = self._mock_pipeline(news)

        with mocks['client'], mocks['remote'], mocks['collect'], mocks['analyze'], \
                mocks['upload'] as mock_upload, mocks['delete'] as mock_delete:
            rc = ns.run()

        self.assertEqual(rc, 0)

        # 题材文件：唯一一个，命名为生成时间，包含全部重要消息
        files = self.subject_files()
        self.assertEqual(len(files), 1)
        self.assertRegex(os.path.basename(files[0]),
                         r'^\d{12}_new_subjects\.json$')
        entries = self.read_json(files[0])
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]['title'], '消息B')  # 按发布时间倒序
        self.assertEqual(entries[0]['related_stocks'][0]['stars'], '✨✨✨✨')
        # 上传被调用
        mock_upload.assert_called_once()
        # 首次运行无旧远程文件，不删除
        mock_delete.assert_not_called()

    def test_run_only_important_news_saved(self) -> None:
        """只保留重要消息：不重要消息不写入题材文件"""
        now = datetime.now()
        news = [
            make_news(title='重要消息',
                      publish_time=(now - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S'),
                      url='http://a/1'),
            make_news(title='不重要消息',
                      publish_time=(now - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S'),
                      url='http://a/2'),
        ]
        analyzed = []
        for n in news:
            worth = n['title'] == '重要消息'
            item = dict(n)
            item.update({
                'analyzed': True, 'worth_collecting': worth,
                'value_level': '高' if worth else '低', 'subject': '测试题材' if worth else '',
                'reason': 'r', 'related_stocks': [], 'sources': [n['source']], 'urls': [n['url']],
            })
            analyzed.append(item)

        remote = {'name': None, 'library': [], 'size': 0, 'error': None}
        with patch.object(ns, 'GiteeClient', return_value=MagicMock()), \
                patch.object(ns, 'fetch_latest_remote_news', return_value=remote), \
                patch.object(ns, 'collect_all_news', return_value=news), \
                patch.object(ns, 'analyze_news', side_effect=lambda x: analyzed), \
                patch.object(ns, 'upload_news_to_gitee', return_value=True):
            rc = ns.run()

        self.assertEqual(rc, 0)
        entries = self.read_json(self.subject_files()[0])
        titles = [n['title'] for n in entries]
        self.assertEqual(titles, ['重要消息'])

    def test_run_increments_from_remote_file(self) -> None:
        """增量采集：以 Gitee 最近文件名为采集起点，合并进远程库并删除旧远程文件"""
        # 远程已有文件（生成于 22:44），库内已有消息A
        remote = {
            'name': '202608202244_new_subjects.json',
            'library': [{
                'title': '消息A', 'content': '短', 'publish_time': '2026-08-20 10:00:00',
                'sources': ['东方财富-东方视点'], 'urls': ['http://a/1'],
                'subject': '测试题材', 'value_level': '高', 'reason': 'r',
                'related_stocks': [],
            }],
            'size': 2048, 'error': None,
        }
        # 采集到：消息A（重复）与消息C（新，发布于 22:44 之后）
        news = [make_news(title='消息A', publish_time='2026-08-20 10:00:00', url='http://a/1'),
                make_news(title='消息C', publish_time='2026-08-20 23:00:00', url='http://a/3')]
        mocks = self._mock_pipeline(news, remote=remote)

        with mocks['client'], mocks['remote'], mocks['collect'], mocks['analyze'], \
                mocks['upload'] as mock_upload, mocks['delete'] as mock_delete, \
                patch.object(ns, 'datetime', FakeDatetime):
            rc = ns.run()

        self.assertEqual(rc, 0)
        # 本地生成新文件 202608202359，远程旧文件已删除
        mock_upload.assert_called_once()
        mock_delete.assert_called_once()
        args = mock_delete.call_args[0]
        self.assertIn('202608202244_new_subjects.json', args)

        files = self.subject_files()
        self.assertEqual(len(files), 1)
        self.assertEqual(os.path.basename(files[0]), '202608202359_new_subjects.json')
        entries = self.read_json(files[0])
        # 消息A 与远程库重复合并，新增消息C，共 2 条
        titles = [n['title'] for n in entries]
        self.assertEqual(titles, ['消息C', '消息A'])

    def test_run_remote_error_aborts(self) -> None:
        """远程文件读取失败：中止返回 1，不采集不上传（防止误删远端数据）"""
        remote = {'name': '202608202244_new_subjects.json', 'library': [],
                  'size': 0, 'error': '下载远程题材文件失败'}
        mocks = self._mock_pipeline([make_news(title='消息A')], remote=remote)

        with mocks['client'], mocks['remote'], mocks['collect'] as mock_collect, \
                mocks['upload'] as mock_upload, mocks['delete'] as mock_delete:
            rc = ns.run()

        self.assertEqual(rc, 1)
        mock_collect.assert_not_called()
        mock_upload.assert_not_called()
        mock_delete.assert_not_called()

    def test_run_rolls_when_remote_file_exceeds_limit(self) -> None:
        """远程题材文件超 500KB：归档（不删除远程旧文件），新开文件只含本次新增"""
        remote = {
            'name': '202608202244_new_subjects.json',
            'library': [{'title': '旧消息', 'publish_time': '2026-08-20 10:00:00',
                         'sources': ['A'], 'urls': ['http://a/1'],
                         'subject': 's', 'value_level': '高', 'reason': '',
                         'related_stocks': []}],
            'size': 600 * 1024, 'error': None,
        }
        news = [make_news(title='新消息', publish_time='2026-08-20 23:00:00', url='http://a/3')]
        mocks = self._mock_pipeline(news, remote=remote)

        with mocks['client'], mocks['remote'], mocks['collect'], mocks['analyze'], \
                mocks['upload'] as mock_upload, mocks['delete'] as mock_delete, \
                patch.object(ns, 'datetime', FakeDatetime):
            rc = ns.run()

        self.assertEqual(rc, 0)
        mock_upload.assert_called_once()
        # 归档场景：不删除远程旧文件
        mock_delete.assert_not_called()

        files = self.subject_files()
        self.assertEqual(len(files), 1)
        self.assertEqual(os.path.basename(files[0]), '202608202359_new_subjects.json')
        # 新开文件只包含本次新增消息（旧库归档不合并）
        entries = self.read_json(files[0])
        self.assertEqual([n['title'] for n in entries], ['新消息'])

    def test_run_same_minute_no_remote_delete(self) -> None:
        """同分钟重跑：新文件与远程旧文件同名，不删除（防止误删刚上传的文件）"""
        same_name = f"{datetime.now().strftime('%Y%m%d%H%M')}_new_subjects.json"
        remote = {
            'name': same_name,
            'library': [{'title': '消息A', 'publish_time': '2026-08-20 10:00:00',
                         'sources': ['A'], 'urls': ['http://a/1'],
                         'subject': 's', 'value_level': '高', 'reason': '',
                         'related_stocks': []}],
            'size': 2048, 'error': None,
        }
        news = [make_news(
            title='消息C',
            publish_time=(datetime.now() + timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S'),
            url='http://a/3')]
        mocks = self._mock_pipeline(news, remote=remote)

        with mocks['client'], mocks['remote'], mocks['collect'], mocks['analyze'], \
                mocks['upload'] as mock_upload, mocks['delete'] as mock_delete:
            rc = ns.run()

        self.assertEqual(rc, 0)
        mock_upload.assert_called_once()
        mock_delete.assert_not_called()

    def test_run_upload_failure_keeps_remote_file(self) -> None:
        """上传失败：不删除远程旧文件（防止数据丢失），本地结果保留"""
        remote = {
            'name': '202608202244_new_subjects.json',
            'library': [], 'size': 2048, 'error': None,
        }
        news = [make_news(title='消息C', publish_time='2026-08-20 23:00:00', url='http://a/3')]
        mocks = self._mock_pipeline(news, remote=remote)
        mocks['upload'] = patch.object(ns, 'upload_news_to_gitee', return_value=False)

        with mocks['client'], mocks['remote'], mocks['collect'], mocks['analyze'], \
                mocks['upload'], mocks['delete'] as mock_delete:
            rc = ns.run()

        self.assertEqual(rc, 0)
        # 上传失败不删除远程旧文件
        mock_delete.assert_not_called()
        # 本地文件仍生成
        self.assertEqual(len(self.subject_files()), 1)

    def test_run_no_new_news_no_upload(self) -> None:
        """无新消息（时间过滤后为空）：不生成文件、不上传"""
        # 远程文件生成于 22:44，采集到的消息都早于该时间
        remote = {'name': '202608202244_new_subjects.json',
                  'library': [], 'size': 2048, 'error': None}
        news = [make_news(title='旧消息', publish_time='2026-08-20 10:00:00', url='http://a/1')]
        mocks = self._mock_pipeline(news, remote=remote)

        with mocks['client'], mocks['remote'], mocks['collect'], mocks['analyze'], \
                mocks['upload'] as mock_upload, mocks['delete'] as mock_delete:
            rc = ns.run()

        self.assertEqual(rc, 0)
        self.assertEqual(self.subject_files(), [])
        mock_upload.assert_not_called()
        mock_delete.assert_not_called()

    def test_run_no_worth_news_no_file(self) -> None:
        """有新消息但均不重要：不生成题材文件、不上传"""
        news = [make_news(title='不重要消息', publish_time='2026-08-20 23:00:00', url='http://a/1')]
        mocks = self._mock_pipeline(news, worth=False)

        with mocks['client'], mocks['remote'], mocks['collect'], mocks['analyze'], \
                mocks['upload'] as mock_upload, mocks['delete'] as mock_delete:
            rc = ns.run()

        self.assertEqual(rc, 0)
        self.assertEqual(self.subject_files(), [])
        mock_upload.assert_not_called()
        mock_delete.assert_not_called()

    def test_run_analyze_failure_returns_1(self) -> None:
        """分析环节抛异常时整体流程失败返回 1"""
        remote = {'name': None, 'library': [], 'size': 0, 'error': None}
        news = [make_news(
            title='消息A',
            publish_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))]
        with patch.object(ns, 'GiteeClient', return_value=MagicMock()), \
                patch.object(ns, 'fetch_latest_remote_news', return_value=remote), \
                patch.object(ns, 'collect_all_news', return_value=news), \
                patch.object(ns, 'analyze_news', side_effect=RuntimeError('LLM down')), \
                patch.object(ns, 'upload_news_to_gitee', return_value=True):
            rc = ns.run()
        self.assertEqual(rc, 1)

    def test_run_empty_collect(self) -> None:
        """采集完全无数据：正常结束返回 0，不生成题材文件"""
        remote = {'name': None, 'library': [], 'size': 0, 'error': None}
        with patch.object(ns, 'GiteeClient', return_value=MagicMock()), \
                patch.object(ns, 'fetch_latest_remote_news', return_value=remote), \
                patch.object(ns, 'collect_all_news', return_value=[]), \
                patch.object(ns, 'upload_news_to_gitee', return_value=True):
            rc = ns.run()
        self.assertEqual(rc, 0)
        self.assertEqual(self.subject_files(), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
