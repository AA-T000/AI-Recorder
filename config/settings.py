import yaml
import os

DEFAULT_SETTINGS = {
    "recorder": {
        "sample_interval": 5,
        "privacy_mode": True,
    },
    "ai": {
        "api_base": "",
        "api_key": "",
        "model": "agnes-4.8-1m",
        "prompt_template": "daily_report",
    },
    "categories": {
        "development": ["code", "vscode", "pycharm", "idea", "visual studio", "sublime", "atom"],
        "browser": ["chrome", "edge", "firefox", "browser", "microsoft edge", "google chrome"],
        "communication": ["wechat", "dingtalk", "teams", "zoom", "meeting", "qq", "企业微信", "钉钉", "微信"],
        "design": ["photoshop", "premiere", "figma", "sketch", "illustrator", "audition"],
        "office": ["word", "excel", "powerpoint", "wps", "outlook", "邮件", "文档", "表格", "演示"],
        "terminal": ["cmd", "powershell", "terminal", "git bash", "bash", "wsl"],
        "other": [],
    },
    "blackhole": {
        "fragment_threshold": 3,
        "focus_block_minutes": 20,
        "fragment_window_minutes": 5,
    },
    "app_aliases": {
        # 默认映射，用户可在 settings.yaml 中覆盖
        "pycharm64": "PyCharm",
        "code": "VS Code",
        "msedge": "Edge",
        "chrome": "Chrome",
        "weixin": "微信",
        "explorer": "资源管理器",
        "python": "Python",
        "steamwebhelper": "Steam",
        "devenv": "Visual Studio",
        "unity": "Unity",
        "geek64": "Geek Uninstaller",
        "shellhost": "Shell Host",
        "ai-recorder": "AI Recorder",
        "powershell": "PowerShell",
        "cmd": "CMD",
    },
}

APP_DIR = os.path.expanduser("~/Documents/AI-Recorder")
CONFIG_PATH = os.path.join(APP_DIR, "config", "settings.yaml")
DB_PATH = os.path.join(APP_DIR, "data", "records.db")
REPORTS_DIR = os.path.join(APP_DIR, "reports")


def ensure_dirs():
    for d in [APP_DIR, os.path.dirname(CONFIG_PATH), os.path.dirname(DB_PATH), REPORTS_DIR]:
        os.makedirs(d, exist_ok=True)


def load_settings() -> dict:
    ensure_dirs()
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        merged = _deep_merge(DEFAULT_SETTINGS, user_cfg)
        return merged
    # Write default config
    ensure_dirs()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(DEFAULT_SETTINGS, f, default_flow_style=False, allow_unicode=True)
    return DEFAULT_SETTINGS.copy()


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
