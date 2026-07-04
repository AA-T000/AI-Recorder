"""SQLite 数据库封装 — 所有数据持久化操作。"""

import sqlite3
import os
from datetime import datetime, date
from typing import Optional

from config.settings import DB_PATH


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接。"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """初始化数据库表。"""
    conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_name TEXT NOT NULL,
                window_title TEXT NOT NULL,
                category TEXT DEFAULT 'other',
                start_time TEXT NOT NULL,
                end_time TEXT,
                duration_seconds INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_records_st ON records(start_time);
            CREATE INDEX IF NOT EXISTS idx_records_category ON records(category);
        """)
        conn.commit()
    finally:
        conn.close()


def insert_record(app_name: str, window_title: str, category: str,
                  start_time: datetime, end_time: Optional[datetime] = None,
                  duration_seconds: int = 0):
    """插入一条记录。"""
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO records (app_name, window_title, category, start_time, end_time, duration_seconds)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (app_name, window_title, category,
             start_time.isoformat(),
             end_time.isoformat() if end_time else None,
             duration_seconds),
        )
        conn.commit()
    finally:
        conn.close()


def close_open_records(before: datetime):
    """将指定时间之前未关闭的记录标记为结束。"""
    conn = _get_conn()
    try:
        conn.execute(
            """UPDATE records SET end_time = ?, duration_seconds = julianday(?) - julianday(start_time) * 86400
               WHERE end_time IS NULL AND start_time < ?""",
            (before.isoformat(), before.isoformat(), before.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def get_records_by_date(target_date: date):
    """获取某一天的所有记录，按时间排序。"""
    conn = _get_conn()
    try:
        cursor = conn.execute(
            """SELECT id, app_name, window_title, category, start_time, end_time, duration_seconds
               FROM records
               WHERE date(start_time) = date(?)
               ORDER BY start_time ASC""",
            (target_date.isoformat(),),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_records_range(start_date: date, end_date: date):
    """获取日期范围内的所有记录。"""
    conn = _get_conn()
    try:
        cursor = conn.execute(
            """SELECT id, app_name, window_title, category, start_time, end_time, duration_seconds
               FROM records
               WHERE date(start_time) BETWEEN date(?) AND date(?)
               ORDER BY start_time ASC""",
            (start_date.isoformat(), end_date.isoformat()),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_daily_summary(target_date: date):
    """获取某一天的汇总统计。"""
    conn = _get_conn()
    try:
        cursor = conn.execute(
            """SELECT category,
                      COUNT(*) as record_count,
                      SUM(duration_seconds) as total_seconds
               FROM records
               WHERE date(start_time) = date(?)
               GROUP BY category
               ORDER BY total_seconds DESC""",
            (target_date.isoformat(),),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_recent_days(days: int = 7):
    """获取最近 N 天的每日汇总。"""
    conn = _get_conn()
    try:
        cursor = conn.execute(
            """SELECT date(start_time) as d, category,
                      SUM(duration_seconds) as total_seconds
               FROM records
               WHERE date(start_time) >= date('now', '-' || ? || ' days')
               GROUP BY d, category
               ORDER BY d DESC, total_seconds DESC""",
            (days,),
        )
        rows = cursor.fetchall()
        result = {}
        for row in rows:
            day = row["d"]
            if day not in result:
                result[day] = []
            result[day].append({"category": row["category"], "total_seconds": row["total_seconds"]})
        return result
    finally:
        conn.close()


def clear_all_data():
    """清除所有数据。"""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM records")
        conn.commit()
    finally:
        conn.close()


def get_total_records():
    """获取记录总数。"""
    conn = _get_conn()
    try:
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM records")
        row = cursor.fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()
