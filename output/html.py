"""HTML 仪表盘输出 — WebGL 流光背景 + 侧边栏导航 + ECharts 图表。"""

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
                cleaned.append(f"<h4 style='color:rgba(255,255,255,0.7);margin:16px 0 8px;font-size:14px;'>{section_text}</h4>")
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


def save_html_report(report_data: dict, target_date: Optional[date] = None) -> Optional[str]:
    """生成交互式 HTML 仪表盘。"""
    if target_date is None:
        target_date = date.fromisoformat(report_data.get("date", date.today().isoformat()))

    os.makedirs(REPORTS_DIR, exist_ok=True)
    filepath = os.path.join(REPORTS_DIR, f"dashboard-{target_date.isoformat()}.html")

    analysis = report_data.get("local_analysis", {})
    ai_report_raw = report_data.get("ai_report", "")
    ai_report = _clean_ai_report(ai_report_raw) if ai_report_raw else ""
    success = report_data.get("success", False)

    eff = analysis.get("efficiency", 0)
    eff_color = "#4ade80" if eff >= 70 else "#fbbf24" if eff >= 40 else "#f87171"
    categories_html = _build_categories_html(analysis.get("category_stats", []))
    timeline_html = _build_timeline_html(analysis.get("timeline", []))
    holes_html = _build_holes_html(analysis.get("holes", []))

    # 构建专注时段 HTML（必须在模板之前）
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
            <span class="fi-dur">{fs['duration']//60}分钟</span>
        </div>'''
        focus_html += '</div>'

    # 准备 ECharts 数据
    # 时间分布饼图数据
    pie_data = []
    for cat in analysis.get("category_stats", []):
        pie_data.append({
            "name": cat["name"],
            "value": cat["seconds"] // 60,
            "itemStyle": {"color": _get_category_color(cat["category"])}
        })

    # 每小时活跃度柱状图数据
    hourly_labels = []
    hourly_values = []
    hourly_colors = []
    hourly_bg_colors = []
    hourly_colors_full = []
    for h in range(24):
        hh = f"{h:02d}"
        if hh in analysis.get("hourly_distribution", {}):
            hourly_labels.append(f"{h:02d}:00")
            total_mins = analysis["hourly_distribution"][hh]["total_seconds"] // 60
            hourly_values.append(total_mins)
            # 根据活跃度着色
            if total_mins >= 60:
                hourly_colors_full.append("#4ade80")  # 绿色
                hourly_bg_colors.append("#4ade8044")
            elif total_mins >= 30:
                hourly_colors_full.append("#fbbf24")  # 黄色
                hourly_bg_colors.append("#fbbf2444")
            else:
                hourly_colors_full.append("#60a5fa")  # 蓝色
                hourly_bg_colors.append("#60a5fa44")
        else:
            hourly_labels.append(f"{h:02d}:00")
            hourly_values.append(0)
            hourly_colors_full.append("#334155")
            hourly_bg_colors.append("#33415544")

    # 峰值时段高亮
    peak_hours = analysis.get("peak_hours", [])
    peak_labels = [f"{p['hour']}:00" for p in peak_hours]

    # 专注时段数据
    focus_sessions = analysis.get("focus_sessions", [])
    focus_labels = [f"{fs['start']}-{fs['end']}" for fs in focus_sessions]
    focus_durations = [fs["duration"] // 60 for fs in focus_sessions]
    focus_apps = [", ".join(fs.get("app_names", [])) for fs in focus_sessions]

    # ECharts 配置 JSON
    chart_config = {
        "pie_data": pie_data,
        "hourly_labels": hourly_labels,
        "hourly_values": hourly_values,
        "hourly_colors": hourly_colors_full,
        "hourly_bg_colors": hourly_bg_colors,
        "peak_labels": peak_labels,
        "focus_labels": focus_labels,
        "focus_durations": focus_durations,
        "focus_apps": focus_apps,
        "peak_hours_data": peak_hours,
    }
    chart_json = json.dumps(chart_config, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📊 {target_date} 工作日报 — AI Recorder</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
html {{ scroll-behavior: smooth; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: #000;
    color: #e5e5e5;
    overflow-x: hidden;
}}

/* ===== WebGL 背景 ===== */
#wgsl-bg {{
    position: fixed;
    top: 0; left: 0;
    width: 100vw; height: 100vh;
    z-index: 0;
}}
#wgsl-bg canvas {{
    width: 100%; height: 100%;
    display: block;
}}

/* ===== 遮罩层 ===== */
.page-overlay {{
    position: relative;
    z-index: 1;
    background: radial-gradient(ellipse at 50% 0%, rgba(10,5,30,0.3) 0%, rgba(0,0,0,0.8) 60%);
    min-height: 100vh;
    display: flex;
}}

/* ===== 侧边栏导航 ===== */
.sidebar {{
    width: 200px;
    position: fixed;
    top: 0; left: 0;
    height: 100vh;
    background: rgba(0,0,0,0.5);
    backdrop-filter: blur(20px);
    border-right: 1px solid rgba(255,255,255,0.06);
    padding: 24px 0;
    z-index: 10;
    display: flex;
    flex-direction: column;
}}
.sidebar-brand {{
    font-size: 14px;
    font-weight: 700;
    color: rgba(255,255,255,0.5);
    padding: 0 20px;
    margin-bottom: 24px;
    letter-spacing: 1px;
}}
.sidebar-nav {{
    flex: 1;
}}
.sidebar-nav a {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 20px;
    color: rgba(255,255,255,0.4);
    text-decoration: none;
    font-size: 13px;
    transition: all 0.2s;
    border-left: 2px solid transparent;
}}
.sidebar-nav a:hover,
.sidebar-nav a.active {{
    color: rgba(255,255,255,0.9);
    background: rgba(255,255,255,0.04);
    border-left-color: #60a5fa;
}}
.sidebar-nav a .nav-icon {{
    width: 20px;
    text-align: center;
    font-size: 14px;
}}
.sidebar-footer {{
    padding: 16px 20px;
    font-size: 11px;
    color: rgba(255,255,255,0.15);
    border-top: 1px solid rgba(255,255,255,0.04);
}}

/* ===== 主内容区 ===== */
.main-content {{
    margin-left: 200px;
    width: calc(100% - 200px);
    min-height: 100vh;
}}
.container {{
    max-width: 900px;
    margin: 0 auto;
    padding: 40px 32px 80px;
}}

/* ===== 头部 ===== */
.header {{ margin-bottom: 32px; }}
.header h1 {{
    font-size: 34px;
    font-weight: 800;
    letter-spacing: -0.5px;
    background: linear-gradient(135deg, #60a5fa 0%, #a78bfa 40%, #f472b6 80%, #fb923c 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    background-size: 200% 200%;
    animation: gradientShift 6s ease infinite;
}}
@keyframes gradientShift {{
    0%, 100% {{ background-position: 0% 50%; }}
    50% {{ background-position: 100% 50%; }}
}}
.header .subtitle {{
    color: rgba(255,255,255,0.3);
    font-size: 13px;
    margin-top: 6px;
    letter-spacing: 1px;
    text-transform: uppercase;
}}

/* ===== 效率评分 ===== */
.score-card {{
    display: flex;
    align-items: center;
    gap: 16px;
    background: rgba(255,255,255,0.04);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 20px;
    padding: 24px 32px;
    margin: 24px 0 32px;
    width: fit-content;
}}
.score-num {{
    font-size: 56px;
    font-weight: 900;
    color: {eff_color};
    line-height: 1;
    font-variant-numeric: tabular-nums;
    text-shadow: 0 0 30px {eff_color}44;
}}
.score-meta {{ flex: 1; }}
.score-label {{ font-size: 13px; color: rgba(255,255,255,0.4); margin-bottom: 8px; }}
.score-bar-track {{
    width: 160px; height: 6px;
    background: rgba(255,255,255,0.08);
    border-radius: 3px;
    overflow: hidden;
}}
.score-bar-fill {{
    height: 100%;
    width: {eff}%;
    background: {eff_color};
    border-radius: 3px;
    box-shadow: 0 0 10px {eff_color}88;
    transition: width 1.5s cubic-bezier(0.22, 1, 0.36, 1);
}}

/* ===== 统计网格 ===== */
.stats-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin-bottom: 36px;
}}
.stat-card {{
    background: rgba(255,255,255,0.03);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 14px;
    padding: 18px 16px;
    text-align: center;
    transition: all 0.3s ease;
}}
.stat-card:hover {{
    background: rgba(255,255,255,0.06);
    border-color: rgba(255,255,255,0.12);
    transform: translateY(-3px);
    box-shadow: 0 8px 32px rgba(96,165,250,0.1);
}}
.stat-card .label {{
    font-size: 11px;
    color: rgba(255,255,255,0.35);
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-bottom: 8px;
}}
.stat-card .value {{
    font-size: 24px;
    font-weight: 700;
    color: #f0f0f0;
    font-variant-numeric: tabular-nums;
}}

/* ===== 分区 ===== */
.section {{ margin: 32px 0; scroll-margin-top: 20px; }}
.section-header {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 16px;
}}
.section-icon {{
    width: 28px; height: 28px;
    background: linear-gradient(135deg, rgba(96,165,250,0.2), rgba(167,139,250,0.2));
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
}}
.section-title {{
    font-size: 17px;
    font-weight: 600;
    color: rgba(255,255,255,0.8);
}}

/* ===== 图表容器 ===== */
.chart-card {{
    background: rgba(255,255,255,0.03);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 16px;
    padding: 20px;
    margin: 16px 0;
}}
.chart-container {{
    width: 100%;
    height: 300px;
}}
.chart-row {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
}}
.chart-row .chart-container {{
    height: 280px;
}}

/* ===== 时间分布 ===== */
.cat-bar {{
    display: flex;
    align-items: center;
    margin: 10px 0;
    gap: 12px;
}}
.cat-name {{
    width: 70px;
    font-size: 13px;
    color: rgba(255,255,255,0.6);
    display: flex;
    align-items: center;
    gap: 6px;
}}
.cat-dot {{
    width: 8px; height: 8px;
    border-radius: 50%;
    display: inline-block;
}}
.bar-track {{
    flex: 1;
    height: 28px;
    background: rgba(255,255,255,0.04);
    border-radius: 8px;
    overflow: hidden;
    position: relative;
}}
.bar-fill {{
    height: 100%;
    border-radius: 8px;
    transition: width 1.5s cubic-bezier(0.22, 1, 0.36, 1);
    position: relative;
}}
.bar-fill::after {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.2) 50%, transparent 100%);
    animation: barShimmer 2.5s ease-in-out infinite;
}}
@keyframes barShimmer {{
    0%, 100% {{ transform: translateX(-100%); }}
    50% {{ transform: translateX(100%); }}
}}
.cat-val {{
    width: 100px;
    font-size: 13px;
    color: rgba(255,255,255,0.45);
    text-align: right;
    font-variant-numeric: tabular-nums;
}}

/* ===== 时间线卡片 ===== */
.tl-card {{
    display: flex;
    align-items: stretch;
    gap: 14px;
    padding: 16px 20px;
    margin: 8px 0;
    border-radius: 16px;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.06);
    transition: all 0.25s ease;
    font-size: 13px;
}}
.tl-card:hover {{
    background: rgba(255,255,255,0.06);
    border-color: rgba(255,255,255,0.12);
    transform: translateX(4px);
}}
.tl-card-time {{
    color: rgba(255,255,255,0.3);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
    padding-top: 2px;
    width: 40px;
    flex-shrink: 0;
    text-align: right;
}}
.tl-card-dot {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-top: 6px;
    flex-shrink: 0;
    box-shadow: 0 0 8px currentColor;
}}
.tl-card-body {{
    flex: 1;
    min-width: 0;
}}
.tl-card-top {{
    display: flex;
    align-items: center;
    gap: 12px;
}}
.tl-card-info {{
    flex: 1;
    min-width: 0;
}}
.tl-card-name {{
    font-weight: 600;
    color: rgba(255,255,255,0.85);
    font-size: 14px;
    margin-bottom: 2px;
}}
.tl-card-cat {{
    font-size: 12px;
    color: rgba(255,255,255,0.35);
}}
.tl-card-sub {{
    font-size: 12px;
    color: rgba(255,255,255,0.4);
    margin-top: 6px;
    padding-left: 52px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}}
.tl-card-duration {{
    color: rgba(255,255,255,0.3);
    font-size: 13px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    padding-top: 2px;
    flex-shrink: 0;
}}

/* ===== 专注时段列表 ===== */
.focus-list {{
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 12px 0;
}}
.focus-item {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 16px;
    background: rgba(74, 222, 128, 0.06);
    border: 1px solid rgba(74, 222, 128, 0.12);
    border-radius: 10px;
    font-size: 13px;
}}
.focus-item .fi-time {{
    color: rgba(255,255,255,0.5);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
    width: 80px;
    flex-shrink: 0;
}}
.focus-item .fi-app {{
    flex: 1;
    color: rgba(255,255,255,0.8);
    font-weight: 500;
}}
.focus-item .fi-dur {{
    color: #4ade80;
    font-weight: 600;
    font-size: 13px;
    flex-shrink: 0;
}}

/* ===== 时间黑洞 ===== */
.hole-card {{
    background: rgba(255,255,255,0.03);
    border-radius: 12px;
    padding: 14px 16px;
    margin: 8px 0;
    border-left: 3px solid #555;
    transition: background 0.2s;
}}
.hole-card:hover {{ background: rgba(255,255,255,0.05); }}
.hole-card.warning {{ border-left-color: #f87171; }}
.hole-card.info {{ border-left-color: #60a5fa; }}
.hole-card strong {{ font-size: 14px; color: #f0f0f0; }}
.hole-card p {{ margin: 4px 0; font-size: 13px; color: rgba(255,255,255,0.55); }}
.hole-card em {{ font-size: 12px; color: rgba(255,255,255,0.35); }}

/* ===== AI 报告 ===== */
.ai-section {{
    background: rgba(255,255,255,0.03);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 14px;
    padding: 20px;
    margin: 16px 0;
    line-height: 1.8;
    font-size: 14px;
    color: rgba(255,255,255,0.75);
}}

/* ===== 空状态 ===== */
.empty-state {{
    text-align: center;
    padding: 32px 20px;
    color: rgba(255,255,255,0.25);
    font-size: 14px;
}}

/* ===== 页脚 ===== */
.footer {{
    text-align: center;
    padding: 40px 0 20px;
    color: rgba(255,255,255,0.15);
    font-size: 12px;
    letter-spacing: 1px;
}}

/* ===== 响应式 ===== */
@media (max-width: 768px) {{
    .sidebar {{ display: none; }}
    .main-content {{ margin-left: 0; width: 100%; }}
    .container {{ padding: 24px 16px 60px; }}
    .header h1 {{ font-size: 24px; }}
    .score-card {{ padding: 18px 20px; flex-direction: column; align-items: flex-start; }}
    .score-num {{ font-size: 42px; }}
    .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .stat-card .value {{ font-size: 20px; }}
    .cat-val {{ width: 70px; font-size: 12px; }}
    .cat-name {{ width: 55px; font-size: 12px; }}
    .chart-row {{ grid-template-columns: 1fr; }}
}}

@media (prefers-reduced-motion: reduce) {{
    .header h1 {{ animation: none; }}
    .bar-fill::after {{ animation: none; }}
    .stat-card {{ transition: none; }}
}}
</style>
</head>
<body>

<!-- WebGL 流光背景 -->
<div id="wgsl-bg"></div>

<div class="page-overlay">

<!-- ===== 侧边栏导航 ===== -->
<nav class="sidebar">
    <div class="sidebar-brand">AI RECORDER</div>
    <div class="sidebar-nav">
        <a href="#overview" class="active"><span class="nav-icon">📊</span> 概览</a>
        <a href="#charts"><span class="nav-icon">📈</span> 图表</a>
        <a href="#distribution"><span class="nav-icon">⏰</span> 时间分布</a>
        <a href="#timeline"><span class="nav-icon">🕐</span> 时间线</a>
        <a href="#focus"><span class="nav-icon">🎯</span> 专注时段</a>
        <a href="#holes"><span class="nav-icon">🔍</span> 时间黑洞</a>
        <a href="#ai"><span class="nav-icon">🤖</span> AI 分析</a>
    </div>
    <div class="sidebar-footer">{target_date}</div>
</nav>

<!-- ===== 主内容 ===== -->
<main class="main-content">
<div class="container">

    <div class="header" id="overview">
        <h1>📊 {target_date} 工作日报</h1>
        <p class="subtitle">AI Recorder · 自动生成</p>
    </div>

    <div class="score-card">
        <div class="score-num">{eff}</div>
        <div class="score-meta">
            <div class="score-label">效率评分</div>
            <div class="score-bar-track"><div class="score-bar-fill"></div></div>
        </div>
    </div>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="label">最早活动</div>
            <div class="value">{analysis.get('earliest', '?')}</div>
        </div>
        <div class="stat-card">
            <div class="label">最晚活动</div>
            <div class="value">{analysis.get('latest', '?')}</div>
        </div>
        <div class="stat-card">
            <div class="label">总时长</div>
            <div class="value">{analysis.get('total_actual_seconds', 0)//60} 分钟</div>
        </div>
        <div class="stat-card">
            <div class="label">记录数</div>
            <div class="value">{analysis.get('record_count', 0)}</div>
        </div>
    </div>

    <!-- ===== 图表区域 ===== -->
    <div class="section" id="charts">
        <div class="section-header">
            <div class="section-icon">📈</div>
            <div class="section-title">数据可视化</div>
        </div>
        <div class="chart-row">
            <div class="chart-card">
                <div style="font-size:13px;color:rgba(255,255,255,0.5);margin-bottom:8px;">🍩 时间分布</div>
                <div id="chart-pie" class="chart-container"></div>
            </div>
            <div class="chart-card">
                <div style="font-size:13px;color:rgba(255,255,255,0.5);margin-bottom:8px;">📊 每小时活跃度</div>
                <div id="chart-hourly" class="chart-container"></div>
            </div>
        </div>
    </div>

    <!-- ===== 时间分布 ===== -->
    <div class="section" id="distribution">
        <div class="section-header">
            <div class="section-icon">⏰</div>
            <div class="section-title">时间分布</div>
        </div>
        {categories_html if categories_html else '<div class="empty-state">暂无数据</div>'}
    </div>

    <!-- ===== 时间线 ===== -->
    <div class="section" id="timeline">
        <div class="section-header">
            <div class="section-icon">📋</div>
            <div class="section-title">时间线</div>
        </div>
        {timeline_html if timeline_html else '<div class="empty-state">暂无数据</div>'}
    </div>

    <!-- ===== 专注时段 ===== -->
    <div class="section" id="focus">
        <div class="section-header">
            <div class="section-icon">🎯</div>
            <div class="section-title">专注时段（≥20分钟）</div>
        </div>
        {focus_html if focus_sessions else '<div class="empty-state">今天没有 >=20 分钟的连续专注时段</div>'}
    </div>

    <!-- ===== 时间黑洞 ===== -->
    <div class="section" id="holes">
        <div class="section-header">
            <div class="section-icon">🔍</div>
            <div class="section-title">时间黑洞分析</div>
        </div>
        {holes_html if holes_html else '<div class="empty-state">✅ 未发现明显的时间黑洞，今天很专注！</div>'}
    </div>

    <!-- ===== AI 分析 ===== -->
    <div class="section" id="ai">
        <div class="section-header">
            <div class="section-icon">🤖</div>
            <div class="section-title">AI 分析</div>
        </div>
        {f'<div class="ai-section">{ai_report}</div>' if ai_report else ''}
    </div>

    <div class="footer">AI Recorder · 你的智能工作伙伴</div>

</div>
</main>
</div>

<!-- ECharts CDN -->
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>

<script>
// ===== 侧边栏导航高亮 =====
(function() {{
    var navLinks = document.querySelectorAll('.sidebar-nav a');
    var sections = document.querySelectorAll('.section, .header');

    function updateActiveNav() {{
        var scrollPos = window.scrollY + 100;
        for (var i = sections.length - 1; i >= 0; i--) {{
            if (sections[i].offsetTop <= scrollPos) {{
                var id = sections[i].getAttribute('id');
                navLinks.forEach(function(link) {{
                    link.classList.remove('active');
                    if (link.getAttribute('href') === '#' + id) {{
                        link.classList.add('active');
                    }}
                }});
                break;
            }}
        }}
    }}

    window.addEventListener('scroll', updateActiveNav);
    updateActiveNav();
}})();

// ===== WebGL 流光背景 =====
(function() {{
    var container = document.getElementById('wgsl-bg');
    if (!container) return;

    var isLowEnd = false;
    try {{
        var mem = navigator.deviceMemory || 4;
        var cores = navigator.hardwareConcurrency || 4;
        if (mem <= 2 || cores <= 2) isLowEnd = true;
    }} catch(e) {{}}

    var colors = [
        [0.65, 0.78, 1.0],
        [0.32, 0.15, 1.0],
        [1.0, 0.63, 0.98],
    ];
    var bgColor = [0.04, 0.02, 0.12];

    var canvas = document.createElement('canvas');
    container.appendChild(canvas);
    var gl = canvas.getContext('webgl', {{ alpha: true, antialias: !isLowEnd }});
    if (!gl) {{
        canvas.style.display = 'none';
        container.style.background = 'linear-gradient(135deg, #0a0a2e 0%, #1a0a2e 50%, #0a1a2e 100%)';
        return;
    }}

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
        uniform vec2  iMouse;
        uniform float iTime;
        uniform vec3  uColor0;
        uniform vec3  uColor1;
        uniform vec3  uColor2;
        uniform vec3  uBgColor;
        uniform float uSpeed;
        uniform int   uStreakCount;
        uniform float uStreakWidth;
        uniform float uStreakLength;
        uniform float uGlow;
        uniform float uDensity;
        uniform float uTwinkle;
        uniform float uZoom;
        uniform float uBgGlow;
        uniform float uMouseEnabled;
        uniform float uMouseStrength;
        uniform float uMouseRadius;
        varying vec2 vUv;

        vec3 palette(float h) {{
            if (h < 0.333) return uColor0;
            if (h < 0.666) return uColor1;
            return uColor2;
        }}

        vec3 tanhv(vec3 x) {{
            vec3 e = exp(-2.0 * x);
            return (1.0 - e) / (1.0 + e);
        }}

        vec2 sceneC(vec2 frag, vec2 r) {{
            vec2 P = (frag + frag - r) / r.x;
            float z = 0.0;
            float d = 1e3;
            vec4 O = vec4(0.0);
            for (int k = 0; k < 39; k++) {{
                if (d <= 1e-4) break;
                O = z * normalize(vec4(P, uZoom, 0.0)) - vec4(0.0, 4.0, 1.0, 0.0) / 4.5;
                d = 1.0 - sqrt(length(O * O));
                z += d;
            }}
            return vec2(O.x, atan(O.z, O.y));
        }}

        void mainImage(out vec4 o, vec2 C) {{
            vec2 r = iResolution.xy;
            vec2 uv0 = (C + C - r) / r.x;
            float T = 0.1 * iTime * uSpeed + 9.0;
            float angRings = max(1.0, floor(6.28318530718 * max(uDensity, 0.05) + 0.5));
            vec2 Y = vec2(5e-3, 6.28318530718 / angRings);

            vec2 c0 = sceneC(C, r);
            vec2 cdx = sceneC(C + vec2(1.0, 0.0), r);
            vec2 cdy = sceneC(C + vec2(0.0, 1.0), r);
            vec2 dCx = cdx - c0;
            vec2 dCy = cdy - c0;
            dCx.y -= 6.28318530718 * floor(dCx.y / 6.28318530718 + 0.5);
            dCy.y -= 6.28318530718 * floor(dCy.y / 6.28318530718 + 0.5);
            vec2 fw = abs(dCx) + abs(dCy);
            C = c0;

            vec2 P = vec2(2.0, 1.0) * uv0 - (r / r.x) * vec2(0.0, 1.0);
            vec4 O = vec4(uBgColor * 90.0 * uBgGlow / (1e3 * dot(P, P) + 6.0), 0.0);

            float mGlow = 0.0;
            if (uMouseEnabled > 0.5) {{
                vec2 mN = (iMouse + iMouse - r) / r.x;
                float md = length(uv0 - mN);
                mGlow = exp(-md * md / max(uMouseRadius * uMouseRadius, 1e-4)) * uMouseStrength;
                O.rgb += uColor0 * mGlow * 0.25;
            }}

            float zr = 5e-4 * uStreakWidth;
            vec2 rr = vec2(max(length(fw), 1e-5));
            float tail = 19.0 / max(uStreakLength, 0.05);

            for (int m = 0; m < 16; m++) {{
                if (m >= uStreakCount) break;
                float jf = float(m) + 1.0;
                float ic = fract(sin(dot(vec2(jf, floor(C.x / Y.x + 0.5)), vec2(7.0, 11.0)) * 73.0));
                vec2 Pp = C - (T + T * ic) * vec2(0.0, 1.0);
                Pp -= floor(Pp / Y + 0.5) * Y;
                float h = fract(8663.0 * ic);
                vec3 col = palette(h);
                float weight = mix(1.5, 1.0 + sin(T + 7.0 * h + 4.0), uTwinkle);
                weight *= (1.0 + mGlow * 2.0);
                vec2 inner = vec2(length(max(Pp, vec2(-1.0, 0.0))), length(Pp) - zr) - zr;
                vec2 sm = vec2(1.0) - smoothstep(-rr, rr, inner);
                O.rgb += dot(sm, vec2(exp(tail * Pp.y), 3.0)) * col * weight;
                C.x += Y.x / 8.0;
            }}

            vec3 colr = sqrt(tanhv(max(O.rgb * uGlow - vec3(0.04, 0.08, 0.02), 0.0)));
            o = vec4(colr, 1.0);
        }}

        void main() {{
            vec4 color;
            mainImage(color, vUv * iResolution.xy);
            gl_FragColor = color;
        }}
    `;

    function compileShader(src, type) {{
        var shader = gl.createShader(type);
        gl.shaderSource(shader, src);
        gl.compileShader(shader);
        if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {{
            console.warn('Shader compile failed:', gl.getShaderInfoLog(shader));
            return null;
        }}
        return shader;
    }}

    var vert = compileShader(vertSrc, gl.VERTEX_SHADER);
    var frag = compileShader(fragSrc, gl.FRAGMENT_SHADER);
    if (!vert || !frag) {{
        container.style.background = 'linear-gradient(135deg, #0a0a2e 0%, #1a0a2e 50%, #0a1a2e 100%)';
        return;
    }}

    var program = gl.createProgram();
    gl.attachShader(program, vert);
    gl.attachShader(program, frag);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {{
        console.warn('Program link failed:', gl.getProgramInfoLog(program));
        container.style.background = 'linear-gradient(135deg, #0a0a2e 0%, #1a0a2e 50%, #0a1a2e 100%)';
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
    var uniformNames = [
        'iResolution','iMouse','iTime',
        'uColor0','uColor1','uColor2',
        'uBgColor','uSpeed','uStreakCount','uStreakWidth',
        'uStreakLength','uGlow','uDensity','uTwinkle',
        'uZoom','uBgGlow','uMouseEnabled','uMouseStrength','uMouseRadius'
    ];
    for (var i = 0; i < uniformNames.length; i++) {{
        locs[uniformNames[i]] = gl.getUniformLocation(program, uniformNames[i]);
    }}

    var params = {{
        speed: 0.5,
        streakCount: 2,
        streakWidth: 1,
        streakLength: 1,
        glow: 1,
        density: 0.6,
        twinkle: 1,
        zoom: 3,
        bgGlow: 0.5,
        mouseEnabled: 1,
        mouseStrength: 0.5,
        mouseRadius: 1,
        mouseDampening: 0.15,
    }};

    var mouseTarget = [0, 0];
    var mouseCurrent = [0, 0];
    var lastTime = 0;

    canvas.addEventListener('mousemove', function(e) {{
        var rect = canvas.getBoundingClientRect();
        var scaleX = canvas.width / rect.width;
        var scaleY = canvas.height / rect.height;
        mouseTarget[0] = (e.clientX - rect.left) * scaleX;
        mouseTarget[1] = (rect.height - (e.clientY - rect.top)) * scaleY;
    }});
    canvas.addEventListener('mouseleave', function() {{
        mouseTarget[0] = 0;
        mouseTarget[1] = 0;
    }});
    canvas.addEventListener('touchmove', function(e) {{
        var t = e.touches[0];
        var rect = canvas.getBoundingClientRect();
        var scaleX = canvas.width / rect.width;
        var scaleY = canvas.height / rect.height;
        mouseTarget[0] = (t.clientX - rect.left) * scaleX;
        mouseTarget[1] = (rect.height - (t.clientY - rect.top)) * scaleY;
    }}, {{ passive: true }});

    function resize() {{
        var rect = container.getBoundingClientRect();
        var w = Math.floor(rect.width * (isLowEnd ? 1 : 2));
        var h = Math.floor(rect.height * (isLowEnd ? 1 : 2));
        canvas.width = w;
        canvas.height = h;
        gl.viewport(0, 0, w, h);
        gl.uniform3f(locs.iResolution, w, h, 1);
    }}
    resize();
    var ro = new ResizeObserver(resize);
    ro.observe(container);

    function animate(time) {{
        requestAnimationFrame(animate);
        if (time - lastTime < 33) return;
        lastTime = time;

        gl.uniform1f(locs.iTime, time * 0.001);

        var tau = Math.max(0.001, params.mouseDampening);
        var dt = 0.016;
        var factor = 1 - Math.exp(-dt / tau);
        mouseCurrent[0] += (mouseTarget[0] - mouseCurrent[0]) * factor;
        mouseCurrent[1] += (mouseTarget[1] - mouseCurrent[1]) * factor;
        gl.uniform2fv(locs.iMouse, mouseCurrent);

        gl.uniform3fv(locs.uColor0, colors[0]);
        gl.uniform3fv(locs.uColor1, colors[1]);
        gl.uniform3fv(locs.uColor2, colors[2]);
        gl.uniform3fv(locs.uBgColor, bgColor);

        gl.uniform1f(locs.uSpeed, params.speed);
        gl.uniform1i(locs.uStreakCount, params.streakCount);
        gl.uniform1f(locs.uStreakWidth, params.streakWidth);
        gl.uniform1f(locs.uStreakLength, params.streakLength);
        gl.uniform1f(locs.uGlow, params.glow);
        gl.uniform1f(locs.uDensity, params.density);
        gl.uniform1f(locs.uTwinkle, params.twinkle);
        gl.uniform1f(locs.uZoom, params.zoom);
        gl.uniform1f(locs.uBgGlow, params.bgGlow);
        gl.uniform1f(locs.uMouseEnabled, params.mouseEnabled);
        gl.uniform1f(locs.uMouseStrength, params.mouseStrength);
        gl.uniform1f(locs.uMouseRadius, params.mouseRadius);

        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }}
    requestAnimationFrame(animate);

    document.addEventListener('visibilitychange', function() {{
        if (document.hidden) {{
            cancelAnimationFrame(animate);
        }}
    }});
}})();

// ===== ECharts 图表 =====
(function() {{
    // 检查 ECharts 是否加载成功
    if (typeof echarts === 'undefined') {{
        console.warn('ECharts 加载失败，使用 CSS 图表回退');
        return;
    }}

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
            radius: ['40%', '70%'],
            center: ['50%', '55%'],
            avoidLabelOverlap: true,
            itemStyle: {{
                borderRadius: 6,
                borderColor: '#000',
                borderWidth: 2
            }},
            label: {{
                show: true,
                position: 'outside',
                formatter: '{{b}}\\n{{d}}%',
                color: 'rgba(255,255,255,0.6)',
                fontSize: 11
            }},
            labelLine: {{
                lineStyle: {{ color: 'rgba(255,255,255,0.2)' }}
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
            top: '10%',
            containLabel: true
        }},
        xAxis: {{
            type: 'category',
            data: chartData.hourly_labels,
            axisLabel: {{
                color: 'rgba(255,255,255,0.4)',
                fontSize: 10,
                rotate: 0,
                interval: 2
            }},
            axisLine: {{ lineStyle: {{ color: 'rgba(255,255,255,0.1)' }} }},
            axisTick: {{ show: false }}
        }},
        yAxis: {{
            type: 'value',
            name: '分钟',
            nameTextStyle: {{ color: 'rgba(255,255,255,0.3)', fontSize: 10 }},
            axisLabel: {{ color: 'rgba(255,255,255,0.4)', fontSize: 10 }},
            splitLine: {{ lineStyle: {{ color: 'rgba(255,255,255,0.05)' }} }},
            axisLine: {{ show: false }},
            axisTick: {{ show: false }}
        }},
        series: [{{
            name: '活跃度',
            type: 'bar',
            barWidth: '60%',
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
        }}],
        // 峰值时段标记
        markLine: {{
            symbol: 'none',
            data: chartData.peak_labels.map(function(label) {{
                var idx = chartData.hourly_labels.indexOf(label);
                return {{
                    xAxis: idx >= 0 ? idx : 0,
                    label: {{ show: false }}
                }};
            }})
        }}
    }});

    // 响应式
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
        color = _get_category_color(cat["category"])
        html += f"""
        <div class="cat-bar">
            <span class="cat-name"><span class="cat-dot" style="background:{color}"></span>{cat['name']}</span>
            <div class="bar-track">
                <div class="bar-fill" style="width:{cat['percentage']}%;background:linear-gradient(90deg,{color}cc,{color})"></div>
            </div>
            <span class="cat-val">{cat['percentage']}% ({cat['seconds']//60}min)</span>
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


def _get_app_icon_svg(category: str) -> str:
    """返回应用图标 SVG（圆形彩色背景 + 分类图标）。"""
    color_map = {
        "development": "#3b82f6",
        "browser": "#f97316",
        "communication": "#eab308",
        "design": "#a855f7",
        "office": "#64748b",
        "terminal": "#22c55e",
        "other": "#6b7280",
    }
    bg_color = color_map.get(category, "#6b7280")
    icon_map = {
        "development": "⟨/⟩",
        "browser": "🌐",
        "communication": "💬",
        "design": "🎨",
        "office": "📄",
        "terminal": "⬛",
        "other": "•",
    }
    icon = icon_map.get(category, "•")
    return (
        f'<div style="width:40px;height:40px;border-radius:10px;'
        f'background:{bg_color};display:flex;align-items:center;'
        f'justify-content:center;font-size:18px;flex-shrink:0;">'
        f'{icon}</div>'
    )


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
        color = _get_category_color(block["category"])
        icon = CATEGORY_ICONS.get(block["category"], "⬜")
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
                    {_get_app_icon_svg(block['category'])}
                    <div class="tl-card-info">
                        <div class="tl-card-name">{apps_str}</div>
                        <div class="tl-card-cat">{icon} {name}</div>
                    </div>
                </div>
                {'<div class="tl-card-sub">' + subtitle + '</div>' if subtitle else ''}
            </div>
            <div class="tl-card-duration">{duration_min}m</div>
        </div>"""

    if len(timeline) - len(filtered) > 0:
        hidden = len(timeline) - len(filtered)
        html += f'<div style="text-align:center;padding:8px;color:rgba(255,255,255,0.25);font-size:12px;">还有 {hidden} 个短块（<1分钟）已折叠</div>'

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
