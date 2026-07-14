"""通知工具 — Windows 系统通知气泡。

使用 plyer.notification 发送 Windows 10 原生 Toast 通知。
"""

import threading


def show_toast(title: str, message: str, duration: int = 3):
    """在桌面右下角显示 Windows 原生通知气泡，自动消失。

    Args:
        title: 通知标题
        message: 通知内容（支持 \n 换行）
        duration: 显示秒数，默认4秒
    """
    thread = threading.Thread(target=_show, args=(title, message, duration), daemon=True)
    thread.start()


def _show(title: str, message: str, duration: int):
    """发送通知。"""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="AI Recorder",
            timeout=3,
        )
    except Exception:
        pass
