# -*- coding: utf-8 -*-
"""涨停关联分析（CorrelationService）单元测试：基于临时 SQLite 库

口径：次日延续事件 = B 次日仍出现在 hot_subject；
lift = P(B次日仍热门|A首板且B当日热门) / P(B次日仍热门|B当日热门)
"""

import os
import sqlite3
import tempfile

import pytest

from src.services.correlation_service import CorrelationService

# 服务实际访问的源表列（SELECT * 后按列名取值，缺列会 KeyError）
_LIMIT_UP_COLS = (
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "股票代码 TEXT, 股票中文名称 TEXT, 是否新股 INTEGER, 连续涨停天数 INTEGER, "
    "首次涨停时间 TEXT, 关联板块名称 TEXT, 个股涨停原因 TEXT, 板块上涨原因 TEXT, "
    "换手率 REAL, 买入锁仓比例 REAL, 打开涨停次数 INTEGER"
)
_HOT_SUBJECT_COLS = (
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "日期 TEXT NOT NULL, 股票代码 TEXT NOT NULL, 股票中文名称 TEXT, 涨跌幅 REAL, "
    "是否涨停 INTEGER, 简介 TEXT, 研报标题 TEXT, 板块名称 TEXT"
)


def _make_db(path: str) -> None:
    con = sqlite3.connect(path)
    con.execute(f"CREATE TABLE stock_limit_up ({_LIMIT_UP_COLS})")
    con.execute(f"CREATE TABLE stock_hot_subject ({_HOT_SUBJECT_COLS})")
    con.commit()
    con.close()


@pytest.fixture
def service():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db3")
        _make_db(db)
        yield CorrelationService(db)


def _add_limit_up(con, day, code, name, first_time, sector, boards=1,
                  reason="机器人 减速器", new_stock=0):
    con.execute(
        "INSERT INTO stock_limit_up (股票代码, 股票中文名称, 是否新股, 连续涨停天数, "
        "首次涨停时间, 关联板块名称, 个股涨停原因, 换手率, 买入锁仓比例, 打开涨停次数) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (code, name, new_stock, boards, f"{day} {first_time}", sector, reason, 4.0, 20.0, 0),
    )


def _add_hot(con, day, code, name, pct, limit_up=0, sector="机器人", intro=""):
    con.execute(
        "INSERT INTO stock_hot_subject (日期, 股票代码, 股票中文名称, 涨跌幅, 是否涨停, "
        "简介, 研报标题, 板块名称) VALUES (?,?,?,?,?,?,?,?)",
        (day, code, name, pct, limit_up, intro, "", sector),
    )


# 源表涨跌幅为小数比例（0.05 = 5%）
PCT_A = 0.10
PCT_B1_T0 = 0.05
PCT_B1_T1 = 0.06


def _jan(day: int) -> str:
    return f"2026-01-{day:02d}"


# 龙头 A 的首板日（间隔 3 天，共 10 天，使 B 的次日延续不会被自然连热干扰）
A_DAYS = [2, 5, 8, 11, 14, 17, 20, 23, 26, 29]
# 跟风 B1 热门日 = A 日 + A 日次日（孤岛式，控制自身延续基准为 0.5）
B1_DAYS = sorted(set(A_DAYS) | {d + 1 for d in A_DAYS})


def _seed_linkage_data(con):
    """A(机器人板块) 每隔3日首板；B1 热门日覆盖 A 日及其次日（当日跟风+延续）；
    B3 仅在 A 日次日与第三日热门（次日跟风+延续）；D 每天热门（补全日期序列）"""
    for d in A_DAYS:
        _add_limit_up(con, _jan(d), "600001.SS", "龙头A", "09:35:00", "机器人")
        _add_hot(con, _jan(d), "600001.SS", "龙头A", PCT_A, limit_up=1)
    for d in B1_DAYS:
        _add_hot(con, _jan(d), "300001.SZ", "跟风B1",
                 PCT_B1_T0 if d in A_DAYS else PCT_B1_T1)
    # B3：次日跟风模式（A 首板日不在热门，次日与第三日热门）
    for d in A_DAYS:
        _add_hot(con, _jan(d + 1), "300003.SZ", "跟风B3", 0.04, limit_up=1)
        _add_hot(con, _jan(d + 2), "300003.SZ", "跟风B3", 0.07)
    for d in range(1, 32):
        _add_hot(con, _jan(d), "600100.SS", "每日热门D", 0.01, sector="其他")


class TestBuildStats:
    def test_sector_channel_pair(self, service):
        """B1 当日跟风且延续 → 高 lift；B3 次日跟风模式也被统计且延续成功"""
        con = sqlite3.connect(service.repo.db_path)
        _seed_linkage_data(con)
        con.commit()
        con.close()

        stats = service.build_stats()
        assert stats["days"] == 31
        assert stats["pairs"] > 0

        pairs = service.repo.query_pair_stats_by_leader("600001.SS")
        by_b = {p["跟风B"]: p for p in pairs}
        # B1：板块通道，10 次当日联动全部延续，自身延续基准 0.5 → lift=2.0
        assert "300001.SZ" in by_b
        b1 = by_b["300001.SZ"]
        assert b1["关联通道"] == "sector"
        assert b1["样本数"] == 10
        assert b1["B次日跟风次数"] == 0  # 全部是当日跟风
        assert b1["B延续热门次数"] == 10
        assert b1["B无条件延续率"] == pytest.approx(0.5)
        assert b1["lift"] == pytest.approx(2.0)
        # B3：次日跟风模式（A 首板日不在热门，次日才热门），第三日全部延续
        assert "300003.SZ" in by_b
        b3 = by_b["300003.SZ"]
        assert b3["样本数"] == 10
        assert b3["B次日跟风次数"] == 10  # 全部是次日跟风
        assert b3["B延续热门次数"] == 10
        # B3 自身延续基准 10/19（末日无次日可比），联动延续率 1.0 → lift≈1.9
        assert b3["lift"] == pytest.approx(1.9)
        # D：板块不同且无题材重合，不应出现在 A 的关联中
        assert "600100.SS" not in by_b

    def test_next_day_follow_counts(self, service):
        """次日跟风是有效联动事件：即使 B 延续失败也计入样本"""
        con = sqlite3.connect(service.repo.db_path)
        # A 首板 10 天，B 仅在 A 次日热门（第三日不延续）→ 样本应计 10 次
        for d in A_DAYS:
            _add_limit_up(con, _jan(d), "600001.SS", "龙头A", "09:35:00", "机器人")
            _add_hot(con, _jan(d), "600001.SS", "龙头A", PCT_A, limit_up=1)
            _add_hot(con, _jan(d + 1), "300005.SZ", "次日跟风B", 0.04, limit_up=1)
        con.commit()
        con.close()
        service.build_stats()

        # 不过门槛（延续 0），但原始对已统计
        conn = service.repo._connect_stats()
        row = conn.execute(
            "SELECT 样本数, B次日跟风次数, B延续热门次数 FROM stock_pair_stats "
            "WHERE 龙头A='600001.SS' AND 跟风B='300005.SZ'"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["样本数"] == 10
        assert row["B次日跟风次数"] == 10
        assert row["B延续热门次数"] == 0

    def test_new_stock_and_multi_board_excluded(self, service):
        """新股与二连板以上股票不进龙头池"""
        con = sqlite3.connect(service.repo.db_path)
        _add_limit_up(con, "2026-02-02", "600002.SS", "新股龙头", "09:40:00",
                      "机器人", new_stock=1)
        _add_limit_up(con, "2026-02-02", "600003.SS", "二板龙头", "09:41:00",
                      "机器人", boards=2)
        _add_hot(con, "2026-02-02", "600002.SS", "新股龙头", 0.20, limit_up=1)
        _add_hot(con, "2026-02-02", "600003.SS", "二板龙头", 0.10, limit_up=1)
        con.commit()
        con.close()

        stats = service.build_stats()
        assert stats["leaders"] == 0

    def test_theme_channel(self, service):
        """涨停原因与简介文本重合度高但不同板块 → theme 通道"""
        con = sqlite3.connect(service.repo.db_path)
        reason = "公司机器人减速器产品打入头部客户供应链"
        intro = "公司机器人减速器产品出货量全球领先"
        for d in A_DAYS:
            _add_limit_up(con, _jan(d), "600004.SS", "题材龙头", "09:36:00",
                          "机器人", reason=reason)
            _add_hot(con, _jan(d), "600004.SS", "题材龙头", PCT_A, limit_up=1)
        for d in B1_DAYS:
            _add_hot(con, _jan(d), "300004.SZ", "题材跟风",
                     PCT_B1_T0 if d in A_DAYS else PCT_B1_T1,
                     sector="汽车零部件", intro=intro)
        for d in range(1, 32):
            _add_hot(con, _jan(d), "600100.SS", "每日热门D", 0.01, sector="其他")
        con.commit()
        con.close()

        service.build_stats()
        pairs = service.repo.query_pair_stats_by_leader("600004.SS")
        theme_pairs = [p for p in pairs if p["关联通道"] == "theme"]
        assert any(p["跟风B"] == "300004.SZ" for p in theme_pairs)
        b = next(p for p in theme_pairs if p["跟风B"] == "300004.SZ")
        assert b["lift"] == pytest.approx(2.0)


class TestFindRelated:
    def test_related_output(self, service):
        con = sqlite3.connect(service.repo.db_path)
        _seed_linkage_data(con)
        con.commit()
        con.close()
        service.build_stats()

        result = service.find_related("600001.SS")
        assert result["code"] == "600001.SS"
        assert result["date"] == "2026-01-29"  # 最近涨停日
        codes = [r["code"] for r in result["related"]]
        assert "300001.SZ" in codes
        entry = next(r for r in result["related"] if r["code"] == "300001.SZ")
        assert entry["channel"] == "sector"
        assert entry["t1_persist_rate"] == pytest.approx(1.0)
        assert entry["t1_avg_pct"] == pytest.approx(PCT_B1_T1)
        # B1 当日涨 5% → T+0 已兑现提示
        assert "T+0" in entry["today_status"]

    def test_unknown_code(self, service):
        result = service.find_related("999999.SS")
        assert "error" in result


class TestAttribute:
    def test_leader_driven(self, service):
        """B1 当日也被 A 带动涨停（时间晚于 A）→ 归因为龙头带动"""
        con = sqlite3.connect(service.repo.db_path)
        _seed_linkage_data(con)
        # 最后一日 B1 也涨停，时间晚于 A
        _add_limit_up(con, _jan(29), "300001.SZ", "跟风B1", "10:15:00", "机器人")
        con.commit()
        con.close()
        service.build_stats()

        result = service.attribute("300001.SZ", _jan(29))
        assert result["type"] == "龙头带动"
        assert result["target"] == "600001.SS"
        assert result["confidence"] > 0
        assert "延续率" in result["description"]

    def test_independent_fallback(self, service):
        """无历史关联、无板块联动 → 独立行情 + 强度评分"""
        con = sqlite3.connect(service.repo.db_path)
        _add_limit_up(con, "2026-02-02", "600009.SS", "独狼", "09:31:00", "稀缺板块")
        _add_hot(con, "2026-02-02", "600009.SS", "独狼", 0.10, limit_up=1, sector="其他")
        con.commit()
        con.close()
        service.build_stats()

        result = service.attribute("600009.SS", "2026-02-02")
        assert result["type"] == "独立行情"
        assert result["strength_score"] >= 5  # 早盘 + 低换手 + 锁仓 + 未开板

    def test_find_related_observation(self, service):
        """低样本联动（1 次）不足门槛 → 进入 observation 列表而非被吞掉"""
        con = sqlite3.connect(service.repo.db_path)
        # A 仅 1 次首板，B1 次日跟风并延续（低样本高 lift）
        _add_limit_up(con, "2026-02-02", "600030.SS", "一次性龙头", "09:35:00", "机器人")
        _add_hot(con, "2026-02-02", "600030.SS", "一次性龙头", PCT_A, limit_up=1)
        _add_hot(con, "2026-02-03", "300030.SZ", "低样本跟风", 0.04, limit_up=1)
        _add_hot(con, "2026-02-04", "300030.SZ", "低样本跟风", 0.07)
        con.commit()
        con.close()
        service.build_stats()

        result = service.find_related("600030.SS", "2026-02-02")
        assert result["related"] == []          # 样本 1 < 8，不进正式列表
        obs = result["observation"]
        assert len(obs) >= 1
        b = next(o for o in obs if o["code"] == "300030.SZ")
        assert b["samples"] == 1
        assert b["next_follow_count"] == 1
        assert b["t0_limit_count"] == 1

    def test_sector_driven(self, service):
        """无历史 pair 但同板块多家更早涨停 → 板块带动"""
        con = sqlite3.connect(service.repo.db_path)
        _add_limit_up(con, "2026-02-02", "600010.SS", "早板", "09:32:00", "机器人")
        _add_limit_up(con, "2026-02-02", "600011.SS", "早板2", "09:40:00", "机器人")
        _add_limit_up(con, "2026-02-02", "300010.SZ", "晚板", "10:30:00", "机器人")
        _add_hot(con, "2026-02-02", "600010.SS", "早板", 0.10, limit_up=1)
        _add_hot(con, "2026-02-02", "600011.SS", "早板2", 0.10, limit_up=1)
        _add_hot(con, "2026-02-02", "300010.SZ", "晚板", 0.10, limit_up=1)
        con.commit()
        con.close()
        service.build_stats()

        result = service.attribute("300010.SZ", "2026-02-02")
        assert result["type"] == "板块带动"
        assert result["target"] == "600010.SS"  # 最早封板者

    def test_single_connected_board_leader_driven(self, service):
        """同板块仅 1 家更早涨停且为 >=2 连板龙头 → 仍判板块带动（单一龙头有效）"""
        con = sqlite3.connect(service.repo.db_path)
        _add_limit_up(con, "2026-02-02", "600020.SS", "连板龙头", "09:30:00",
                      "折叠屏", boards=3)
        _add_limit_up(con, "2026-02-02", "300020.SZ", "晚板跟风", "13:06:00", "折叠屏")
        _add_hot(con, "2026-02-02", "600020.SS", "连板龙头", 0.10, limit_up=1)
        _add_hot(con, "2026-02-02", "300020.SZ", "晚板跟风", 0.10, limit_up=1)
        con.commit()
        con.close()
        service.build_stats()

        result = service.attribute("300020.SZ", "2026-02-02")
        assert result["type"] == "板块带动"
        assert result["target"] == "600020.SS"
        assert "3 连板" in result["description"]

    def test_single_first_board_not_driven(self, service):
        """同板块仅 1 家更早涨停且为首板（非连板龙头）→ 不足以判定带动，独立行情"""
        con = sqlite3.connect(service.repo.db_path)
        _add_limit_up(con, "2026-02-02", "600021.SS", "首板早", "09:30:00", "机器人", boards=1)
        _add_limit_up(con, "2026-02-02", "300021.SZ", "首板晚", "13:06:00", "机器人", boards=1)
        _add_hot(con, "2026-02-02", "600021.SS", "首板早", 0.10, limit_up=1)
        _add_hot(con, "2026-02-02", "300021.SZ", "首板晚", 0.10, limit_up=1)
        con.commit()
        con.close()
        service.build_stats()

        result = service.attribute("300021.SZ", "2026-02-02")
        assert result["type"] == "独立行情"


class TestTextOverlap:
    def test_overlap_values(self):
        from src.services.correlation_service import text_overlap
        assert text_overlap("机器人减速器", "机器人减速器") == 1.0
        assert text_overlap("机器人减速器", "光伏组件") < 0.2
        assert text_overlap(None, "abc") == 0.0
