"""通知工具 — Windows 系统通知气泡。

使用 Windows Shell_NotifyIconW 气球提示，通过 ctypes 调用 shell32.dll，
无需 tkinter、winrt 或任何其他第三方依赖。
"""

import ctypes
import ctypes.wintypes as wt
import threading


shell32 = ctypes.windll.shell32
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("hWnd", wt.HWND),
        ("uID", wt.UINT),
        ("uFlags", wt.UINT),
        ("uCallbackMessage", wt.DWORD),
        ("hIcon", wt.HICON),
        ("szTip", ctypes.c_char * 128),
        ("dwState", wt.DWORD),
        ("dwStateMask", wt.DWORD),
        ("szInfo", ctypes.c_char * 256),
        ("uVersion", wt.UINT),
        ("szInfoTitle", ctypes.c_char * 64),
        ("dwInfoFlags", wt.DWORD),
    ]


# NIM constants
NIM_ADD = 0x00
NIM_MODIFY = 0x01
NIM_DELETE = 0x02
NIF_INFO = 0x10

# NIIF constants
NIIF_INFO = 0x01


def show_toast(title: str, message: str, duration: int = 4):
    """在桌面右下角显示 Windows 气球提示通知，自动消失。

    Args:
        title: 通知标题（最大 63 字符）
        message: 通知内容（最大 255 字符）
        duration: 显示秒数，默认4秒
    """
    thread = threading.Thread(target=_show, args=(title, message, duration), daemon=True)
    thread.start()


def _show(title: str, message: str, duration: int):
    """发送气球提示通知。"""
    try:
        # 注册窗口类
        class_name = b"AIToastClass"
        wc = ctypes.WNDCLASSW()
        wc.lpfnWndProc = ctypes.cast(user32.DefWindowProcW, ctypes.c_void_p)
        wc.lpszClassName = class_name.decode("utf-16")
        wc.hInstance = kernel32.GetModuleHandleW(None)
        atom = user32.RegisterClassW(ctypes.byref(wc))
        if not atom:
            return

        # 创建隐藏窗口
        hwnd = user32.CreateWindowExW(
            0, wc.lpszClassName, "AIToast",
            0, 0, 0, 0, 0, 0, 0, kernel32.GetModuleHandleW(None), 0
        )
        if not hwnd:
            return

        # 构建气球提示
        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = hwnd
        nid.uID = 1
        nid.uFlags = NIF_INFO
        nid.szInfo = message.encode("utf-8", errors="replace")[:255]
        nid.szInfoTitle = title.encode("utf-8", errors="replace")[:63]
        nid.dwInfoFlags = NIIF_INFO
        nid.uVersion = 4

        # 先添加图标到托盘（气球提示需要一个图标存在）
        nid.uFlags = 0x04  # NIF_TIP
        nid.szTip = b"AI Recorder"
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

        # 发送气球提示
        nid.uFlags = NIF_INFO
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

        # 延迟清理
        def cleanup():
            time.sleep(duration)
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
            user32.DestroyWindow(hwnd)

        import time
        threading.Thread(target=cleanup, daemon=True).start()

    except Exception:
        pass
