"""HTML 仪表盘输出。"""

import os
from datetime import date, datetime
from typing import Optional

from config.settings import REPORTS_DIR


def save_html_report(report_data: dict, target_date: Optional[date] = None) -> Optional[str]:
    """生成交互式 HTML 仪表盘。"""
    if target_date is None:
        target_date = date.fromisoformat(report_data.get("date", date.today().isoformat()))

    os.makedirs(REPORTS_DIR, exist_ok=True)
    filepath = os.path.join(REPORTS_DIR, f"dashboard-{target_date.isoformat()}.html")

    analysis = report_data.get("local_analysis", {})
    ai_report = report_data.get("ai_report", "")
    success = report_data.get("success", False)

    # 准备数据
    categories_html = ""
    if analysis.get("category_stats"):
        for cat in analysis["category_stats"]:
            color = _get_category_color(cat["category"])
            categories_html += f"""
            <div class="cat-bar">
                <span class="cat-name">{cat['icon']} {cat['name']}</span>
                <div class="bar-track">
                    <div class="bar-fill" style="width:{cat['percentage']}%;background:{color}"></div>
                </div>
                <span class="cat-val">{cat['percentage']}% ({cat['seconds']//60}min)</span>
            </div>"""

    timeline_html = ""
    for block in analysis.get("timeline", [])[:50]:
        start = block["start"].strftime("%H:%M")
        duration_min = block.get("duration", 0) // 60
        icon = _get_icon(block["category"])
        color = _get_category_color(block["category"])
        timeline_html += f"""
        <div class="tl-block" style="border-left-color:{color}">
            <span class="tl-time">{start}</span>
            <span class="tl-icon">{icon}</span>
            <span class="tl-app">{block['app']}</span>
            <span class="tl-duration">{duration_min}m</span>
        </div>"""

    holes_html = ""
    if analysis.get("holes"):
        for hole in analysis["holes"]:
            sev_class = hole["severity"]
            holes_html += f"""
            <div class="hole-card {sev_class}">
                <strong>{hole['title']}</strong>
                <p>{hole['detail']}</p>
                <em>建议: {hole['suggestion']}</em>
            </div>"""
    else:
        holes_html = "<p style='color:#4ade80'>✅ 未发现明显的时间黑洞</p>"

    eff = analysis.get("efficiency", 0)
    eff_color = "#4ade80" if eff >= 70 else "#fbbf24" if eff >= 40 else "#f87171"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📊 {target_date} 工作日报</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
       background:#0f0f0f; color:#e5e5e5; padding:24px; max-width:900px; margin:0 auto; }}
h1 {{ font-size:28px; margin-bottom:8px; }}
.subtitle {{ color:#888; margin-bottom:24px; }}
.score {{ display:inline-block; font-size:48px; font-weight:bold; color:{eff_color};
          border:3px solid {eff_color}; border-radius:12px; padding:8px 24px; margin:16px 0; }}
.section {{ margin:24px 0; }}
.section-title {{ font-size:18px; font-weight:bold; margin-bottom:12px;
                  border-bottom:1px solid #333; padding-bottom:6px; }}
.cat-bar {{ display:flex; align-items:center; margin:6px 0; gap:12px; }}
.cat-name {{ width:80px; font-size:14px; white-space:nowrap; }}
.bar-track {{ flex:1; height:20px; background:#1a1a1a; border-radius:4px; overflow:hidden; }}
.bar-fill {{ height:100%; border-radius:4px; transition:width 0.5s; }}
.cat-val {{ width:100px; font-size:13px; color:#888; text-align:right; }}
.tl-block {{ display:flex; align-items:center; gap:10px; padding:6px 10px;
             margin:2px 0; border-left:3px solid #555; background:#1a1a1a;
             border-radius:0 4px 4px 0; font-size:13px; }}
.tl-time {{ color:#888; width:45px; }}
.tl-icon {{ width:20px; }}
.tl-app {{ flex:1; }}
.tl-duration {{ color:#888; width:40px; text-align:right; }}
.hole-card {{ background:#1a1a1a; border-radius:8px; padding:12px; margin:8px 0; }}
.hole-card.warning {{ border-left:3px solid #f87171; }}
.hole-card.info {{ border-left:3px solid #60a5fa; }}
.hole-card p {{ margin:4px 0; }}
.ai-section {{ background:#1a1a1a; border-radius:8px; padding:16px; margin:16px 0;
              white-space:pre-wrap; line-height:1.7; font-size:14px; }}
.stats-row {{ display:flex; gap:16px; margin:12px 0; flex-wrap:wrap; }}
.stat-card {{ background:#1a1a1a; border-radius:8px; padding:12px 16px; flex:1; min-width:120px; }}
.stat-label {{ font-size:12px; color:#888; }}
.stat-value {{ font-size:20px; font-weight:bold; margin-top:4px; }}
</style>
</head>
<body>
<h1>📊 {target_date} 工作日报</h1>
<p class="subtitle">AI Recorder · 自动生成</p>

<div class="score">{eff}</div>

<div class="stats-row">
    <div class="stat-card">
        <div class="stat-label">最早活动</div>
        <div class="stat-value">{analysis.get('earliest', '?')}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">最晚活动</div>
        <div class="stat-value">{analysis.get('latest', '?')}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">总时长</div>
        <div class="stat-value">{analysis.get('work_duration', 0)//60} 分钟</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">记录数</div>
        <div class="stat-value">{analysis.get('record_count', 0)}</div>
    </div>
</div>

<div class="section">
    <div class="section-title">⏰ 时间分布</div>
    {categories_html if categories_html else '<p>暂无数据</p>'}
</div>

<div class="section">
    <div class="section-title">📋 时间线</div>
    {timeline_html if timeline_html else '<p>暂无数据</p>'}
</div>

<div class="section">
    <div class="section-title">🔍 时间黑洞报告</div>
    {holes_html}
</div>

{f'<div class="section"><div class="section-title">🤖 AI 分析</div><div class="ai-section">{ai_report}</div></div>' if ai_report else ''}

</body>
</html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    return filepath


def _get_category_color(category: str) -> str:
    colors = {
        "development": "#3b82f6",
        "browser": "#f97316",
        "communication": "#eab308",
        "design": "#a855f7",
        "office": "#64748b",
        "terminal": "#22c55e",
        "other": "#6b7280",
    }
    return colors.get(category, "#6b7280")


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
