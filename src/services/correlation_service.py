# -*- coding: utf-8 -*-
"""
===================================
涨停关联分析 - 统计与归因引擎
===================================

职责：
1. build_stats:     基于 stock_limit_up（龙头）与 stock_hot_subject（候选跟风股）
                    构建 (龙头A, 跟风B) 历史联动统计（T+0 / T+1 双窗口 + lift）
2. find_related:    输入今日涨停股 A，输出历史强关联跟风股列表
3. attribute:       输入今日涨停股 A，输出涨停归因链（谁带动了 A）

关联通道：
- sector: A.关联板块名称 == B.板块名称
- theme:  A.个股涨停原因 与 B.简介/研报标题 的字符 bigram 重合度（overlap coefficient）

已知口径限制（一期）：
- B 的 T+1 数据来自 hot_subject 次日记录，次日不热门则无记录，胜率略偏高（热门股内口径）
- 无分钟级数据，T+0 跟随以 B 当日涨跌幅近似
"""

import logging
import re
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from src.repositories.correlation_repo import CorrelationRepository

logger = logging.getLogger(__name__)

# 有效关联门槛
MIN_SAMPLES = 8          # 历史联动次数下限
MIN_LIFT = 1.4           # 提升度下限（条件延续率 / 无条件延续率）
MIN_NEXT_DAY_PCT = 0.015  # 次日平均涨幅下限（源表涨跌幅为小数比例，0.015 = 1.5%）
RECENT_DAYS = 60         # 最近联动有效天数（自然日，用于展示层衰减提示）
THEME_SIM_THRESHOLD = 0.35  # 题材文本重合度阈值（overlap coefficient）


def _char_bigrams(text: Optional[str]) -> set:
    """中文文本字符 bigram 集合（去除标点/空白）"""
    if not text:
        return set()
    cleaned = re.sub(r'[^\w\u4e00-\u9fff]+', '', str(text))
    if len(cleaned) < 2:
        return {cleaned} if cleaned else set()
    return {cleaned[i:i + 2] for i in range(len(cleaned) - 1)}


def text_overlap(a: Optional[str], b: Optional[str]) -> float:
    """overlap coefficient = |A∩B| / min(|A|,|B|)，适合长短文本的主题包含判断"""
    ga, gb = _char_bigrams(a), _char_bigrams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / min(len(ga), len(gb))


def _parse_limit_time(t: Optional[str]) -> Optional[int]:
    """'2026-08-31 09:36:28' -> 当日分钟序数（9:36 -> 576），解析失败返回 None"""
    if not t or len(t) < 19:
        return None
    try:
        hh, mm = int(t[11:13]), int(t[14:16])
        return hh * 60 + mm
    except (ValueError, IndexError):
        return None


class CorrelationService:
    """涨停关联分析与归因服务"""

    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            from src.config import Config
            cfg = Config.get_instance()
            db_path = getattr(cfg, 'correlation_db_path', '') or ''
        self.repo = CorrelationRepository(db_path)

    # ================= build_stats =================

    def build_stats(self) -> Dict:
        """
        全量构建 pair_stats。

        龙头池：limit_up 中 连续涨停天数=1（首板）、非新股的股票
        候选B池：A 首板日热门 ∪ 次日热门（A 本身除外），覆盖当日跟风与次日跟风两种模式

        核心口径（热门股 universe 内，涨跌幅不可作胜率——股票因上涨才入选热门）：
        - 联动事件 = A 首板窗口内（当日或次日）B 上热门（当日跟风 / 次日跟风）
        - 延续事件 = 联动事件后一交易日 B 仍热门
        - B 无条件延续率 = P(B 下一交易日仍热门 | B 当日热门)，B 自身热度惯性基准
        - lift = P(B 延续 | A 首板联动) / B 无条件延续率
        """
        dates = self.repo.get_hot_subject_dates()
        if not dates:
            return {'days': 0, 'pairs': 0, 'leaders': 0, 'error': 'stock_hot_subject 无数据'}

        limit_baselines = self.repo.get_follower_baselines()
        # 预加载全部日期的热门股（140 天 x ~100 行，内存无压力）
        all_hot: Dict[str, Dict[str, object]] = {
            d: self.repo.get_hot_subject_by_date(d) for d in dates}
        # 延续率基准: code -> [当日热门且有次日的天数, 次日仍热门天数]
        persist: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
        for i, day in enumerate(dates):
            hot_today = all_hot[day]
            hot_next = all_hot.get(dates[i + 1]) if i + 1 < len(dates) else None
            if hot_next is not None:
                for code in hot_today:
                    persist[code][0] += 1
                    if code in hot_next:
                        persist[code][1] += 1

        # 观测累积: (A, B, channel) -> 聚合字段
        agg: Dict[Tuple[str, str, str], dict] = defaultdict(lambda: {
            'n': 0, 'follow_limit': 0, 'follow_pct_sum': 0.0, 'follow_cnt': 0,
            'next_follow': 0,
            'persist': 0, 'persist_pct_sum': 0.0, 'persist_cnt': 0,
            'first_date': None, 'last_date': None,
        })
        # 预计算每日每只热门股的文本 bigram（题材通道用）
        hot_grams: Dict[str, Dict[str, set]] = {
            d: {code: _char_bigrams(f"{r['简介'] or ''}{r['研报标题'] or ''}")
                for code, r in hot.items()}
            for d, hot in all_hot.items()
        }

        total_leaders = 0
        for i, day in enumerate(dates):
            leaders = self._get_leaders(day)
            if not leaders:
                continue
            hot_today = all_hot[day]
            hot_next = all_hot.get(dates[i + 1]) if i + 1 < len(dates) else None
            hot_next2 = all_hot.get(dates[i + 2]) if i + 2 < len(dates) else None
            # 候选 B：当日热门 ∪ 次日热门（次日才上热门 = 次日跟风模式）
            candidates = set(hot_today) | (set(hot_next) if hot_next else set())

            total_leaders += len(leaders)
            for a in leaders:
                a_code = a['股票代码']
                a_sector = (a['关联板块名称'] or '').strip()
                a_grams = _char_bigrams(a['个股涨停原因'])

                for b_code in candidates:
                    if b_code == a_code:
                        continue
                    # 确定事件类型与事件日数据：
                    # 当日跟风（B 当日热门，延续看次日）/ 次日跟风（B 次日才热门，延续看第三日）
                    if b_code in hot_today:
                        event_offset = 0
                        b_row = hot_today[b_code]
                        event_day = day
                        next_hot = hot_next
                    else:
                        event_offset = 1
                        b_row = hot_next[b_code]
                        event_day = dates[i + 1]
                        next_hot = hot_next2

                    # 通道匹配（用事件日的 B 记录）
                    obs = None
                    if a_sector and (b_row['板块名称'] or '').strip() == a_sector:
                        obs = agg[(a_code, b_code, 'sector')]
                    else:
                        b_g = hot_grams[event_day].get(b_code)
                        if a_grams and b_g:
                            inter = len(a_grams & b_g)
                            if inter and inter / min(len(a_grams), len(b_g)) >= THEME_SIM_THRESHOLD:
                                obs = agg[(a_code, b_code, 'theme')]
                    if obs is None:
                        continue

                    persist_row = next_hot.get(b_code) if next_hot else None
                    self._accumulate(
                        obs, day, event_offset,
                        b_row['涨跌幅'], b_row['是否涨停'],
                        persist_row is not None,
                        persist_row['涨跌幅'] if persist_row is not None else None,
                    )

        rows = self._finalize(agg, persist, limit_baselines)
        written = self.repo.replace_pair_stats(rows)
        result = {'days': len(dates), 'leaders': total_leaders, 'pairs': written}
        logger.info("pair_stats 构建完成: %s", result)
        return result

    def _get_leaders(self, day: str) -> List:
        """某日龙头池：首板 + 非新股"""
        return [r for r in self.repo.get_limit_up_by_date(day)
                if (r['连续涨停天数'] or 0) == 1
                and not (r['是否新股'] or 0)
                and r['股票代码']]

    @staticmethod
    def _accumulate(obs: dict, day: str, event_offset: int,
                    follow_pct: Optional[float], follow_limit: Optional[int],
                    persist_flag: bool, persist_pct: Optional[float]) -> None:
        obs['n'] += 1
        if obs['first_date'] is None:
            obs['first_date'] = day
        obs['last_date'] = day
        if follow_pct is not None:
            obs['follow_cnt'] += 1
            obs['follow_pct_sum'] += follow_pct
        if follow_limit:
            obs['follow_limit'] += 1
        if event_offset == 1:
            obs['next_follow'] += 1
        if persist_flag:
            obs['persist'] += 1
            if persist_pct is not None:
                obs['persist_cnt'] += 1
                obs['persist_pct_sum'] += persist_pct

    @staticmethod
    def _finalize(agg: Dict[Tuple[str, str, str], dict],
                  persist: Dict[str, List[int]],
                  limit_baselines: Dict[str, Tuple[float, int]]) -> List[Tuple]:
        import time
        now = int(time.time())
        rows = []
        for (a, b, channel), o in agg.items():
            # 延续率基准（B 自身热度惯性）
            p_n, p_k = persist.get(b, (0, 0))
            persist_base = (p_k / p_n) if p_n else None
            limit_base = limit_baselines.get(b, (None, 0))[0]
            persist_rate = (o['persist'] / o['n']) if o['n'] else None
            lift = None
            if persist_rate is not None and persist_base and persist_base >= 0.05:
                lift = persist_rate / persist_base
            rows.append((
                a, b, channel, o['n'],
                o['follow_limit'],
                (o['follow_pct_sum'] / o['follow_cnt']) if o['follow_cnt'] else None,
                o['next_follow'],
                o['persist'],
                (o['persist_pct_sum'] / o['persist_cnt']) if o['persist_cnt'] else None,
                persist_base, limit_base, lift,
                o['first_date'], o['last_date'], now,
            ))
        return rows

    # ================= find_related =================

    def find_related(self, code: str, date: Optional[str] = None,
                     top_n: int = 20) -> Dict:
        """
        输入涨停股 A，输出历史强关联跟风股列表。

        date 缺省取 A 最近一次涨停日期；若 A 当日未涨停则回退并提示。
        """
        code = code.strip()
        latest = date or self.repo.get_latest_limit_up_date_of(code)
        if not latest:
            return {'code': code, 'error': f'{code} 在 stock_limit_up 中无涨停记录'}

        day_rows = {r['股票代码']: r for r in self.repo.get_limit_up_by_date(latest)}
        a_row = day_rows.get(code)
        if not a_row:
            return {'code': code, 'error': f'{code} 在 {latest} 无涨停记录（该股最近涨停日请用 --correlation-date 指定）'}

        stats = self.repo.query_pair_stats_by_leader(code, MIN_SAMPLES, MIN_LIFT)
        hot_today = self.repo.get_hot_subject_by_date(latest)

        # A 自身画像
        sector = (a_row['关联板块名称'] or '').strip()
        sector_count = sum(1 for r in day_rows.values()
                           if (r['关联板块名称'] or '').strip() == sector) if sector else 0

        related = []
        for s in stats:
            b_code = s['跟风B']
            avg_next = s['B延续平均涨幅']
            if avg_next is not None and avg_next < MIN_NEXT_DAY_PCT:
                continue
            b_today = hot_today.get(b_code)
            status = '无当日热门记录'
            if b_today is not None:
                pct = b_today['涨跌幅']  # 小数比例
                if b_today['是否涨停']:
                    status = f'已联动涨停（当日涨幅 {pct * 100:+.1f}%），次日关注溢价'
                elif pct is not None and pct >= 0.05:
                    status = f'当日已涨 {pct * 100:+.1f}%，T+0 跟风已兑现'
                elif pct is not None:
                    status = f'当日 {pct * 100:+.1f}%，T+1 候选：观察次日竞价是否高开 > 2%'
            related.append({
                'code': b_code,
                'name': self.repo.get_stock_name(b_code),
                'channel': s['关联通道'],
                'samples': s['样本数'],
                't1_persist_rate': (s['B延续热门次数'] / s['样本数']) if s['样本数'] else None,
                'lift': s['lift'],
                't1_avg_pct': avg_next,
                't0_avg_pct': s['B跟风平均涨幅'],
                't0_limit_count': s['B跟风涨停次数'],
                'next_follow_count': s['B次日跟风次数'],
                'last_date': s['最近联动日期'],
                'today_status': status,
            })
        related.sort(key=lambda x: (x['lift'] or 0), reverse=True)

        # 低样本观察：不足门槛的关联对（历史联动 < 8 次），仅供人工参考
        observation = []
        if len(related) < top_n:
            qualified_keys = {(r['code'], r['channel']) for r in related}
            for s in self.repo.query_all_pair_stats_by_leader(code):
                if len(observation) >= top_n:
                    break
                key = (s['跟风B'], s['关联通道'])
                if key in qualified_keys:
                    continue
                observation.append({
                    'code': s['跟风B'],
                    'name': self.repo.get_stock_name(s['跟风B']),
                    'channel': s['关联通道'],
                    'samples': s['样本数'],
                    't1_persist_rate': (s['B延续热门次数'] / s['样本数']) if s['样本数'] else None,
                    'lift': s['lift'],
                    't1_avg_pct': s['B延续平均涨幅'],
                    't0_avg_pct': s['B跟风平均涨幅'],
                    't0_limit_count': s['B跟风涨停次数'],
                    'next_follow_count': s['B次日跟风次数'],
                    'last_date': s['最近联动日期'],
                    'today_status': self._today_status(hot_today.get(s['跟风B'])),
                })

        return {
            'code': code,
            'name': a_row['股票中文名称'],
            'date': latest,
            'first_limit_time': a_row['首次涨停时间'],
            'sector': sector,
            'sector_limit_up_count': sector_count,
            'reason': (a_row['个股涨停原因'] or '')[:120],
            'related': related[:top_n],
            'observation': observation,
            'total_qualified': len(related),
            'stats_note': ('联动 = A首板当日或次日B上热门；延续率 = 联动后一交易日B仍热门的概率；'
                           'lift 为相对 B 自身热度延续基准的提升倍数；延续日涨幅仅统计延续样本，偏高仅供参考'),
        }

    @staticmethod
    def _today_status(b_today) -> str:
        """B 当日热门记录 → 操作提示文案"""
        if b_today is None:
            return '无当日热门记录'
        pct = b_today['涨跌幅']  # 小数比例
        if b_today['是否涨停']:
            return f'已联动涨停（当日涨幅 {pct * 100:+.1f}%），次日关注溢价'
        if pct is not None and pct >= 0.05:
            return f'当日已涨 {pct * 100:+.1f}%，T+0 跟风已兑现'
        if pct is not None:
            return f'当日 {pct * 100:+.1f}%，T+1 候选：观察次日竞价是否高开 > 2%'
        return '无当日热门记录'

    # ================= attribute =================

    def attribute(self, code: str, date: Optional[str] = None) -> Dict:
        """
        输入涨停股 A，输出涨停归因链。

        优先级：历史强关联龙头带动 > 当日板块带动 > 独立行情（含强度评分）
        """
        code = code.strip()
        latest = date or self.repo.get_latest_limit_up_date_of(code)
        if not latest:
            return {'code': code, 'error': f'{code} 在 stock_limit_up 中无涨停记录'}

        day_rows = {r['股票代码']: r for r in self.repo.get_limit_up_by_date(latest)}
        a_row = day_rows.get(code)
        if not a_row:
            return {'code': code, 'error': f'{code} 在 {latest} 无涨停记录'}

        a_time = _parse_limit_time(a_row['首次涨停时间'])
        sector = (a_row['关联板块名称'] or '').strip()
        result = {
            'code': code, 'name': a_row['股票中文名称'], 'date': latest,
            'first_limit_time': a_row['首次涨停时间'],
            'sector': sector, 'boards': a_row['连续涨停天数'],
        }

        # ---- 优先级1：历史强关联龙头带动 ----
        reverse_stats = self.repo.query_pair_stats_by_follower(code, MIN_SAMPLES, MIN_LIFT)
        best = None
        for s in reverse_stats:
            leader_code = s['龙头A']
            l_row = day_rows.get(leader_code)
            if not l_row:
                continue
            l_time = _parse_limit_time(l_row['首次涨停时间'])
            # 龙头必须涨停时间早于 A，且方向成立（A 是跟风方）
            if l_time is not None and a_time is not None and l_time >= a_time:
                continue
            if best is None or (s['lift'] or 0) > (best['lift'] or 0):
                best = s
        if best:
            leader_row = day_rows[best['龙头A']]
            t1_rate = (best['B延续热门次数'] / best['样本数']) if best['样本数'] else None
            desc = (f"受 {leader_row['股票中文名称'] or best['龙头A']}（{leader_row['首次涨停时间'][11:16] if leader_row['首次涨停时间'] else '?'} "
                    f"封板，{leader_row['连续涨停天数'] or 1} 连板）带动；"
                    f"历史联动 {best['样本数']} 次，A 被带动后次日热度延续率 "
                    f"{t1_rate * 100:.0f}%，lift {best['lift']:.2f}")
            confidence = self._confidence(best['lift'], best['样本数'], sector, day_rows)
            self.repo.save_attribution(latest, code, '龙头带动', best['龙头A'], desc,
                                       confidence, self._evidence_json(best, sector, day_rows))
            result.update({'type': '龙头带动', 'target': best['龙头A'],
                           'target_name': leader_row['股票中文名称'],
                           'description': desc, 'confidence': round(confidence, 2)})
            return result

        # ---- 优先级2：当日板块带动 ----
        # 触发条件：存在更早封板的同板块涨停股，且（板块多家涨停 形成板块效应，
        # 或 该股为 >=2 连板的龙头——单一高位连板龙头同样构成有效带动）
        sector_rows = [r for r in day_rows.values()
                       if r['股票代码'] != code and (r['关联板块名称'] or '').strip() == sector]
        if sector and sector_rows:
            earlier = [r for r in sector_rows
                       if (_parse_limit_time(r['首次涨停时间']) or 10 ** 6) < (a_time or 10 ** 6)]
            trigger = min(earlier, key=lambda r: _parse_limit_time(r['首次涨停时间']) or 10 ** 6) if earlier else None
            has_leader = trigger is not None and (trigger['连续涨停天数'] or 1) >= 2
            if trigger is not None and (len(sector_rows) >= 2 or has_leader):
                sector_reason = trigger['板块上涨原因'] or a_row['板块上涨原因'] or ''
                desc = (f"受同板块 {trigger['股票中文名称'] or trigger['股票代码']}（{trigger['首次涨停时间'][11:16]} "
                        f"封板，{trigger['连续涨停天数'] or 1} 连板）带动；板块[{sector}]当日共 "
                        f"{len(sector_rows) + 1} 家涨停")
                if sector_reason:
                    desc += f"；板块上涨原因：{sector_reason[:80]}"
                confidence = self._confidence(1.5, len(sector_rows), sector, day_rows)
                self.repo.save_attribution(latest, code, '板块带动', trigger['股票代码'], desc,
                                           confidence, self._evidence_json(None, sector, day_rows))
                result.update({'type': '板块带动', 'target': trigger['股票代码'],
                               'target_name': trigger['股票中文名称'],
                               'description': desc, 'confidence': round(confidence, 2)})
                return result

        # ---- 优先级3：独立行情 + 强度评分 ----
        score, score_desc = self._strength_score(a_row)
        desc = f"独立行情（无历史强关联龙头、板块联动弱）：强度评分 {score}/10；{score_desc}"
        self.repo.save_attribution(latest, code, '独立行情', '', desc, score / 10.0,
                                    self._evidence_json(None, sector, day_rows))
        result.update({'type': '独立行情', 'target': '', 'target_name': '',
                       'description': desc, 'confidence': round(score / 10.0, 2),
                       'strength_score': score})
        return result

    # ---------- 评分辅助 ----------

    def _confidence(self, lift: Optional[float], samples: int, sector: str,
                    day_rows: Dict) -> float:
        """置信度 = 0.4*lift归一化 + 0.3*样本量对数归一化 + 0.2*板块协同度 + 0.1*基准"""
        import math
        lift_score = min((lift or 1.0) / 3.0, 1.0)
        sample_score = min(math.log1p(max(samples, 0)) / math.log1p(50), 1.0)
        if sector:
            same = sum(1 for r in day_rows.values()
                       if (r['关联板块名称'] or '').strip() == sector)
            sector_score = min(same / 6.0, 1.0)
        else:
            sector_score = 0.0
        return max(0.0, min(1.0, 0.4 * lift_score + 0.3 * sample_score + 0.2 * sector_score + 0.1))

    @staticmethod
    def _evidence_json(pair_stat, sector: str, day_rows: Dict) -> str:
        import json
        evidence = {'sector': sector}
        if sector:
            evidence['sector_limit_up_count'] = sum(
                1 for r in day_rows.values() if (r['关联板块名称'] or '').strip() == sector)
        if pair_stat is not None:
            evidence.update({
                'samples': pair_stat['样本数'],
                'lift': pair_stat['lift'],
                't1_hot_count': pair_stat['B延续热门次数'],
                't1_sample_count': pair_stat['样本数'],
                'last_link_date': pair_stat['最近联动日期'],
            })
        return json.dumps(evidence, ensure_ascii=False)

    @staticmethod
    def _strength_score(row) -> Tuple[int, str]:
        """涨停强度评分（0-10）：首板时间分档 + 换手率 + 买入锁仓"""
        score, notes = 0, []
        t = _parse_limit_time(row['首次涨停时间'])
        if t is not None:
            if t <= 10 * 60:
                score += 4
                notes.append('早盘封板(10:00前)')
            elif t <= 11 * 60 + 30:
                score += 3
                notes.append('午前封板')
            elif t <= 13 * 60 + 30:
                score += 2
                notes.append('午后封板')
            else:
                score += 1
                notes.append('尾盘封板(强度偏弱)')
        turnover = row['换手率']
        if turnover is not None:
            if turnover < 5:
                score += 3
                notes.append(f'低换手({turnover:.1f}%，惜售)')
            elif turnover < 15:
                score += 2
                notes.append(f'换手适中({turnover:.1f}%)')
            else:
                score += 1
                notes.append(f'高换手({turnover:.1f}%，分歧大)')
        lock = row['买入锁仓比例']
        if lock is not None and lock > 0:
            score += min(int(lock / 10), 3)
            notes.append(f'买入锁仓{lock:.0f}%')
        opens = row['打开涨停次数'] or 0
        if opens == 0:
            score += 1
            notes.append('未开板')
        else:
            notes.append(f'炸板{opens}次')
        return min(score, 10), '；'.join(notes)
