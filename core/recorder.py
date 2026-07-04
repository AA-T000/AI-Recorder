"""数据采集器 — 后台运行，每 N 秒采样一次当前活动窗口。"""

import time
import logging
from datetime import datetime
from typing import Optional

import psutil
import pygetwindow as gw

from config.settings import load_settings
from storage.database import init_db, insert_record, close_open_records

logger = logging.getLogger(__name__)


def _classify_app(app_name: str, window_title: str, categories: dict) -> str:
    """根据关键词将应用归类。"""
    name_lower = app_name.lower()
    title_lower = window_title.lower()
    combined = name_lower + " " + title_lower

    for category, keywords in categories.items():
        if category == "other":
            continue
        for kw in keywords:
            if kw in combined:
                return category
    return "other"


def _get_active_window_info() -> Optional[tuple]:
    """获取当前活动窗口的信息。

    Returns:
        (app_name, window_title) 或 None（获取失败时）。
    """
    try:
        windows = gw.getActiveWindow()
        if not windows:
            return None
        title = windows.title or ""
        # 尝试从进程名获取应用名
        try:
            pid = windows._hWnd
            proc = psutil.Process(pid)
            app_name = proc.name().lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
            app_name = "unknown"

        if not app_name or app_name == "unknown":
            return None

        return (app_name, title)
    except Exception as e:
        logger.debug(f"获取窗口信息失败: {e}")
        return None


class WindowRecorder:
    """窗口活动记录器。后台持续运行，将采样数据写入数据库。"""

    def __init__(self):
        self._settings = load_settings()
        self._running = False
        self._last_app: Optional[str] = None
        self._last_title: Optional[str] = None
        self._last_start: Optional[datetime] = None
        init_db()
        logger.info("数据采集器已初始化")

    def _save_snapshot(self, app_name: str, title: str):
        """保存一个采样快照。"""
        categories = self._settings.get("categories", {})
        category = _classify_app(app_name, title, categories)
        now = datetime.now()

        # 如果窗口没变，只延长上一段的结束时间
        if (self._last_app == app_name and self._last_title == title
                and self._last_start is not None):
            # 更新上一条记录的结束时间
            from storage.database import _get_conn
            conn = _get_conn()
            try:
                conn.execute(
                    """UPDATE records SET end_time = ?, duration_seconds =
                       julianday(?) - julianday(start_time) * 86400
                       WHERE id = (
                           SELECT id FROM records
                           WHERE end_time IS NULL
                           ORDER BY start_time DESC LIMIT 1
                       )""",
                    (now.isoformat(), now.isoformat()),
                )
                conn.commit()
            finally:
                conn.close()
            return

        # 关闭上一段记录
        if self._last_start is not None:
            duration = int((now - self._last_start).total_seconds())
            if duration > 0:
                insert_record(
                    app_name=self._last_app or "unknown",
                    window_title=self._last_title or "",
                    category=_classify_app(
                        self._last_app or "unknown",
                        self._last_title or "",
                        categories,
                    ),
                    start_time=self._last_start,
                    end_time=now,
                    duration_seconds=duration,
                )

        # 开始新记录
        self._last_app = app_name
        self._last_title = title
        self._last_start = now

    def start(self):
        """开始后台采集。"""
        self._running = True
        interval = self._settings.get("recorder", {}).get("sample_interval", 5)
        logger.info(f"数据采集器启动，采样间隔: {interval}秒")

        try:
            while self._running:
                info = _get_active_window_info()
                if info:
                    app_name, title = info
                    self._save_snapshot(app_name, title)
                else:
                    logger.debug("未能获取活动窗口信息")

                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在关闭...")
        finally:
            self.stop()

    def stop(self):
        """停止采集，关闭所有未完成的记录。"""
        self._running = False
        now = datetime.now()
        if self._last_start is not None:
            duration = int((now - self._last_start).total_seconds())
            if duration > 0:
                insert_record(
                    app_name=self._last_app or "unknown",
                    window_title=self._last_title or "",
                    category=_classify_app(
                        self._last_app or "unknown",
                        self._last_title or "",
                        self._settings.get("categories", {}),
                    ),
                    start_time=self._last_start,
                    end_time=now,
                    duration_seconds=duration,
                )
        close_open_records(now)
        logger.info("数据采集器已停止")

    def is_running(self) -> bool:
        return self._running
