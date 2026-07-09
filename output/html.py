"""HTML 仪表盘输出 — 磷光终端风（Phosphor Terminal）。
基于 finesse-ui 方法论重构：移除 AI 廉价感模式，采用单一灵魂人格。
"""

import os
import json
from datetime import date
from typing import Optional

from config.settings import REPORTS_DIR, load_settings
from core.analyzer import CATEGORY_NAMES, CATEGORY_ICONS


def _clean_ai_report(raw: str) -> str:
    """清洗 AI 报告：去掉 markdown 格式，转为 HTML。"""
    import re
    lines = raw.split("\n")
    cleaned = []
    in_list = False

    for line in lines:
        stripped = line.strip()

        # 跳过纯介绍性废话
        if not cleaned and re.match(r'^你好|我是|这份日报|旨在帮助|个人成长日报', stripped):
            continue

        # 章节标题 ### → h4
        if stripped.startswith("### "):
            section_text = stripped[4:]
            section_titles = ["📋 今日工作清单", "🖥️ 应用使用", "🔍 效率洞察", "💡 效率建议", "📈 一句话总结"]
            if section_text in section_titles:
                cleaned.append(f"<h4 style='color:rgba(200,255,220,0.6);margin:16px 0 8px;font-size:13px;font-family:'JetBrains Mono',monospace;'>{section_text}</h4>")
                continue
            else:
                continue

        # 去掉一级/二级标题
        if stripped.startswith("# ") or stripped.startswith("## "):
            continue

        # 有序列表
        ordered_match = re.match(r'^(\d+)\.\s+(.*)', stripped)
        if ordered_match:
            if not in_list:
                cleaned.append("<ol style='padding-left:24px;margin:4px 0;'>")
                in_list = True
            num, content = ordered_match.group(1), ordered_match.group(2)
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
            cleaned.append(f"<li>{content}</li>")
            continue

        # 无序列表
        if stripped.startswith("* ") or stripped.startswith("- "):
            if not in_list:
                cleaned.append("<ul style='padding-left:20px;margin:4px 0;'>")
                in_list = True
            item = stripped[2:]
            item = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', item)
            if item.startswith("    "):
                cleaned.append(f"<li style='padding-left:16px'>{item.strip()}</li>")
            else:
                cleaned.append(f"<li>{item}</li>")
            continue

        # 段落
        if in_list:
            cleaned.append("</ul>")
            in_list = False
        if stripped:
            if " · " in stripped and ("使用时长" in stripped or "主要用途" in stripped):
                parts = [p.strip() for p in stripped.split(" · ")]
                html_parts = []
                for part in parts:
                    part = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', part)
                    html_parts.append(part)
                cleaned.append(f'<p style="margin:6px 0;line-height:1.8">{"".join(html_parts)}</p>')
            else:
                stripped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)
                cleaned.append(f"<p style='margin:4px 0;line-height:1.6'>{stripped}</p>")

    if in_list:
        cleaned.append("</ul>")

    return "\n".join(cleaned)


def _get_phosphor_palette(category: str) -> tuple:
    """磷光终端风格配色：暗底 + 单色荧光绿 + 分类微色调。"""
    # 主色调：荧光绿（终端风格）
    primary = "#00ff88"
    # 分类微调色相偏移（保持整体统一，仅微调）
    hue_shifts = {
        "development": "#00ff88",
        "browser": "#f0c040",
        "communication": "#50b0ff",
        "design": "#c070ff",
        "office": "#a0a0a0",
        "terminal": "#00ff88",
        "gaming": "#ff5050",
        "finance": "#40d0a0",
        "network": "#40c0e0",
        "system": "#8080ff",
        "audio": "#ff70b0",
        "other": "#606060",
    }
    return hue_shifts.get(category, primary), primary


def save_html_report(report_data: dict, target_date: Optional[date] = None) -> Optional[str]:
    """生成交互式 HTML 仪表盘 — 磷光终端风。"""
    if target_date is None:
        target_date = date.fromisoformat(report_data.get("date", date.today().isoformat()))

    os.makedirs(REPORTS_DIR, exist_ok=True)
    filepath = os.path.join(REPORTS_DIR, f"dashboard-{target_date.isoformat()}.html")

    analysis = report_data.get("local_analysis", {})
    ai_report_raw = report_data.get("ai_report", "")
    ai_report = _clean_ai_report(ai_report_raw) if ai_report_raw else ""
    success = report_data.get("success", False)

    eff = analysis.get("efficiency", 0)
    eff_color = "#00ff88" if eff >= 70 else "#f0c040" if eff >= 40 else "#ff5050"
    categories_html = _build_categories_html(analysis.get("category_stats", []))
    timeline_html = _build_timeline_html(analysis.get("timeline", []))
    holes_html = _build_holes_html(analysis.get("holes", []))

    # 构建专注时段 HTML
    focus_sessions = analysis.get("focus_sessions", [])
    focus_html = ''
    if focus_sessions:
        focus_html = '<div class="focus-list">'
        for fs in focus_sessions:
            apps_clean = [_clean_app_name(a) for a in fs.get("app_names", [])]
            apps_str = ", ".join(apps_clean) if apps_clean else "-"
            focus_html += f'''
        <div class="focus-item">
            <span class="fi-time">{fs['start']} - {fs['end']}</span>
            <span class="fi-app">{apps_str}</span>
            <span class="fi-dur">{fs['duration']//60}m</span>
        </div>'''
        focus_html += '</div>'

    # 准备 ECharts 数据
    pie_data = []
    for cat in analysis.get("category_stats", []):
        color, _ = _get_phosphor_palette(cat["category"])
        pie_data.append({
            "name": cat["name"],
            "value": cat["seconds"] // 60,
            "itemStyle": {"color": color}
        })

    hourly_labels = []
    hourly_values = []
    hourly_colors = []
    hourly_bg_colors = []
    for h in range(24):
        hh = f"{h:02d}"
        if hh in analysis.get("hourly_distribution", {}):
            hourly_labels.append(f"{h:02d}:00")
            total_mins = analysis["hourly_distribution"][hh]["total_seconds"] // 60
            hourly_values.append(total_mins)
            if total_mins >= 60:
                hourly_colors.append("#00ff88")
                hourly_bg_colors.append("#00ff8822")
            elif total_mins >= 30:
                hourly_colors.append("#f0c040")
                hourly_bg_colors.append("#f0c04022")
            else:
                hourly_colors.append("#50b0ff")
                hourly_bg_colors.append("#50b0ff22")
        else:
            hourly_labels.append(f"{h:02d}:00")
            hourly_values.append(0)
            hourly_colors.append("#1a2a22")
            hourly_bg_colors.append("#1a2a22")

    peak_hours = analysis.get("peak_hours", [])
    peak_labels = [f"{p['hour']}:00" for p in peak_hours]

    focus_labels = [f"{fs['start']}-{fs['end']}" for fs in focus_sessions]
    focus_durations = [fs["duration"] // 60 for fs in focus_sessions]
    focus_apps = [", ".join(fs.get("app_names", [])) for fs in focus_sessions]

    chart_config = {
        "pie_data": pie_data,
        "hourly_labels": hourly_labels,
        "hourly_values": hourly_values,
        "hourly_colors": hourly_colors,
        "hourly_bg_colors": hourly_bg_colors,
        "peak_labels": peak_labels,
        "focus_labels": focus_labels,
        "focus_durations": focus_durations,
        "focus_apps": focus_apps,
        "peak_hours_data": peak_hours,
    }
    chart_json = json.dumps(chart_config, ensure_ascii=False)

    # 效率等级标签
    if eff >= 80:
        eff_label = "高效"
    elif eff >= 60:
        eff_label = "良好"
    elif eff >= 40:
        eff_label = "一般"
    elif eff >= 20:
        eff_label = "偏低"
    else:
        eff_label = "低效"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{target_date} 日报</title>
<style>
/* ===== 基础重置 ===== */
* {{ margin:0; padding:0; box-sizing:border-box; }}
html {{ scroll-behavior:smooth; }}

/* ===== 字体栈：JetBrains Mono（终端） + 系统无衬线 ===== */
body {{
    font-family: 'JetBrains Mono', 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
    background: #0a0e0a;
    color: #c8ffc8;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}}

/* ===== WebGL 流光背景容器 ===== */
#bg-canvas {{
    position: fixed;
    top: 0; left: 0;
    width: 100vw; height: 100vh;
    z-index: 0;
    opacity: 0.45;
}}

/* ===== 暗角叠加层 ===== */
.page-overlay {{
    position: relative;
    z-index: 1;
    background: radial-gradient(ellipse at 50% 0%, transparent 30%, rgba(10,14,10,0.7) 70%, #0a0e0a 100%);
    min-height: 100vh;
    pointer-events: none;
}}
.page-overlay > * {{
    pointer-events: auto;
}}

/* ===== 全局容器 ===== */
.wrap {{
    max-width: 860px;
    margin: 0 auto;
    padding: 0 24px;
    position: relative;
    z-index: 1;
}}

/* ===== 头部 ===== */
.header {{
    padding: 48px 0 32px;
    border-bottom: 1px solid rgba(0,255,136,0.08);
    margin-bottom: 32px;
}}
.header-date {{
    font-size: 11px;
    color: rgba(0,255,136,0.3);
    letter-spacing: 0.15em;
    text-transform: uppercase;
    margin-bottom: 8px;
}}
.header-title {{
    font-size: 28px;
    font-weight: 700;
    color: #e0ffe0;
    letter-spacing: -0.02em;
    line-height: 1.1;
}}
.header-brand {{
    font-size: 11px;
    color: rgba(0,255,136,0.2);
    margin-top: 8px;
    letter-spacing: 0.1em;
}}

/* ===== 效率评分 ===== */
.score-row {{
    display: flex;
    align-items: baseline;
    gap: 20px;
    margin: 28px 0 36px;
    padding: 20px 24px;
    background: rgba(0,255,136,0.02);
    border: 1px solid rgba(0,255,136,0.06);
    border-radius: 2px;
    width: fit-content;
}}
.score-num {{
    font-size: 52px;
    font-weight: 700;
    color: {eff_color};
    line-height: 1;
    font-variant-numeric: tabular-nums;
}}
.score-meta {{ flex: 1; }}
.score-label {{
    font-size: 11px;
    color: rgba(200,255,200,0.4);
    margin-bottom: 6px;
    letter-spacing: 0.08em;
}}
.score-tag {{
    font-size: 13px;
    color: {eff_color};
    font-weight: 600;
}}
.score-bar-track {{
    width: 140px;
    height: 3px;
    background: rgba(0,255,136,0.08);
    border-radius: 1px;
    overflow: hidden;
    margin-top: 8px;
}}
.score-bar-fill {{
    height: 100%;
    width: {eff}%;
    background: {eff_color};
    border-radius: 1px;
    transition: width 1.5s cubic-bezier(0.16, 1, 0.3, 1);
}}

/* ===== 统计行（非卡片，用分隔线） ===== */
.stats-row {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0;
    margin-bottom: 40px;
    border-top: 1px solid rgba(0,255,136,0.08);
    border-bottom: 1px solid rgba(0,255,136,0.08);
}}
.stat-item {{
    padding: 16px 12px;
    text-align: center;
    border-right: 1px solid rgba(0,255,136,0.04);
}}
.stat-item:last-child {{ border-right: none; }}
.stat-item .label {{
    font-size: 10px;
    color: rgba(200,255,200,0.3);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 6px;
}}
.stat-item .value {{
    font-size: 20px;
    font-weight: 600;
    color: #d0ffd0;
    font-variant-numeric: tabular-nums;
}}

/* ===== 分区 ===== */
.section {{ margin: 36px 0; scroll-margin-top: 20px; }}
.section-header {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(0,255,136,0.06);
}}
.section-num {{
    font-size: 10px;
    color: rgba(0,255,136,0.25);
    font-variant-numeric: tabular-nums;
    min-width: 20px;
}}
.section-title {{
    font-size: 14px;
    font-weight: 600;
    color: rgba(200,255,200,0.7);
    letter-spacing: 0.05em;
}}

/* ===== 图表容器 ===== */
.chart-row {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin: 16px 0;
}}
.chart-card {{
    padding: 16px;
    border: 1px solid rgba(0,255,136,0.06);
    border-radius: 2px;
    background: rgba(0,255,136,0.01);
}}
.chart-container {{
    width: 100%;
    height: 280px;
}}
.chart-caption {{
    font-size: 11px;
    color: rgba(200,255,200,0.35);
    margin-bottom: 12px;
    letter-spacing: 0.05em;
}}

/* ===== 时间分布条 ===== */
.cat-bar {{
    display: flex;
    align-items: center;
    margin: 10px 0;
    gap: 12px;
}}
.cat-name {{
    width: 70px;
    font-size: 12px;
    color: rgba(200,255,200,0.55);
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
}}
.cat-dot {{
    width: 6px;
    height: 6px;
    border-radius: 50%;
    display: inline-block;
}}
.bar-track {{
    flex: 1;
    height: 20px;
    background: rgba(0,255,136,0.03);
    border-radius: 1px;
    overflow: hidden;
}}
.bar-fill {{
    height: 100%;
    border-radius: 1px;
    transition: width 1.5s cubic-bezier(0.16, 1, 0.3, 1);
}}
.cat-val {{
    width: 90px;
    font-size: 12px;
    color: rgba(200,255,200,0.4);
    text-align: right;
    font-variant-numeric: tabular-nums;
    flex-shrink: 0;
}}

/* ===== 时间线 ===== */
.tl-card {{
    display: flex;
    align-items: stretch;
    gap: 14px;
    padding: 14px 16px;
    margin: 6px 0;
    border-left: 2px solid rgba(0,255,136,0.12);
    font-size: 12px;
    transition: background 0.2s;
}}
.tl-card:hover {{
    background: rgba(0,255,136,0.02);
}}
.tl-card-time {{
    color: rgba(200,255,200,0.3);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    padding-top: 2px;
    width: 40px;
    flex-shrink: 0;
    text-align: right;
}}
.tl-card-dot {{
    width: 6px;
    height: 6px;
    border-radius: 50%;
    margin-top: 6px;
    flex-shrink: 0;
}}
.tl-card-body {{ flex: 1; min-width: 0; }}
.tl-card-top {{
    display: flex;
    align-items: center;
    gap: 10px;
}}
.tl-card-info {{ flex: 1; min-width: 0; }}
.tl-card-name {{
    font-weight: 600;
    color: rgba(200,255,200,0.8);
    font-size: 13px;
    margin-bottom: 2px;
}}
.tl-card-cat {{
    font-size: 11px;
    color: rgba(200,255,200,0.3);
}}
.tl-card-sub {{
    font-size: 11px;
    color: rgba(200,255,200,0.35);
    margin-top: 4px;
    padding-left: 46px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}}
.tl-card-duration {{
    color: rgba(200,255,200,0.3);
    font-size: 12px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    padding-top: 2px;
    flex-shrink: 0;
}}

/* ===== 专注时段 ===== */
.focus-list {{
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin: 12px 0;
}}
.focus-item {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    border: 1px solid rgba(0,255,136,0.08);
    border-radius: 2px;
    font-size: 12px;
}}
.focus-item .fi-time {{
    color: rgba(200,255,200,0.45);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    width: 80px;
    flex-shrink: 0;
}}
.focus-item .fi-app {{
    flex: 1;
    color: rgba(200,255,200,0.75);
    font-weight: 500;
}}
.focus-item .fi-dur {{
    color: #00ff88;
    font-weight: 600;
    font-size: 12px;
    flex-shrink: 0;
}}

/* ===== 时间黑洞 ===== */
.hole-card {{
    padding: 12px 14px;
    margin: 8px 0;
    border-left: 2px solid rgba(0,255,136,0.15);
    border-radius: 0 2px 2px 0;
    background: rgba(0,255,136,0.01);
    transition: background 0.2s;
}}
.hole-card:hover {{ background: rgba(0,255,136,0.03); }}
.hole-card.warning {{ border-left-color: #ff5050; }}
.hole-card.info {{ border-left-color: #50b0ff; }}
.hole-card strong {{ font-size: 13px; color: #d0ffd0; font-weight: 600; }}
.hole-card p {{ margin: 4px 0; font-size: 12px; color: rgba(200,255,200,0.5); }}
.hole-card em {{ font-size: 11px; color: rgba(200,255,200,0.3); font-style: normal; }}

/* ===== AI 报告 ===== */
.ai-section {{
    padding: 20px;
    border: 1px solid rgba(0,255,136,0.06);
    border-radius: 2px;
    background: rgba(0,255,136,0.01);
    line-height: 1.8;
    font-size: 13px;
    color: rgba(200,255,200,0.65);
}}

/* ===== 空状态 ===== */
.empty-state {{
    text-align: center;
    padding: 24px 16px;
    color: rgba(200,255,200,0.2);
    font-size: 12px;
    letter-spacing: 0.05em;
}}

/* ===== 折叠提示 ===== */
.fold-hint {{
    text-align: center;
    padding: 6px 0;
    color: rgba(200,255,200,0.2);
    font-size: 11px;
}}

/* ===== 页脚 ===== */
.footer {{
    text-align: center;
    padding: 48px 0 24px;
    color: rgba(200,255,200,0.12);
    font-size: 10px;
    letter-spacing: 0.15em;
    border-top: 1px solid rgba(0,255,136,0.04);
    margin-top: 48px;
}}

/* ===== 响应式 ===== */
@media (max-width: 768px) {{
    .wrap {{ padding: 0 16px; }}
    .header {{ padding: 32px 0 24px; }}
    .header-title {{ font-size: 22px; }}
    .score-row {{ flex-direction: column; align-items: flex-start; gap: 12px; }}
    .score-num {{ font-size: 40px; }}
    .stats-row {{ grid-template-columns: repeat(2, 1fr); }}
    .stat-item {{ padding: 12px 8px; }}
    .stat-item .value {{ font-size: 18px; }}
    .chart-row {{ grid-template-columns: 1fr; }}
    .chart-container {{ height: 240px; }}
    .cat-name {{ width: 50px; font-size: 11px; }}
    .cat-val {{ width: 60px; font-size: 11px; }}
    .tl-card {{ padding: 10px 12px; }}
    .tl-card-sub {{ padding-left: 0; }}
}}

@media (prefers-reduced-motion: reduce) {{
    .score-bar-fill {{ transition: none; }}
    .bar-fill {{ transition: none; }}
    .tl-card {{ transition: none; }}
    .hole-card {{ transition: none; }}
}}
</style>
</head>
<body>
<!-- ===== WebGL 流光背景 ===== -->
<canvas id="bg-canvas"></canvas>

<div class="page-overlay">
<div class="wrap">

    <!-- ===== 头部 ===== -->
    <div class="header" id="overview">
        <div class="header-date">{target_date.strftime('%A').replace('星期一','Mon').replace('星期二','Tue').replace('星期三','Wed').replace('星期四','Thu').replace('星期五','Fri').replace('星期六','Sat').replace('星期日','Sun')} · {target_date.strftime('%Y.%m.%d')}</div>
        <div class="header-title">工作日报</div>
        <div class="header-brand">AI Recorder</div>
    </div>

    <!-- ===== 效率评分 ===== -->
    <div class="score-row">
        <div class="score-num">{eff}</div>
        <div class="score-meta">
            <div class="score-label">效率评分</div>
            <div class="score-tag">{eff_label}</div>
            <div class="score-bar-track"><div class="score-bar-fill"></div></div>
        </div>
    </div>

    <!-- ===== 统计行 ===== -->
    <div class="stats-row">
        <div class="stat-item">
            <div class="label">最早</div>
            <div class="value">{analysis.get('earliest', '?')}</div>
        </div>
        <div class="stat-item">
            <div class="label">最晚</div>
            <div class="value">{analysis.get('latest', '?')}</div>
        </div>
        <div class="stat-item">
            <div class="label">总时长</div>
            <div class="value">{analysis.get('total_actual_seconds', 0)//60}m</div>
        </div>
        <div class="stat-item">
            <div class="label">记录数</div>
            <div class="value">{analysis.get('record_count', 0)}</div>
        </div>
    </div>

    <!-- ===== 1. 数据可视化 ===== -->
    <div class="section" id="charts">
        <div class="section-header">
            <span class="section-num">01</span>
            <span class="section-title">数据可视化</span>
        </div>
        <div class="chart-row">
            <div class="chart-card">
                <div class="chart-caption">时间分布</div>
                <div id="chart-pie" class="chart-container"></div>
            </div>
            <div class="chart-card">
                <div class="chart-caption">每小时活跃度</div>
                <div id="chart-hourly" class="chart-container"></div>
            </div>
        </div>
    </div>

    <!-- ===== 2. 时间分布 ===== -->
    <div class="section" id="distribution">
        <div class="section-header">
            <span class="section-num">02</span>
            <span class="section-title">时间分布</span>
        </div>
        {categories_html if categories_html else '<div class="empty-state">暂无数据</div>'}
    </div>

    <!-- ===== 3. 时间线 ===== -->
    <div class="section" id="timeline">
        <div class="section-header">
            <span class="section-num">03</span>
            <span class="section-title">时间线</span>
        </div>
        {timeline_html if timeline_html else '<div class="empty-state">暂无数据</div>'}
    </div>

    <!-- ===== 4. 专注时段 ===== -->
    <div class="section" id="focus">
        <div class="section-header">
            <span class="section-num">04</span>
            <span class="section-title">专注时段</span>
        </div>
        {focus_html if focus_sessions else '<div class="empty-state">今天没有 >=20 分钟的连续专注时段</div>'}
    </div>

    <!-- ===== 5. 时间黑洞 ===== -->
    <div class="section" id="holes">
        <div class="section-header">
            <span class="section-num">05</span>
            <span class="section-title">时间黑洞</span>
        </div>
        {holes_html if holes_html else '<div class="empty-state">未发现明显的时间黑洞</div>'}
    </div>

    <!-- ===== 6. AI 分析 ===== -->
    <div class="section" id="ai">
        <div class="section-header">
            <span class="section-num">06</span>
            <span class="section-title">AI 分析</span>
        </div>
        {f'<div class="ai-section">{ai_report}</div>' if ai_report else ''}
    </div>

    <div class="footer">AI RECORDER</div>

</div><!-- /.wrap -->
</div><!-- /.page-overlay -->

<!-- ECharts CDN -->
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>

<script>
// ===== WebGL 流光背景（磷光终端绿） =====
(function() {{
    var container = document.getElementById('bg-canvas');
    if (!container) return;

    var gl = container.getContext('webgl', {{ alpha: true, antialias: false }});
    if (!gl) {{
        container.style.display = 'none';
        return;
    }}

    // 磷光终端配色：荧光绿为主，分类微调色相
    var colors = [
        [0.0, 1.0, 0.53],   // 荧光绿（开发/主色）
        [0.2, 0.8, 0.4],    // 深绿（辅助）
        [0.5, 0.9, 0.3],    // 黄绿（高亮）
    ];
    var bgColor = [0.04, 0.06, 0.04];  // 暗绿底色

    var vertSrc = `
        attribute vec2 position;
        attribute vec2 uv;
        varying vec2 vUv;
        void main() {{
            vUv = uv;
            gl_Position = vec4(position, 0.0, 1.0);
        }}
    `;

    var fragSrc = `
        precision highp float;
        uniform vec3  iResolution;
        uniform float iTime;
        uniform vec3  uColor0;
        uniform vec3  uColor1;
        uniform vec3  uColor2;
        uniform vec3  uBgColor;
        uniform float uStreakCount;
        uniform float uSpeed;
        uniform float uGlow;
        uniform float uDensity;
        uniform float uTwinkle;
        varying vec2 vUv;

        vec3 palette(float h) {{
            if (h < 0.333) return uColor0;
            if (h < 0.666) return uColor1;
            return uColor2;
        }}

        void main() {{
            vec2 uv = vUv * iResolution.xy;
            float T = iTime * uSpeed;
            float angRings = max(1.0, floor(6.28 * max(uDensity, 0.05) + 0.5));
            vec2 Y = vec2(0.005, 6.283 / angRings);

            float bgGlow = exp(-dot(uv - iResolution.xy * 0.5, uv - iResolution.xy * 0.5) / max(dot(iResolution.xy, iResolution.xy) * 0.3, 1e-4)) * 0.15;
            vec3 col = uBgColor + vec3(bgGlow);

            float tail = 19.0;
            for (int m = 0; m < 16; m++) {{
                if (float(m) >= uStreakCount) break;
                float jf = float(m) + 1.0;
                float ic = fract(sin(dot(vec2(jf, 7.0), vec2(7.0, 11.0))) * 73.0);
                float h = fract(8663.0 * ic);
                vec3 c = palette(h);
                float weight = mix(1.5, 1.0 + sin(T + 7.0 * h + 4.0), uTwinkle);

                float phase = fract((T + T * ic) / Y.y + 0.5);
                float trail = exp(-abs(uv.y - phase * iResolution.y) / max(Y.x * iResolution.y, 1.0));
                float fade = smoothstep(0.0, 0.1, phase) * smoothstep(1.0, 0.7, phase);

                col += c * trail * weight * 0.6 * fade;
            }}

            gl_FragColor = vec4(col * uGlow, 1.0);
        }}
    `;

    function compileShader(src, type) {{
        var shader = gl.createShader(type);
        gl.shaderSource(shader, src);
        gl.compileShader(shader);
        if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {{
            return null;
        }}
        return shader;
    }}

    var vert = compileShader(vertSrc, gl.VERTEX_SHADER);
    var frag = compileShader(fragSrc, gl.FRAGMENT_SHADER);
    if (!vert || !frag) {{
        container.style.display = 'none';
        return;
    }}

    var program = gl.createProgram();
    gl.attachShader(program, vert);
    gl.attachShader(program, frag);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {{
        container.style.display = 'none';
        return;
    }}
    gl.useProgram(program);

    var positions = new Float32Array([-1,-1, 1,-1, -1,1, 1,1]);
    var uvs = new Float32Array([0,0, 1,0, 0,1, 1,1]);
    var posBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, posBuf);
    gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW);
    var posLoc = gl.getAttribLocation(program, 'position');
    gl.enableVertexAttribArray(posLoc);
    gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 0, 0);

    var uvBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, uvBuf);
    gl.bufferData(gl.ARRAY_BUFFER, uvs, gl.STATIC_DRAW);
    var uvLoc = gl.getAttribLocation(program, 'uv');
    gl.enableVertexAttribArray(uvLoc);
    gl.vertexAttribPointer(uvLoc, 2, gl.FLOAT, false, 0, 0);

    var locs = {{}};
    ['iResolution','iTime','uColor0','uColor1','uColor2','uBgColor',
     'uStreakCount','uSpeed','uGlow','uDensity','uTwinkle'].forEach(function(n) {{
        locs[n] = gl.getUniformLocation(program, n);
    }});

    var params = {{
        speed: 0.3,
        streakCount: 3,
        glow: 1.0,
        density: 0.4,
        twinkle: 0.8,
    }};

    var lastTime = 0;

    function resize() {{
        var rect = container.getBoundingClientRect();
        var w = Math.floor(rect.width * window.devicePixelRatio);
        var h = Math.floor(rect.height * window.devicePixelRatio);
        canvas.width = w;
        canvas.height = h;
        gl.viewport(0, 0, w, h);
        gl.uniform3f(locs.iResolution, w, h, 1);
    }}
    var canvas = container;
    resize();
    var ro = new ResizeObserver(resize);
    ro.observe(container);

    function animate(time) {{
        requestAnimationFrame(animate);
        if (time - lastTime < 33) return;
        lastTime = time;

        gl.uniform1f(locs.iTime, time * 0.001);
        gl.uniform3fv(locs.uColor0, colors[0]);
        gl.uniform3fv(locs.uColor1, colors[1]);
        gl.uniform3fv(locs.uColor2, colors[2]);
        gl.uniform3fv(locs.uBgColor, bgColor);
        gl.uniform1f(locs.uSpeed, params.speed);
        gl.uniform1i(locs.uStreakCount, params.streakCount);
        gl.uniform1f(locs.uGlow, params.glow);
        gl.uniform1f(locs.uDensity, params.density);
        gl.uniform1f(locs.uTwinkle, params.twinkle);

        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }}
    requestAnimationFrame(animate);

    document.addEventListener('visibilitychange', function() {{
        if (document.hidden) cancelAnimationFrame(animate);
    }});
}})();
(function() {{
    if (typeof echarts === 'undefined') return;

    var chartData = {chart_json};

    // 饼图：时间分布
    var pieChart = echarts.init(document.getElementById('chart-pie'), null, {{ renderer: 'canvas' }});
    pieChart.setOption({{
        tooltip: {{
            trigger: 'item',
            formatter: '{{b}}: {{c}}分钟 ({{d}}%)'
        }},
        series: [{{
            type: 'pie',
            radius: ['35%', '65%'],
            center: ['50%', '55%'],
            avoidLabelOverlap: true,
            itemStyle: {{
                borderRadius: 2,
                borderColor: '#0a0e0a',
                borderWidth: 2
            }},
            label: {{
                show: true,
                position: 'outside',
                formatter: '{{b}}\\n{{d}}%',
                color: 'rgba(200,255,200,0.5)',
                fontSize: 10,
                fontFamily: "'JetBrains Mono', monospace"
            }},
            labelLine: {{
                lineStyle: {{ color: 'rgba(200,255,200,0.15)' }}
            }},
            data: chartData.pie_data
        }}]
    }});

    // 柱状图：每小时活跃度
    var hourlyChart = echarts.init(document.getElementById('chart-hourly'), null, {{ renderer: 'canvas' }});
    hourlyChart.setOption({{
        tooltip: {{
            trigger: 'axis',
            axisPointer: {{ type: 'shadow' }},
            formatter: function(params) {{
                var p = params[0];
                return p.name + '<br/>' + p.seriesName + ': ' + p.value + '分钟';
            }}
        }},
        grid: {{
            left: '3%',
            right: '4%',
            bottom: '3%',
            top: '8%',
            containLabel: true
        }},
        xAxis: {{
            type: 'category',
            data: chartData.hourly_labels,
            axisLabel: {{
                color: 'rgba(200,255,200,0.3)',
                fontSize: 9,
                fontFamily: "'JetBrains Mono', monospace"
            }},
            axisLine: {{ lineStyle: {{ color: 'rgba(0,255,136,0.08)' }} }},
            axisTick: {{ show: false }}
        }},
        yAxis: {{
            type: 'value',
            name: '',
            axisLabel: {{
                color: 'rgba(200,255,200,0.3)',
                fontSize: 9,
                fontFamily: "'JetBrains Mono', monospace"
            }},
            splitLine: {{ lineStyle: {{ color: 'rgba(0,255,136,0.04)' }} }},
            axisLine: {{ show: false }},
            axisTick: {{ show: false }}
        }},
        series: [{{
            name: '活跃度',
            type: 'bar',
            barWidth: '55%',
            data: chartData.hourly_values.map(function(val, idx) {{
                return {{
                    value: val,
                    itemStyle: {{
                        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                            {{ offset: 0, color: chartData.hourly_colors[idx] }},
                            {{ offset: 1, color: chartData.hourly_bg_colors[idx] }}
                        ])
                    }}
                }};
            }})
        }}]
    }});

    window.addEventListener('resize', function() {{
        pieChart.resize();
        hourlyChart.resize();
    }});
}})();
</script>

</body>
</html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    return filepath


def _build_categories_html(stats: list) -> str:
    if not stats:
        return ""
    html = ""
    for cat in stats:
        color, _ = _get_phosphor_palette(cat["category"])
        html += f"""
        <div class="cat-bar">
            <span class="cat-name"><span class="cat-dot" style="background:{color}"></span>{cat['name']}</span>
            <div class="bar-track">
                <div class="bar-fill" style="width:{cat['percentage']}%;background:{color}"></div>
            </div>
            <span class="cat-val">{cat['percentage']}% ({cat['seconds']//60}m)</span>
        </div>"""
    return html


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


def _clean_app_name(raw: str) -> str:
    """清理应用名：去掉 .exe、下划线、多余后缀，保留可读名称。"""
    _load_aliases()
    name = raw.strip().lower()
    if name.endswith(".exe"):
        name = name[:-4]
    if name in _aliases:
        return _aliases[name]
    return name.replace("_", " ").title()


def _get_app_icon(category: str) -> str:
    """返回分类图标字符。"""
    icon_map = {
        "development": "</>",
        "browser": "www",
        "communication": "msg",
        "design": "pal",
        "office": "doc",
        "terminal": "term",
        "gaming": "game",
        "finance": "fin",
        "network": "net",
        "system": "sys",
        "audio": "snd",
        "other": "...",
    }
    return icon_map.get(category, "...")


def _build_timeline_html(timeline: list) -> str:
    if not timeline:
        return ""

    filtered = [b for b in timeline if b.get("duration", 0) >= 60]
    if not filtered:
        filtered = timeline

    html = ""
    for block in filtered:
        start = block["start"].strftime("%H:%M") if hasattr(block["start"], "strftime") else str(block["start"])
        end = block["end"].strftime("%H:%M") if hasattr(block["end"], "strftime") else ""
        duration_min = block.get("duration", 0) // 60
        color, _ = _get_phosphor_palette(block["category"])
        icon = CATEGORY_ICONS.get(block["category"], "·")
        name = CATEGORY_NAMES.get(block["category"], block["category"])
        apps = block.get("app_names", [])
        if isinstance(apps, list):
            cleaned = [_clean_app_name(a) for a in apps[:2]]
            apps_str = ", ".join(cleaned)
        else:
            apps_str = _clean_app_name(str(apps))

        titles = block.get("titles", [])
        subtitle = ""
        if isinstance(titles, list) and titles:
            subtitle = titles[0][:40]

        html += f"""
        <div class="tl-card">
            <div class="tl-card-time">{start}</div>
            <div class="tl-card-dot" style="background:{color}"></div>
            <div class="tl-card-body">
                <div class="tl-card-top">
                    <div class="tl-card-name">{apps_str}</div>
                    <div class="tl-card-cat">{icon} {name}</div>
                </div>
                {'<div class="tl-card-sub">' + subtitle + '</div>' if subtitle else ''}
            </div>
            <div class="tl-card-duration">{duration_min}m</div>
        </div>"""

    if len(timeline) - len(filtered) > 0:
        hidden = len(timeline) - len(filtered)
        html += f'<div class="fold-hint">还有 {hidden} 个短块（<1分钟）已折叠</div>'

    return html


def _build_holes_html(holes: list) -> str:
    if not holes:
        return ""
    html = ""
    for hole in holes:
        sev_class = hole["severity"]
        html += f"""
        <div class="hole-card {sev_class}">
            <strong>{hole['title']}</strong>
            <p>{hole['detail']}</p>
            <em>建议: {hole['suggestion']}</em>
        </div>"""
    return html
