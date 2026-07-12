"""数据采集器 — 后台运行，每 N 秒采样一次当前活动窗口。

设计原则（参考 ActivityWatch 等开源项目）：
- 原始数据只存窗口切换事件（原子记录）
- 粗粒度分析在查询时完成（合并同一应用的连续时间段）
- 不记录屏幕内容、不截屏、不录屏
- 只记录应用名和窗口标题，纯文本
"""

import ctypes
import logging
import time
from datetime import datetime
from typing import Optional

import psutil
import pygetwindow as gw

from config.settings import load_settings
from storage.database import init_db, insert_record, close_open_records

logger = logging.getLogger(__name__)


def _get_pid_from_hwnd(hwnd):
    """从窗口句柄获取进程 ID（Windows API）。"""
    try:
        user32 = ctypes.windll.user32
        pid = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value
    except Exception:
        return None


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

        # 从窗口句柄获取 PID，再用 PID 获取进程名
        hwnd = windows._hWnd
        pid = _get_pid_from_hwnd(hwnd)
        if pid:
            try:
                proc = psutil.Process(pid)
                app_name = proc.name().lower()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                app_name = _infer_app_from_title(title)
        else:
            app_name = _infer_app_from_title(title)

        if not app_name:
            return None

        return (app_name, title)

    except Exception as e:
        logger.debug(f"获取窗口信息失败: {e}")
        return None


def _infer_app_from_title(title: str) -> str:
    """从窗口标题推断应用名（备用方案）。"""
    title_lower = title.lower()
    if "edge" in title_lower or "microsoft" in title_lower:
        return "msedge.exe"
    if "chrome" in title_lower:
        return "chrome.exe"
    if "visual studio" in title_lower or "vscode" in title_lower:
        return "code.exe"
    if "pycharm" in title_lower:
        return "pycharm64.exe"
    if "wechat" in title_lower or "微信" in title_lower:
        return "wechat.exe"
    if "cmd" in title_lower or "powershell" in title_lower:
        return "cmd.exe"
    return "unknown"


class WindowRecorder:
    """窗口活动记录器。

    核心逻辑：
    - 每 N 秒采样一次当前活动窗口
    - 同一应用+同一窗口连续使用时，不断延长上一段
    - 切换到不同应用时，关闭上一段并开启新段
    - 所有原始记录存入 SQLite
    """

    def __init__(self):
        self._settings = load_settings()
        self._running = False
        self._last_app: Optional[str] = None
        self._last_title: Optional[str] = None
        self._last_start: Optional[datetime] = None
        self._last_category: Optional[str] = None
        # 前置宽限期：新应用出现在前台后，需持续停留 grace_period 秒才创建记录
        self._grace_start: Optional[datetime] = None
        self._grace_period = self._settings.get("idle_detection", {}).get("foreground_grace_period", 15)
        init_db()
        logger.info("数据采集器已初始化")

    def _save_snapshot(self, app_name: str, title: str):
        """保存一个采样快照。

        逻辑：
        1. 如果窗口没变 → 延长上一段的结束时间
        2. 如果应用变了 → 先经过前置宽限期（grace period），通过后关闭旧段、开启新段
        3. 同一应用但不同窗口 → 也延长（比如 VS Code 切换了不同文件）
        """
        categories = self._settings.get("categories", {})
        category = _classify_app(app_name, title, categories)
        now = datetime.now()

        # --- 前置宽限期：仅在新应用切换时生效 ---
        app_changed = (self._last_app is None or self._last_app != app_name)
        if app_changed:
            if self._grace_start is not None:
                elapsed = (now - self._grace_start).total_seconds()
                if elapsed < self._grace_period:
                    # 新应用停留时间不足，跳过本次采样
                    self._grace_start = now
                    return
            self._grace_start = now  # 重置宽限期计时器

        # 完全相同的窗口（应用+标题都没变）→ 延长上一段
        if (self._last_app == app_name and self._last_title == title
                and self._last_start is not None):
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

        # 同一应用但不同窗口 → 也延长（比如 VS Code 切换了不同文件）
        if (self._last_app == app_name and self._last_category == category
                and self._last_start is not None):
            from storage.database import _get_conn
            conn = _get_conn()
            try:
                conn.execute(
                    """UPDATE records SET end_time = ?, duration_seconds =
                       julianday(?) - julianday(start_time) * 86400,
                       window_title = ?
                       WHERE id = (
                           SELECT id FROM records
                           WHERE end_time IS NULL
                           ORDER BY start_time DESC LIMIT 1
                       )""",
                    (now.isoformat(), now.isoformat(), title),
                )
                conn.commit()
            finally:
                conn.close()
            return

        # 不同应用 → 关闭旧段，开启新段
        if self._last_start is not None:
            duration = int((now - self._last_start).total_seconds())
            if duration > 0:
                insert_record(
                    app_name=self._last_app or "unknown",
                    window_title=self._last_title or "",
                    category=self._last_category or "other",
                    start_time=self._last_start,
                    end_time=now,
                    duration_seconds=duration,
                )

        self._last_app = app_name
        self._last_title = title
        self._last_category = category
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
                    category=self._last_category or "other",
                    start_time=self._last_start,
                    end_time=now,
                    duration_seconds=duration,
                )
        close_open_records(now)
        logger.info("数据采集器已停止")

    def is_running(self) -> bool:
        return self._running
