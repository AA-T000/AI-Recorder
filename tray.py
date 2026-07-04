"""系统托盘 — 在任务栏显示图标，右键菜单控制。"""

import logging
import threading

import pystray
from PIL import Image, ImageDraw, ImageFont

from core.recorder import WindowRecorder

logger = logging.getLogger(__name__)


def _create_icon_image():
    """创建一个简单的图标图片（播放按钮样式）。"""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 圆形背景
    draw.ellipse([4, 4, 60, 60], fill=(59, 130, 246, 200), outline=(96, 165, 250, 255))
    # 播放三角形
    draw.polygon([(24, 18), (24, 46), (46, 32)], fill=(255, 255, 255))
    return img


def _create_stop_icon_image():
    """停止状态的图标。"""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=(239, 68, 68, 200), outline=(248, 113, 113, 255))
    draw.rectangle([22, 18, 42, 46], fill=(255, 255, 255))
    return img


class TrayIcon:
    """系统托盘图标控制器。"""

    def __init__(self):
        self._recorder = WindowRecorder()
        self._menu = pystray.Menu(
            pystray.MenuItem("开始记录", self._toggle),
            pystray.MenuItem("生成昨天日报", self._generate_report),
            pystray.MenuItem("查看统计", self._show_stats),
            pystray.MenuItem("退出", self._quit),
        )

    def _toggle(self, item: pystray.MenuItem):
        if self._recorder.is_running():
            self._recorder.stop()
            item.title = "开始记录"
            logger.info("数据采集已停止")
        else:
            self._start_recording()

    def _start_recording(self):
        thread = threading.Thread(target=self._recorder.start, daemon=True)
        thread.start()
        logger.info("数据采集已启动")

    def _generate_report(self, item: pystray.MenuItem):
        from datetime import date, timedelta
        from core.reporter import generate_report
        from output.markdown import save_markdown_report
        from output.html import save_html_report

        yesterday = date.today() - timedelta(days=1)
        logger.info(f"正在生成 {yesterday} 的日报...")
        report_data = generate_report(yesterday)

        md_path = save_markdown_report(report_data, yesterday)
        html_path = save_html_report(report_data, yesterday)

        if md_path:
            logger.info(f"Markdown 日报已保存: {md_path}")
        if html_path:
            logger.info(f"HTML 仪表盘已保存: {html_path}")

    def _show_stats(self, item: pystray.MenuItem):
        from storage.database import get_total_records
        total = get_total_records()
        logger.info(f"当前共有 {total} 条记录")

    def _quit(self, item: pystray.MenuItem):
        self._recorder.stop()
        logger.info("正在退出...")

    def run(self):
        """运行托盘图标（阻塞）。"""
        icon = pystray.Icon(
            "ai-recorder",
            _create_icon_image(),
            menu=self._menu,
            title="AI Recorder",
        )
        icon.run()
