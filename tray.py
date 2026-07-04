"""系统托盘 — 在任务栏显示图标，右键菜单控制。"""

import logging
import os
import subprocess
import threading

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


class TrayIcon:
    """系统托盘图标控制器。"""

    def __init__(self):
        self._recorder = WindowRecorder()
        self._is_running = False
        self._icon = None
        self._update_menu()

    def _update_menu(self):
        """根据运行状态更新菜单。"""
        running_text = "■ 停止记录" if self._is_running else "▶ 开始记录"
        self._menu = pystray.Menu(
            pystray.MenuItem(running_text, self._toggle),
            pystray.MenuItem("■ 停止记录", self._stop),
            pystray.MenuItem("生成昨天日报", self._generate_report),
            pystray.MenuItem("生成今天日报", self._generate_today_report),
            pystray.MenuItem("查看统计", self._show_stats),
            pystray.MenuItem("打开报告文件夹", self._open_reports),
            pystray.MenuItem("退出", self._quit),
        )

    def _toggle(self, item: pystray.MenuItem):
        if self._is_running:
            self._stop(item)
        else:
            self._start_recording()

    def _start_recording(self):
        thread = threading.Thread(target=self._recorder.start, daemon=True)
        thread.start()
        self._is_running = True
        self._update_menu()
        logger.info("数据采集已启动")
        show_toast("AI Recorder", "数据采集已启动，正在后台运行...")

    def _stop(self, item: pystray.MenuItem):
        self._recorder.stop()
        self._is_running = False
        self._update_menu()
        logger.info("数据采集已停止")
        show_toast("AI Recorder", "数据采集已停止")

    def _generate_report(self, item: pystray.MenuItem):
        from datetime import date, timedelta
        from core.reporter import generate_report
        from output.markdown import save_markdown_report
        from output.html import save_html_report

        yesterday = date.today() - timedelta(days=1)
        logger.info(f"正在生成 {yesterday} 的日报...")
        show_toast("AI Recorder", "正在生成昨天日报...")

        report_data = generate_report(yesterday)

        md_path = save_markdown_report(report_data, yesterday)
        html_path = save_html_report(report_data, yesterday)

        if md_path and html_path:
            msg = f"日报已生成\nMarkdown: {os.path.basename(md_path)}\nHTML: {os.path.basename(html_path)}"
            show_toast("AI Recorder", msg)
        elif md_path:
            show_toast("AI Recorder", f"Markdown 日报已保存: {os.path.basename(md_path)}")
        else:
            show_toast("AI Recorder", "日报生成失败，请检查日志")

    def _generate_today_report(self, item: pystray.MenuItem):
        from datetime import date
        from core.reporter import generate_report
        from output.markdown import save_markdown_report
        from output.html import save_html_report

        today = date.today()
        logger.info(f"正在生成 {today} 的日报...")
        show_toast("AI Recorder", "正在生成今天日报...")

        report_data = generate_report(today)

        md_path = save_markdown_report(report_data, today)
        html_path = save_html_report(report_data, today)

        if md_path and html_path:
            msg = f"日报已生成\nMarkdown: {os.path.basename(md_path)}\nHTML: {os.path.basename(html_path)}"
            show_toast("AI Recorder", msg)
        elif md_path:
            show_toast("AI Recorder", f"Markdown 日报已保存: {os.path.basename(md_path)}")
        else:
            show_toast("AI Recorder", "日报生成失败，请检查日志")

    def _show_stats(self, item: pystray.MenuItem):
        from storage.database import get_total_records
        total = get_total_records()
        logger.info(f"当前共有 {total} 条记录")
        show_toast("AI Recorder", f"当前共有 {total} 条记录")

    def _open_reports(self, item: pystray.MenuItem):
        """打开报告文件夹。"""
        from config.settings import REPORTS_DIR
        os.makedirs(REPORTS_DIR, exist_ok=True)
        try:
            os.startfile(REPORTS_DIR)
        except AttributeError:
            subprocess.call(["open", REPORTS_DIR])

    def _quit(self, item: pystray.MenuItem):
        if self._is_running:
            self._recorder.stop()
        logger.info("正在退出...")
        show_toast("AI Recorder", "AI Recorder 已退出")
        if self._icon:
            self._icon.stop()
        else:
            os._exit(0)

    def run(self):
        """运行托盘图标（阻塞）。"""
        self._icon = pystray.Icon(
            "ai-recorder",
            _create_icon_image(),
            menu=self._menu,
            title="AI Recorder",
        )
        self._icon.run()
