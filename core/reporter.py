"""AI 日报生成器 — 将本地分析结果发送给 Agnes API，生成智能日报。"""

import json
import logging
from datetime import date
from typing import Optional

import requests

from config.settings import load_settings
from core.analyzer import analyze_day, CATEGORY_NAMES


def _clean_app_name_for_ai(raw: str) -> str:
    """清理应用名给 AI 使用：去掉 .exe，用可读名称。"""
    name = raw.strip().lower()
    if name.endswith(".exe"):
        name = name[:-4]
    # 优先查配置表（不区分大小写）
    try:
        settings = load_settings()
        aliases = settings.get("app_aliases", {})
        # 构建小写 key 的映射
        lower_aliases = {k.lower(): v for k, v in aliases.items()}
        if name in lower_aliases:
            return lower_aliases[name]
    except Exception:
        pass
    # 内置兜底映射
    fallback = {
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
        "tslgame": "PUBG",
    }
    return fallback.get(name, name.replace("_", " ").title())

logger = logging.getLogger(__name__)


def _build_prompt(analysis: dict, settings: dict) -> str:
    """构建发送给 AI 的 prompt。"""
    ai_cfg = settings.get("ai", {})
    model = ai_cfg.get("model", "agnes-4.8-1m")

    categories = []
    for cat in analysis.get("category_stats", []):
        categories.append(f"- {cat['icon']} {cat['name']}: {cat['percentage']}% ({cat['seconds']//60}分钟)")

    holes = []
    for hole in analysis.get("holes", []):
        holes.append(f"- [{hole['severity']}] {hole['title']}: {hole['detail']}")

    # 构建应用使用详情（从合并后的 timeline 重新计算，保证准确）
    # 按应用聚合时长
    app_totals = {}  # {应用名: 总秒数}
    app_categories = {}  # {应用名: 分类名}
    for block in analysis.get("timeline", []):
        dur = block.get("duration", 0)
        cat_name = CATEGORY_NAMES.get(block["category"], block["category"])
        for app in block.get("app_names", []):
            clean = _clean_app_name_for_ai(app)
            app_totals[clean] = app_totals.get(clean, 0) + dur
            app_categories[clean] = cat_name

    # 按总时长排序，取前 5 个
    top_apps = sorted(app_totals.items(), key=lambda x: x[1], reverse=True)[:5]
    app_usage_lines = []
    for app_name, total_secs in top_apps:
        mins = total_secs // 60
        cat = app_categories.get(app_name, "未知")
        app_usage_lines.append(f"- {app_name} ({mins}分钟, {cat})")

    app_usage_str = "\n".join(app_usage_lines) if app_usage_lines else "- 暂无数据"

    # 构建专注时段
    focus_items = []
    for fs in analysis.get("focus_sessions", [])[:5]:
        apps_clean = [_clean_app_name_for_ai(a) for a in fs.get("app_names", [])]
        focus_items.append(f"- {fs['start']}-{fs['end']} {', '.join(apps_clean)} ({fs['duration']//60}分钟)")

    # 构建峰值时段
    peak_items = []
    for ph in analysis.get("peak_hours", []):
        h = ph["hour"]
        mins = ph["total_seconds"] // 60
        cat_name = CATEGORY_NAMES.get(ph["dominant_category"], ph["dominant_category"])
        peak_items.append(f"- {h}:00 ({mins}分钟, {cat_name})")

    prompt = f"""你是一个个人成长复盘助手。根据以下本地分析数据，生成一份结构化的中文日报。

## 工具定位
- 这是自我复盘、自我成长、工作沉淀、量化进度的工具
- 不是监控工具，不是批评自己的工具
- 语气应该是鼓励的、建设性的、面向成长的
- 即使效率低也要指出亮点和进步空间，不要一味批评
- 用"机会"代替"问题"，用"可以做得更好"代替"你做得不好"

## 日期
{analysis['date']}

## 概览
- 工作时长: {analysis.get('total_actual_seconds', 0) // 60} 分钟
- 最早活动: {analysis.get('earliest', '?')} | 最晚活动: {analysis.get('latest', '?')}
- 效率评分: {analysis.get('efficiency', 0)}/100

## 时间分布
{chr(10).join(categories) if categories else '- 暂无数据'}

## 应用使用详情
{app_usage_str}

## 专注时段（>=20分钟）
{chr(10).join(focus_items) if focus_items else '- 今天没有 >=20 分钟的连续专注时段'}

## 峰值时段（最活跃的小时）
{chr(10).join(peak_items) if peak_items else '- 暂无数据'}

## 时间黑洞检测
{chr(10).join(holes) if holes else '- 未发现明显的时间黑洞'}

请严格按照以下格式输出，不要输出其他任何内容：

### 📋 今日工作清单
用 3-5 条列出今天的主要活动块，格式：
- **HH:MM - HH:MM**：简要描述活动（如"代码开发"、"浏览器浏览"），括号标注时长

### 🖥️ 应用使用
列出使用最多的 3-5 个应用，格式：
**应用名** · 使用时长：XX 分钟 · 主要用途：XXX
每行一个应用，用 · 分隔，紧凑排列不要分行

### 🔍 效率洞察
给出 1-2 条核心洞察，基于数据说话

### 💡 效率建议
给出 2-3 条具体可行的改进建议

### 📈 一句话总结
用一句话概括今天的工作状态
"""

    return prompt


def _get_icon(category: str) -> str:
    icons = {
        "development": "🟦",
        "browser": "🟧",
        "communication": "🟨",
        "design": "🟪",
        "office": "📄",
        "terminal": "⬛",
        "other": "⬜",
    }
    return icons.get(category, "⬜")


def _get_category_name(category: str) -> str:
    names = {
        "development": "开发",
        "browser": "浏览器",
        "communication": "通讯",
        "design": "设计",
        "office": "办公",
        "terminal": "终端",
        "other": "其他",
    }
    return names.get(category, category)


def generate_report(target_date: Optional[date] = None) -> dict:
    """生成一天的 AI 日报。

    Returns:
        {
            "date": "2026-07-03",
            "local_analysis": {...},  # 本地分析结果
            "ai_report": "...",       # AI 生成的日报文本
            "success": True/False,
            "error": "..."  # 如果失败
        }
    """
    if target_date is None:
        target_date = date.today()

    settings = load_settings()
    analysis = analyze_day(target_date, settings)

    if not analysis.get("has_data"):
        return {
            "date": analysis["date"],
            "local_analysis": analysis,
            "ai_report": None,
            "success": False,
            "error": "没有数据可分析",
        }

    # 调用 AI
    ai_cfg = settings.get("ai", {})
    api_base = ai_cfg.get("api_base", "")
    api_key = ai_cfg.get("api_key", "")

    if not api_base:
        return {
            "date": analysis["date"],
            "local_analysis": analysis,
            "ai_report": None,
            "success": False,
            "error": "请在 config/settings.yaml 中配置 AI API 地址",
        }

    try:
        prompt = _build_prompt(analysis, settings)

        payload = {
            "model": ai_cfg.get("model", "agnes-4.8-1m"),
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 2000,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}" if api_key else "",
        }

        resp = requests.post(
            f"{api_base.rstrip('/')}/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()

        result = resp.json()
        ai_report = result["choices"][0]["message"]["content"]

        return {
            "date": analysis["date"],
            "local_analysis": analysis,
            "ai_report": ai_report,
            "success": True,
        }

    except requests.exceptions.ConnectionError:
        return {
            "date": analysis["date"],
            "local_analysis": analysis,
            "ai_report": None,
            "success": False,
            "error": f"无法连接到 API: {api_base}，请检查服务是否运行",
        }
    except Exception as e:
        logger.error(f"AI 报告生成失败: {e}")
        return {
            "date": analysis["date"],
            "local_analysis": analysis,
            "ai_report": None,
            "success": False,
            "error": str(e),
        }
