"""Markdown 日报输出 — 应用时间线 + 效率洞察 + 精简 AI 建议。"""

import os
from datetime import date
from typing import Optional

from config.settings import REPORTS_DIR, load_settings

# 全局应用名映射表（从 settings 加载）
_aliases = {}


def _load_aliases():
    global _aliases
    if not _aliases:
        try:
            settings = load_settings()
            raw = settings.get("app_aliases", {})
            _aliases = {k.lower(): v for k, v in raw.items()}
        except Exception:
            pass

# 分类映射（与 analyzer.py 保持一致）
CATEGORY_NAMES = {
    "development": "开发",
    "browser": "浏览器",
    "communication": "通讯",
    "design": "设计",
    "office": "办公",
    "terminal": "终端",
    "other": "其他",
}

CATEGORY_ICONS = {
    "development": "🟦",
    "browser": "🟧",
    "communication": "🟨",
    "design": "🟪",
    "office": "📄",
    "terminal": "⬛",
    "other": "⬜",
}


def _score_bar(score: int) -> str:
    """生成进度条: ████░░░░ 72/100"""
    filled = score // 10
    empty = 10 - filled
    return "█" * filled + "░" * empty


def _seconds_to_hm(seconds: int) -> str:
    """秒数转可读格式。"""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0 and m > 0:
        return f"{h}h {m}m"
    elif h > 0:
        return f"{h}h"
    return f"{m}m"


def _clean_app_name(raw: str) -> str:
    """清理应用名：去掉 .exe、下划线、多余后缀，保留可读名称。"""
    _load_aliases()
    name = raw.strip().lower()
    if name.endswith(".exe"):
        name = name[:-4]
    if name in _aliases:
        return _aliases[name]
    return name.replace("_", " ").title()


def _build_timeline_table(blocks: list, min_duration_min: int = 2) -> str:
    """构建应用时间线表格（过滤掉太短的块，只显示有意义的）。"""
    if not blocks:
        return "- 暂无数据\n"

    lines = []
    for b in blocks:
        duration_sec = b.get("duration", 0)
        if duration_sec < min_duration_min * 60:
            continue

        start = b["start"]
        end = b["end"]
        if hasattr(start, "strftime"):
            start_str = start.strftime("%H:%M")
            end_str = end.strftime("%H:%M")
        else:
            start_str = str(start)
            end_str = str(end)

        icon = CATEGORY_ICONS.get(b["category"], "⬜")
        app_names = b.get("app_names", [])
        if isinstance(app_names, list):
            cleaned = [_clean_app_name(a) for a in app_names[:2]]
            apps_str = ", ".join(cleaned) if cleaned else "-"
        else:
            apps_str = _clean_app_name(str(app_names)) if app_names else "-"
        cat_name = CATEGORY_NAMES.get(b["category"], b["category"])

        lines.append(f"| {start_str}-{end_str} | {apps_str} | {icon} {cat_name} | {_seconds_to_hm(duration_sec)} |")

    if not lines:
        return "- 记录过短，无有意义的工作块\n"

    header = "| 时间 | 应用 | 分类 | 时长 |"
    sep = "|------|------|------|------|"
    table_rows = '\n'.join(lines)
    return f"{header}\n{sep}\n{table_rows}"


def save_markdown_report(report_data: dict, target_date: Optional[date] = None) -> Optional[str]:
    """将 AI 日报保存为 Markdown 文件。

    Returns:
        文件路径，或 None（保存失败）。
    """
    if target_date is None:
        target_date = date.fromisoformat(report_data.get("date", date.today().isoformat()))

    os.makedirs(REPORTS_DIR, exist_ok=True)
    filepath = os.path.join(REPORTS_DIR, f"{target_date.isoformat()}.md")

    analysis = report_data.get("local_analysis", {})
    ai_report = report_data.get("ai_report", "")
    success = report_data.get("success", False)
    error = report_data.get("error", "")

    if not success:
        content = f"# 📊 {target_date} 工作日报\n\n"
        content += f"> ⚠️ 生成失败: {error}\n\n"
        if analysis.get("has_data"):
            content += "本地分析数据存在，但 AI 报告生成失败。\n"
        else:
            content += "当天没有记录数据。\n"
    else:
        content = f"# 📊 {target_date} 工作日报\n\n"

        # ---- 概览 ----
        eff = analysis.get("efficiency", 0)
        earliest = analysis.get("earliest", "?")
        latest = analysis.get("latest", "?")
        work_mins = analysis.get("work_duration", 0) // 60
        bar = _score_bar(eff)

        content += "## 📈 概览\n\n"
        content += f"**效率评分**: {bar} {eff}/100\n\n"
        content += f"{earliest} ─────── {latest}  ({work_mins}分钟)\n\n"

        # ---- 应用时间线 ----
        content += "## 🕐 应用时间线\n\n"
        blocks = analysis.get("timeline", [])
        content += _build_timeline_table(blocks)
        content += "\n\n"

        # ---- 时间分布 ----
        content += "## 📊 时间分布\n\n"
        for cat in analysis.get("category_stats", []):
            mins = cat["seconds"] // 60
            content += f"- {cat['icon']} {cat['name']}: {cat['percentage']}% ({mins}分钟)\n"
        content += "\n"

        # ---- 时间黑洞分析（特色板块） ----
        content += "## 🔍 时间黑洞分析\n\n"
        holes = analysis.get("holes", [])
        if holes:
            for hole in holes:
                sev_icon = {"warning": "⚠️", "info": "ℹ️"}.get(hole.get("severity"), "•")
                content += f"{sev_icon} **{hole['title']}**: {hole['detail']}\n"
                content += f"   → {hole.get('suggestion', '')}\n\n"
        else:
            content += "✅ 未发现明显的时间黑洞，今天很专注！\n\n"

        # ---- AI 报告（按章节拆分） ----
        if ai_report:
            import re
            # 过滤掉 AI 自带的标题前缀（如 "# 个人成长日报"、"## 日期" 等）
            cleaned_lines = []
            for line in ai_report.split("\n"):
                stripped = line.strip()
                # 跳过 AI 自带的顶部标题（不含 emoji 章节号的）
                if stripped.startswith("#") and not re.match(r'^### 📋|^### 🖥️|^### 🔍|^### 💡|^### 📈', stripped):
                    continue
                # 去掉 ### 前缀
                if stripped.startswith("### "):
                    stripped = stripped[4:]
                cleaned_lines.append(stripped)
            ai_report = "\n".join(cleaned_lines)

            # 按 emoji 章节标题拆分（用中文关键词匹配，兼容 emoji 编码问题）
            section_keywords = ["今日工作清单", "应用使用", "效率洞察", "效率建议", "一句话总结"]
            sections = {}
            current_section = None
            current_lines = []

            for line in ai_report.split("\n"):
                stripped = line.strip()
                # 检查是否包含章节关键词
                found_keyword = None
                for kw in section_keywords:
                    if kw in stripped:
                        found_keyword = kw
                        break

                if found_keyword:
                    if current_section:
                        sections[current_section] = "\n".join(current_lines).strip()
                    current_section = found_keyword
                    current_lines = []
                else:
                    current_lines.append(line)

            if current_section:
                sections[current_section] = "\n".join(current_lines).strip()

            # 一、今日工作清单
            if "今日工作清单" in sections:
                content += f"## 📋 今日工作清单\n\n{sections['今日工作清单']}\n\n"

            # 二、应用使用
            if "应用使用" in sections:
                content += f"## 🖥️ 应用使用\n\n{sections['应用使用']}\n\n"

            # 三、效率洞察
            if "效率洞察" in sections:
                content += f"## 🔍 效率洞察\n\n{sections['效率洞察']}\n\n"

            # 四、建议
            if "效率建议" in sections:
                content += f"## 💡 建议\n\n{sections['效率建议']}\n\n"

            # 五、一句话总结
            if "一句话总结" in sections:
                content += f"## 📌 总结\n\n{sections['一句话总结']}\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath
