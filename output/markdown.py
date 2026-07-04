"""Markdown 日报输出。"""

import os
from datetime import date
from typing import Optional

from config.settings import REPORTS_DIR


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
        content = f"# 📊 {target_date} 日报\n\n"
        content += f"> ⚠️ 生成失败: {error}\n\n"
        if analysis.get("has_data"):
            content += f"本地分析数据存在，但 AI 报告生成失败。\n"
        else:
            content += "当天没有记录数据。\n"
    else:
        # 构建 Markdown
        content = f"# 📊 {target_date} 工作日报\n\n"

        # 效率评分
        eff = analysis.get("efficiency", 0)
        if eff >= 80:
            emoji = "🌟"
        elif eff >= 60:
            emoji = "👍"
        elif eff >= 40:
            emoji = "😐"
        else:
            emoji = "💤"

        content += f"**效率评分**: {emoji} {eff}/100\n\n"

        # 基本信息
        content += f"- **最早活动**: {analysis.get('earliest', '?')}"
        content += f"\n- **最晚活动**: {analysis.get('latest', '?')}"
        content += f"\n- **总工作时长**: {analysis.get('work_duration', 0) // 60} 分钟"
        content += f"\n- **记录数**: {analysis.get('record_count', 0)}\n\n"

        # 时间分布
        if analysis.get("category_stats"):
            content += "## ⏰ 时间分布\n\n"
            content += "| 类别 | 图标 | 占比 | 时长 |\n"
            content += "|------|------|------|------|\n"
            for cat in analysis["category_stats"]:
                mins = cat["seconds"] // 60
                content += f"| {cat['name']} | {cat['icon']} | {cat['percentage']}% | {mins}分钟 |\n"
            content += "\n"

        # 时间黑洞
        if analysis.get("holes"):
            content += "## 🔍 时间黑洞报告\n\n"
            for hole in analysis["holes"]:
                severity_icon = {"warning": "⚠️", "info": "ℹ️"}.get(hole["severity"], "•")
                content += f"{severity_icon} **{hole['title']}**: {hole['detail']}\n"
                content += f"   → 建议: {hole['suggestion']}\n\n"
        else:
            content += "## 🔍 时间黑洞报告\n\n✅ 未发现明显的时间黑洞，今天很专注！\n\n"

        # AI 报告
        if ai_report:
            content += "---\n\n"
            content += "## 🤖 AI 分析\n\n"
            content += ai_report

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath
