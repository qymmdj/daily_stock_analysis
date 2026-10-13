# -*- coding: utf-8 -*-
"""临时脚本：验证 WAL 假设 + 测试复制到本地后读取"""
import shutil
import sqlite3

SRC = r"D:\source\qym\electron-stock\stockDb.db3"
LOCAL = r"D:\source\qym\daily_stock_analysis\.tmp_src_copy.db"

# 复制到本地可写目录后读取
shutil.copyfile(SRC, LOCAL)
try:
    con = sqlite3.connect(LOCAL)
    print("复制后读取 hot_subject:", con.execute("SELECT COUNT(*) FROM stock_hot_subject").fetchone())
    print("复制后读取 limit_up:", con.execute("SELECT COUNT(*) FROM stock_limit_up").fetchone())
    print("journal_mode:", con.execute("PRAGMA journal_mode").fetchone())
    con.close()
finally:
    import os
    os.remove(LOCAL)
    # 清理可能的 -wal/-shm
    for ext in ("-wal", "-shm"):
        p = LOCAL + ext
        if os.path.exists(p):
            os.remove(p)
