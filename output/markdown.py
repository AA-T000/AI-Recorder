"""Markdown 日报输出 — 应用时间线 + 效率洞察 + 精简 AI 建议。"""

import os
from datetime import date
from typing import Optional

from config.settings import REPORTS_DIR

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


def _build_timeline_table(blocks: list, min_duration_min: int = 2) -> str:
    """构建应用时间线表格（过滤掉太短的块，只显示有意义的）。"""
    if not blocks:
        return "- 暂无数据\n"

    lines = []
    for b in blocks:
        duration_sec = b.get("duration", 0)
        # 太短的块跳过（< min_duration_min 分钟的不显示）
        if duration_sec < min_duration_min * 60:
            continue

        start = b["start"]
        end = b["end"]
        # 处理时间格式
        if hasattr(start, "strftime"):
            start_str = start.strftime("%H:%M")
            end_str = end.strftime("%H:%M")
        else:
            start_str = str(start)
            end_str = str(end)

        icon = CATEGORY_ICONS.get(b["category"], "⬜")
        app_names = b.get("app_names", [])
        apps_str = ", ".join(app_names[:2]) if app_names else "-"
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

        # ---- AI 建议（精简） ----
        if ai_report:
            content += "## 💡 AI 建议\n\n"
            # AI prompt 要求 2-3 条建议 + 一句话总结
            # 提取建议部分
            suggestion_lines = []
            summary_line = ""
            in_suggestions = False
            in_summary = False
            for line in ai_report.split("\n"):
                stripped = line.strip()
                if "💡 效率建议" in stripped or "建议" in stripped:
                    in_suggestions = True
                    in_summary = False
                    continue
                if "📝 一句话总结" in stripped or "📈 一句话总结" in stripped:
                    in_suggestions = False
                    in_summary = True
                    continue
                if in_suggestions and stripped:
                    suggestion_lines.append(stripped)
                if in_summary and stripped:
                    summary_line = stripped

            if suggestion_lines:
                for i, s in enumerate(suggestion_lines[:3], 1):
                    # 清理数字前缀
                    clean = s.lstrip("0123456789.）)- ")
                    content += f"{i}. {clean}\n"
                content += "\n"

            if summary_line:
                content += f"## 📝 总结\n\n{summary_line}\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath
