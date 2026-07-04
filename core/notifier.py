"""通知工具 — Windows 系统通知气泡。"""

import ctypes
import os
import threading
import time


def show_toast(title: str, message: str, duration: int = 4):
    """在桌面右下角显示系统通知气泡，自动消失。

    Args:
        title: 通知标题
        message: 通知内容
        duration: 显示秒数，默认4秒
    """
    def _show():
        try:
            # 使用 Windows 10+ 原生 Toast Notification API
            notification = ctypes.windll.user32
            # Shell_NotifyIcon 方式可能不可靠，改用 tkinter 临时窗口
            _show_tkinter_toast(title, message, duration)
        except Exception:
            pass

    def _show_tkinter_toast(title: str, message: str, duration: int):
        """用 tkinter 在右下角显示通知窗口。"""
        import tkinter as tk
        from tkinter import ttk

        root = tk.Tk()
        root.overrideredirect(True)  # 无边框
        root.attributes("-topmost", True)  # 置顶

        # 获取屏幕尺寸
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()

        # 窗口大小
        window_width = 320
        window_height = 80
        x = screen_width - window_width - 20  # 右下角
        y = screen_height - window_height - 80

        root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        root.configure(bg="#1e1e1e")

        # 内容标签
        label = tk.Label(
            root,
            text=f"{title}\n{message}",
            bg="#1e1e1e",
            fg="#ffffff",
            font=("Microsoft YaHei UI", 10),
            justify=tk.LEFT,
            padx=15,
            pady=10,
        )
        label.pack(fill=tk.BOTH, expand=True)

        # 关闭按钮（右上角 ×）
        close_btn = tk.Button(
            root,
            text="×",
            bg="#1e1e1e",
            fg="#ffffff",
            font=("Microsoft YaHei UI", 12, "bold"),
            bd=0,
            relief=tk.FLAT,
            cursor="hand2",
            command=root.destroy,
        )
        close_btn.place(relx=1.0, rely=0.0, anchor="ne", x=5, y=-5)

        # 自动关闭计时器
        root.after(duration * 1000, root.destroy)

        root.mainloop()

    # 在新线程中显示，不阻塞主程序
    thread = threading.Thread(target=_show, daemon=True)
    thread.start()
