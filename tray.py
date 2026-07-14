"""系统托盘 — 在任务栏显示图标，右键菜单控制。

功能：
- 开始/暂停/恢复 数据采集
- 一键生成日报（今天/昨天/指定日期）
- 一键生成周报（本周/上周）
- 查看实时统计
- 打开最新报告 / 打开报告文件夹
- 退出（自动停止采集）
"""

import logging
import os
import subprocess
import threading
from datetime import date, timedelta

import pystray
from PIL import Image, ImageDraw

from core.recorder import WindowRecorder
from core.notifier import show_toast

logger = logging.getLogger(__name__)


def _create_icon_image():
    """运行中图标（蓝色播放按钮）。"""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=(59, 130, 246, 200), outline=(96, 165, 250, 255))
    draw.polygon([(24, 18), (24, 46), (46, 32)], fill=(255, 255, 255))
    return img


def _create_paused_icon_image():
    """暂停状态图标（灰色暂停按钮）。"""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=(100, 116, 139, 200), outline=(148, 163, 184, 255))
    # 暂停符号（两条竖线）
    draw.rectangle([(22, 20), (28, 44)], fill=(255, 255, 255))
    draw.rectangle([(36, 20), (42, 44)], fill=(255, 255, 255))
    return img


class TrayIcon:
    """系统托盘图标控制器。

    维护采集器状态，提供完整的托盘菜单交互。
    """

    def __init__(self):
        self._recorder = WindowRecorder()
        self._is_running = False
        self._is_paused = False  # 暂停状态（区别于未启动）
        self._icon = None
        self._update_menu()

    # ------------------------------------------------------------------ #
    # 菜单构建
    # ------------------------------------------------------------------ #

    def _update_menu(self):
        """根据运行状态动态构建菜单。"""
        if self._is_running:
            if self._is_paused:
                status_item = pystray.MenuItem("▶ 继续记录", self._resume, checked=lambda _: True)
            else:
                status_item = pystray.MenuItem("⏸ 暂停记录", self._pause, checked=lambda _: True)
        else:
            status_item = pystray.MenuItem("▶ 开始记录", self._start_recording, checked=lambda _: False)

        today_str = date.today().isoformat()
        yesterday_str = (date.today() - timedelta(days=1)).isoformat()

        self._menu = pystray.Menu(
            # --- 采集控制 ---
            status_item,
            pystray.MenuItem("━━━━━━━━━━", lambda _: None, enabled=False),

            # --- 日报生成 ---
            pystray.MenuItem("📅 生成今天日报", lambda item: self._generate_report(item, today_str)),
            pystray.MenuItem("📅 生成昨天日报", lambda item: self._generate_report(item, yesterday_str)),
            pystray.MenuItem("📅 生成指定日期日报", self._show_date_picker),
            pystray.MenuItem("━━━━━━━━━━", lambda _: None, enabled=False),

            # --- 周报生成 ---
            pystray.MenuItem("📊 生成本周周报", lambda item: self._generate_weekly_report(item, True)),
            pystray.MenuItem("📊 生成上周周报", lambda item: self._generate_weekly_report(item, False)),
            pystray.MenuItem("━━━━━━━━━━", lambda _: None, enabled=False),

            # --- 统计与报告 ---
            pystray.MenuItem("📈 查看实时统计", self._show_stats),
            pystray.MenuItem("📂 打开最新报告", self._open_latest_report),
            pystray.MenuItem("📁 打开报告文件夹", self._open_reports),
            pystray.MenuItem("━━━━━━━━━━", lambda _: None, enabled=False),

            # --- 退出 ---
            pystray.MenuItem("✖ 退出", self._quit),
        )

    # ------------------------------------------------------------------ #
    # 采集控制
    # ------------------------------------------------------------------ #

    def _start_recording(self, item=None):
        """启动数据采集。"""
        thread = threading.Thread(target=self._recorder.start, daemon=True)
        thread.start()
        self._is_running = True
        self._is_paused = False
        self._update_menu()
        logger.info("数据采集已启动")
        show_toast("AI Recorder", "数据采集已启动，正在后台运行...")

    def _pause(self, item):
        """暂停数据采集（不丢失已有记录）。"""
        self._recorder.stop()
        self._is_paused = True
        self._is_running = False
        self._update_menu()
        logger.info("数据采集已暂停")
        show_toast("AI Recorder", "数据采集已暂停")

    def _resume(self, item):
        """恢复数据采集。"""
        thread = threading.Thread(target=self._recorder.start, daemon=True)
        thread.start()
        self._is_running = True
        self._is_paused = False
        self._update_menu()
        logger.info("数据采集已恢复")
        show_toast("AI Recorder", "数据采集已恢复")

    def _toggle(self, item):
        """兼容旧接口的切换方法（已弃用，保留以防其他地方调用）。"""
        if self._is_running and not self._is_paused:
            self._pause(item)
        elif self._is_paused:
            self._resume(item)
        else:
            self._start_recording(item)

    # ------------------------------------------------------------------ #
    # 日报生成
    # ------------------------------------------------------------------ #

    def _generate_report(self, item, target: str = None):
        """生成指定日期的日报。

        Args:
            item: 菜单项
            target: 目标日期字符串 "YYYY-MM-DD"，默认昨天
        """
        from core.reporter import generate_report
        from output.markdown import save_markdown_report
        from output.html import save_html_report

        try:
            target_date = date.fromisoformat(target) if target else date.today() - timedelta(days=1)
        except ValueError:
            show_toast("AI Recorder", "日期格式错误，请使用 YYYY-MM-DD")
            return

        logger.info(f"正在生成 {target_date} 的日报...")
        show_toast("AI Recorder", f"正在生成 {target_date} 的日报...")

        report_data = generate_report(target_date)

        if not report_data.get("success"):
            show_toast("AI Recorder", f"日报生成失败: {report_data.get('error', '未知错误')}")
            return

        md_path = save_markdown_report(report_data, target_date)
        html_path = save_html_report(report_data, target_date)

        files = []
        if md_path:
            files.append(f"Markdown: {os.path.basename(md_path)}")
        if html_path:
            files.append(f"HTML: {os.path.basename(html_path)}")

        msg = f"✅ 日报已生成\n" + "\n".join(files)
        show_toast("AI Recorder", msg)

    def _show_date_picker(self, item):
        """简易日期选择器：弹出输入框让用户输入日期。"""
        import tkinter as tk
        from tkinter import simpledialog

        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口
        root.attributes("-topmost", True)

        today = date.today().isoformat()
        result = simpledialog.askstring(
            "选择日期",
            f"请输入日期 (格式: YYYY-MM-DD)\n\n当前日期: {today}",
            initialvalue=today,
            parent=root,
        )
        root.destroy()

        if result:
            self._generate_report(item, target=result)

    # ------------------------------------------------------------------ #
    # 周报生成
    # ------------------------------------------------------------------ #

    def _generate_weekly_report(self, item, this_week: bool = True):
        """生成周报。

        Args:
            this_week: True=本周(周一至今天), False=上周(完整周)
        """
        from core.weekly import generate_week_report, save_weekly_markdown_report, save_weekly_html_report

        today = date.today()
        weekday = today.weekday()  # 0=周一

        if this_week:
            # 本周周一到今天
            start_date = today - timedelta(days=weekday)
            end_date = today
        else:
            # 上周完整周
            last_monday = today - timedelta(days=weekday + 7)
            last_sunday = last_monday + timedelta(days=6)
            start_date = last_monday
            end_date = last_sunday

        label = "本周" if this_week else "上周"
        logger.info(f"正在生成 {label} ({start_date} ~ {end_date}) 的周报...")
        show_toast("AI Recorder", f"正在生成{label}周报...")

        report_data = generate_week_report(start_date, end_date)

        if not report_data.get("success"):
            show_toast("AI Recorder", f"周报生成失败: {report_data.get('error', '未知错误')}")
            return

        md_path = save_weekly_markdown_report(report_data, start_date)
        html_path = save_weekly_html_report(report_data, start_date)

        files = []
        if md_path:
            files.append(f"Markdown: {os.path.basename(md_path)}")
        if html_path:
            files.append(f"HTML: {os.path.basename(html_path)}")

        msg = f"✅ {label}周报已生成\n" + "\n".join(files)
        show_toast("AI Recorder", msg)

    # ------------------------------------------------------------------ #
    # 统计与报告
    # ------------------------------------------------------------------ #

    def _show_stats(self, item):
        """显示实时统计信息。"""
        from storage.database import get_total_records, get_recent_days

        total = get_total_records()
        if total == 0:
            show_toast("AI Recorder", "暂无数据。请先启动数据采集。")
            return

        # 今天已记录时长
        today = date.today()
        start = today.isoformat() + "T00:00:00"
        end = date.today().isoformat() + "T" + date.today().strftime("%H:%M:%S")

        try:
            from storage.database import _get_conn
            conn = _get_conn()
            cursor = conn.execute(
                """SELECT COALESCE(SUM(duration_seconds), 0) as total
                   FROM records
                   WHERE date(start_time) = date(?)""",
                (today.isoformat(),),
            )
            row = cursor.fetchone()
            total_secs = row["total"] if row else 0
            conn.close()
        except Exception:
            total_secs = 0

        total_mins = total_secs // 60
        total_h = total_mins // 60
        rem_mins = total_mins % 60

        # 最近 3 天数据
        recent = get_recent_days(3)
        recent_lines = []
        for day_str in sorted(recent.keys(), reverse=True)[:3]:
            day_data = recent[day_str]
            day_secs = sum(item["total_seconds"] for item in day_data)
            day_mins = day_secs // 60
            cats = ", ".join(
                f"{item['category']}:{item['total_seconds']//60}m"
                for item in sorted(day_data, key=lambda x: x["total_seconds"], reverse=True)[:3]
            )
            recent_lines.append(f"  {day_str}: {day_mins}min ({cats})")

        msg = (
            f"📊 AI Recorder 统计\n\n"
            f"累计记录: {total} 条\n"
            f"今天: {total_h}h{rem_mins}m\n\n"
            f"最近 3 天:\n" + "\n".join(recent_lines)
        )
        show_toast("AI Recorder", msg, duration=3)

    def _open_latest_report(self, item):
        """打开最新的报告文件（日报或周报）。"""
        from config.settings import REPORTS_DIR

        if not os.path.isdir(REPORTS_DIR):
            show_toast("AI Recorder", "报告文件夹不存在")
            return

        try:
            # 找最新的 HTML 报告文件（按修改时间排序）
            reports = [
                f for f in os.listdir(REPORTS_DIR)
                if f.endswith(".html")
            ]
            if not reports:
                show_toast("AI Recorder", "没有找到报告文件")
                return

            # 按文件修改时间排序，取最新的
            reports.sort(key=lambda f: os.path.getmtime(os.path.join(REPORTS_DIR, f)))
            latest = reports[-1]
            filepath = os.path.join(REPORTS_DIR, latest)

            # 用默认浏览器打开
            import webbrowser
            webbrowser.open("file://" + filepath)
            show_toast("AI Recorder", f"已打开: {latest}")
        except Exception as e:
            show_toast("AI Recorder", f"打开报告失败: {e}")

    def _open_reports(self, item):
        """打开报告文件夹。"""
        from config.settings import REPORTS_DIR

        os.makedirs(REPORTS_DIR, exist_ok=True)
        try:
            os.startfile(REPORTS_DIR)
        except OSError:
            # macOS / Linux 回退
            subprocess.call(["open" if os.name == "darwin" else "xdg-open", REPORTS_DIR])

    # ------------------------------------------------------------------ #
    # 退出
    # ------------------------------------------------------------------ #

    def _quit(self, item):
        """退出程序：先停止采集，再退出托盘。"""
        if self._is_running:
            self._recorder.stop()
        logger.info("正在退出...")
        show_toast("AI Recorder", "AI Recorder 已退出")
        if self._icon:
            self._icon.stop()
        else:
            os._exit(0)

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #

    def run(self):
        """运行托盘图标（阻塞直到用户退出）。"""
        self._icon = pystray.Icon(
            "ai-recorder",
            _create_icon_image(),
            menu=self._menu,
            title="AI Recorder",
            tooltip="AI Recorder · 双击打开",
        )
        # 双击图标也显示统计
        self._icon.default_menu_index = None
        self._icon.run()
