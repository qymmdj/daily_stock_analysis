# -*- coding: utf-8 -*-
"""临时脚本：检查表是否存在 + 重试写入探测"""
import sqlite3

DB = r"D:\source\qym\electron-stock\stockDb.db3"
con = sqlite3.connect(DB)
cur = con.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE name IN ('stock_pair_stats', 'stock_rise_attribution')")
print("已存在的产出表:", [r[0] for r in cur.fetchall()])

# 写入探测
try:
    cur.execute("CREATE TABLE IF NOT EXISTS _write_test (id INTEGER)")
    cur.execute("INSERT INTO _write_test VALUES (1)")
    con.commit()
    print("写入: OK")
    cur.execute("DROP TABLE _write_test")
    con.commit()
    print("清理: OK")
except Exception as e:
    print("写入失败:", type(e).__name__, e)
finally:
    con.close()
