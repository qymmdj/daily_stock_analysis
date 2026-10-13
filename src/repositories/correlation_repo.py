# -*- coding: utf-8 -*-
"""
===================================
涨停关联分析 - 数据访问层
===================================

职责：
1. 直连外部涨停数据库（stockDb.db3，含 stock_limit_up / stock_hot_subject 两张源表）
2. 管理 stock_pair_stats / stock_rise_attribution 两张产出表（与源表同库）
3. 不依赖应用主库（DatabaseManager），独立管理 sqlite3 连接

口径说明：
- stock_limit_up 的日期取自 SUBSTR(首次涨停时间, 1, 10)，已验证覆盖率 100%
- stock_hot_subject 自带 日期 字段
"""

import logging
import sqlite3
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 产出表 DDL：与两张源表同库，方便 JOIN
# 口径说明：
#   联动事件 = A 首板窗口内（当日或次日）B 首次上热门：
#     - 当日跟风：A 首板日 B 已热门
#     - 次日跟风：A 首板日 B 不在热门、次日才上热门
#   B延续热门次数 = 联动事件后一交易日 B 仍热门的天数（热度延续事件）
#   B无条件延续率 = B 自身的 P(下一交易日仍热门 | 当日热门) 基准
#   lift = (B延续热门次数/样本数) / B无条件延续率，衡量 A 涨停对 B 热度延续的增量
_PAIR_STATS_DDL = """
CREATE TABLE IF NOT EXISTS stock_pair_stats (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    龙头A          TEXT NOT NULL,
    跟风B          TEXT NOT NULL,
    关联通道       TEXT NOT NULL,
    样本数         INTEGER NOT NULL DEFAULT 0,
    B跟风涨停次数  INTEGER NOT NULL DEFAULT 0,
    B跟风平均涨幅  REAL,
    B次日跟风次数  INTEGER NOT NULL DEFAULT 0,
    B延续热门次数  INTEGER NOT NULL DEFAULT 0,
    B延续平均涨幅  REAL,
    B无条件延续率  REAL,
    B无条件涨停率  REAL,
    lift           REAL,
    首次联动日期   TEXT,
    最近联动日期   TEXT,
    更新时间       INTEGER,
    UNIQUE (龙头A, 跟风B, 关联通道)
)
"""

_ATTRIBUTION_DDL = """
CREATE TABLE IF NOT EXISTS stock_rise_attribution (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    日期        TEXT NOT NULL,
    股票代码    TEXT NOT NULL,
    归因类型    TEXT,
    归因对象    TEXT,
    归因描述    TEXT,
    置信度      REAL,
    证据        TEXT,
    创建时间    INTEGER
)
"""


class CorrelationRepository:
    """涨停关联分析数据访问：源表与产出表同库（stockDb.db3），直接读写

    注意：若外部采集进程同时写库，SQLite 会因锁竞争失败；
    写连接已设置 busy_timeout(5s) 缓解，建议盘后采集完成后再运行构建。
    """

    def __init__(self, db_path: str):
        if not db_path:
            raise ValueError("correlation_db_path 未配置，请在 .env 中设置 CORRELATION_DB_PATH")
        import os
        if not os.path.exists(db_path):
            raise ValueError(f"涨停数据库不存在: {db_path}")
        self.db_path = db_path
        self._ensure_tables()

    # ---------- 基础 ----------

    def _connect(self) -> sqlite3.Connection:
        """源库连接（读写），带锁等待缓解采集进程并发写入"""
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA busy_timeout = 5000')
        return conn

    def _connect_stats(self) -> sqlite3.Connection:
        """产出表连接：与源表同库"""
        return self._connect()

    def _ensure_tables(self) -> None:
        conn = self._connect_stats()
        try:
            # 旧版列结构不兼容时重建（检测新版列名）
            cols = {r[1] for r in conn.execute('PRAGMA table_info(stock_pair_stats)').fetchall()}
            if cols and 'B延续热门次数' not in cols:
                logger.info("检测到旧版 stock_pair_stats 结构，重建表（需重新 --build-correlation）")
                conn.execute('DROP TABLE stock_pair_stats')
            conn.execute(_PAIR_STATS_DDL)
            conn.execute(_ATTRIBUTION_DDL)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pair_leader ON stock_pair_stats(龙头A)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pair_follower ON stock_pair_stats(跟风B)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_attr_date ON stock_rise_attribution(日期, 股票代码)")
            conn.commit()
        finally:
            conn.close()

    # ---------- 源表读取 ----------

    def get_hot_subject_dates(self) -> List[str]:
        """获取 hot_subject 覆盖的全部日期（升序）"""
        conn = self._connect()
        try:
            rows = conn.execute(
                'SELECT DISTINCT 日期 FROM stock_hot_subject WHERE 日期 IS NOT NULL ORDER BY 日期'
            ).fetchall()
            return [r[0] for r in rows]
        finally:
            conn.close()

    def get_hot_subject_by_date(self, date: str) -> Dict[str, sqlite3.Row]:
        """某日热门股：股票代码 -> 行"""
        conn = self._connect()
        try:
            rows = conn.execute(
                'SELECT * FROM stock_hot_subject WHERE 日期 = ?', (date,)
            ).fetchall()
            return {r['股票代码']: r for r in rows}
        finally:
            conn.close()

    def get_limit_up_by_date(self, date: str) -> List[sqlite3.Row]:
        """某日涨停股（日期取自首次涨停时间前缀）"""
        conn = self._connect()
        try:
            return conn.execute(
                'SELECT * FROM stock_limit_up WHERE SUBSTR(首次涨停时间, 1, 10) = ?',
                (date,),
            ).fetchall()
        finally:
            conn.close()

    def get_latest_limit_up_date(self) -> Optional[str]:
        conn = self._connect()
        try:
            row = conn.execute(
                'SELECT MAX(SUBSTR(首次涨停时间, 1, 10)) FROM stock_limit_up '
                'WHERE 首次涨停时间 IS NOT NULL AND 首次涨停时间 != ""'
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def get_latest_limit_up_date_of(self, code: str) -> Optional[str]:
        """某股票最近一次涨停的日期"""
        conn = self._connect()
        try:
            row = conn.execute(
                'SELECT MAX(SUBSTR(首次涨停时间, 1, 10)) FROM stock_limit_up '
                'WHERE 股票代码 = ? AND 首次涨停时间 IS NOT NULL AND 首次涨停时间 != ""',
                (code,),
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def get_stock_name(self, code: str) -> Optional[str]:
        """优先从 limit_up 查中文名，再从 hot_subject 查"""
        conn = self._connect()
        try:
            row = conn.execute(
                'SELECT 股票中文名称 FROM stock_limit_up WHERE 股票代码 = ? '
                'AND 股票中文名称 IS NOT NULL ORDER BY id DESC LIMIT 1', (code,)
            ).fetchone()
            if not row:
                row = conn.execute(
                    'SELECT 股票中文名称 FROM stock_hot_subject WHERE 股票代码 = ? '
                    'AND 股票中文名称 IS NOT NULL ORDER BY id DESC LIMIT 1', (code,)
                ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def get_follower_baselines(self) -> Dict[str, Tuple[float, int]]:
        """每只股票在 hot_subject 全部样本日的涨停率（涨停率, 样本日数）"""
        conn = self._connect()
        try:
            rows = conn.execute(
                'SELECT 股票代码, '
                'AVG(CASE WHEN 是否涨停 = 1 THEN 1.0 ELSE 0.0 END), COUNT(*) '
                'FROM stock_hot_subject GROUP BY 股票代码'
            ).fetchall()
            return {r[0]: (r[1], r[2]) for r in rows}
        finally:
            conn.close()

    # ---------- pair_stats 写入与查询 ----------

    def replace_pair_stats(self, rows: List[Tuple]) -> int:
        """全量覆盖写入 pair_stats，返回写入行数"""
        conn = self._connect_stats()
        try:
            conn.execute('DELETE FROM stock_pair_stats')
            conn.executemany(
                'INSERT OR REPLACE INTO stock_pair_stats ('
                '龙头A, 跟风B, 关联通道, 样本数, B跟风涨停次数, B跟风平均涨幅, '
                'B次日跟风次数, B延续热门次数, B延续平均涨幅, '
                'B无条件延续率, B无条件涨停率, lift, '
                '首次联动日期, 最近联动日期, 更新时间) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                rows,
            )
            conn.commit()
            return len(rows)
        finally:
            conn.close()

    def query_pair_stats_by_leader(self, code: str, min_samples: int = 8,
                                   min_lift: float = 1.4) -> List[sqlite3.Row]:
        conn = self._connect_stats()
        try:
            return conn.execute(
                'SELECT * FROM stock_pair_stats WHERE 龙头A = ? AND 样本数 >= ? '
                'AND lift IS NOT NULL AND lift >= ? ORDER BY lift DESC',
                (code, min_samples, min_lift),
            ).fetchall()
        finally:
            conn.close()

    def query_all_pair_stats_by_leader(self, code: str) -> List[sqlite3.Row]:
        """某龙头的全部关联对（不设门槛），按样本数（历史重复性）优先排序，用于低样本观察展示"""
        conn = self._connect_stats()
        try:
            return conn.execute(
                'SELECT * FROM stock_pair_stats WHERE 龙头A = ? '
                'ORDER BY 样本数 DESC, (lift IS NULL), (lift or 0) DESC',
                (code,),
            ).fetchall()
        finally:
            conn.close()

    def query_pair_stats_by_follower(self, code: str, min_samples: int = 8,
                                     min_lift: float = 1.4) -> List[sqlite3.Row]:
        conn = self._connect_stats()
        try:
            return conn.execute(
                'SELECT * FROM stock_pair_stats WHERE 跟风B = ? AND 样本数 >= ? '
                'AND lift IS NOT NULL AND lift >= ? ORDER BY lift DESC',
                (code, min_samples, min_lift),
            ).fetchall()
        finally:
            conn.close()

    def count_pair_stats(self) -> int:
        conn = self._connect_stats()
        try:
            return conn.execute('SELECT COUNT(*) FROM stock_pair_stats').fetchone()[0]
        finally:
            conn.close()

    # ---------- attribution 写入 ----------

    def save_attribution(self, date: str, code: str, attr_type: str,
                         target: str, description: str, confidence: float,
                         evidence: str) -> None:
        conn = self._connect_stats()
        try:
            conn.execute(
                'INSERT INTO stock_rise_attribution '
                '(日期, 股票代码, 归因类型, 归因对象, 归因描述, 置信度, 证据, 创建时间) '
                'VALUES (?,?,?,?,?,?,?,?)',
                (date, code, attr_type, target, description, confidence, evidence, int(time.time())),
            )
            conn.commit()
        finally:
            conn.close()
