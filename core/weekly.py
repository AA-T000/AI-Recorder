"""周报生成器 — 基于 analyze_week 数据生成 Markdown + HTML 周报。"""

import os
import json
from datetime import date, timedelta
from typing import Optional

from config.settings import REPORTS_DIR
from core.analyzer import analyze_week, CATEGORY_NAMES, CATEGORY_ICONS, _seconds_to_hm


def generate_week_report(start_date: date, end_date: date) -> dict:
    """生成一周的周报。

    Args:
        start_date: 周一日期
        end_date: 周日日期

    Returns:
        {
            "start_date": "2026-07-06",
            "end_date": "2026-07-12",
            "weekly_data": {...},  # analyze_week 的结果
            "ai_report": "...",
            "success": True/False,
            "error": "..."
        }
    """
    from config.settings import load_settings
    from core.reporter import _clean_app_name_for_ai

    settings = load_settings()

    # 按指定日期范围查询数据，而不是固定查最近7天
    from storage.database import get_records_range
    from core.analyzer import analyze_day, build_coalesced_timeline, detect_boreholes, calculate_efficiency, CATEGORY_NAMES, CATEGORY_ICONS
    from datetime import timedelta

    trend = []
    overall_categories = {}
    total_seconds = 0
    total_records = 0
    current = start_date
    while current <= end_date:
        day_analysis = analyze_day(current, settings)
        if day_analysis.get("has_data"):
            # 使用 total_actual_seconds（合并后的 timeline 总秒数）
            day_total = day_analysis.get("total_actual_seconds", 0)
            total_seconds += day_total
            total_records += day_analysis.get("record_count", 0)
            trend.append({
                "date": current.isoformat(),
                "total_seconds": day_total,
                "record_count": day_analysis.get("record_count", 0),
                "categories": day_analysis.get("category_stats", []),
            })
            # 从 category_stats 累计分类秒数
            for cat in day_analysis.get("category_stats", []):
                c = cat["category"]
                s = cat["seconds"]
                overall_categories[c] = overall_categories.get(c, 0) + s
        current += timedelta(days=1)

    if not trend:
        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "weekly_data": {},
            "ai_report": None,
            "success": False,
            "error": "该日期范围内没有数据",
        }

    # 计算整体分类占比
    grand_total = sum(overall_categories.values())
    overall_cats = []
    for cat, secs in sorted(overall_categories.items(), key=lambda x: x[1], reverse=True):
        overall_cats.append({
            "category": cat,
            "name": CATEGORY_NAMES.get(cat, cat),
            "icon": CATEGORY_ICONS.get(cat, "·"),
            "total_seconds": secs,
            "percentage": round(secs / grand_total * 100, 1) if grand_total > 0 else 0,
        })

    total_days = len(trend)
    avg_daily = total_seconds // total_days if total_days > 0 else 0

    week_summary = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_days": total_days,
        "total_seconds": total_seconds,
        "total_records": total_records,
        "avg_daily_seconds": avg_daily,
        "overall_categories": overall_cats,
        "trend": trend,
    }

    # 调用 AI 生成周报摘要
    try:
        ai_cfg = settings.get("ai", {})
        api_base = ai_cfg.get("api_base", "")
        api_key = ai_cfg.get("api_key", "")

        if not api_base:
            return {**week_summary, "ai_report": None, "success": False, "error": "未配置 AI API"}

        # 构建周报 prompt
        categories_str = "\n".join(
            f"- {c['icon']} {c['name']}: {c['percentage']}% ({c['total_seconds']//60}分钟)"
            for c in week_summary["overall_categories"]
        )
        trend_str = "\n".join(
            f"- {d['date']}: {d['total_seconds']//60}分钟"
            for d in week_summary["trend"]
        )

        prompt = f"""你是一个个人成长复盘助手。根据以下一周的工作数据，生成一份中文周报。

## 周期
{week_summary['start_date']} ~ {week_summary['end_date']}

## 概览
- 总工作时长: {week_summary['total_seconds']//60}分钟（约{week_summary['total_seconds']//3600}小时）
- 日均时长: {week_summary['avg_daily_seconds']//60}分钟
- 记录总数: {week_summary['total_records']}

## 本周趋势
{trend_str}

## 分类占比
{categories_str}

请严格按照以下格式输出：

### 本周概览
用 2-3 句话概括本周整体工作状态

### 应用 TOP 5
列出使用最多的 5 个应用（如果有数据），格式：
**应用名** · 使用时长：XX 分钟 · 主要用途：XXX

### 效率洞察
给出 1-2 条核心洞察（如"周三效率最高"、"工作日 vs 周末差异"等）

### 下周建议
给出 2-3 条具体可行的改进建议

### 一句话总结
用一句话概括本周的工作状态
"""

        import requests
        payload = {
            "model": ai_cfg.get("model", "agnes-2.0-flash"),
            "messages": [{"role": "user", "content": prompt}],
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

        return {**week_summary, "ai_report": ai_report, "success": True}

    except Exception as e:
        return {**week_summary, "ai_report": None, "success": False, "error": str(e)}


def save_weekly_markdown_report(report_data: dict, start_date: Optional[date] = None) -> Optional[str]:
    """保存周报为 Markdown 文件。"""
    if start_date is None:
        start_date = date.fromisoformat(report_data.get("start_date", date.today().isoformat()))

    end_date = date.fromisoformat(report_data.get("end_date", date.today().isoformat()))
    os.makedirs(REPORTS_DIR, exist_ok=True)
    filepath = os.path.join(REPORTS_DIR, f"week-{start_date.isoformat()}.md")

    weekly_data = report_data.get("weekly_data", {})
    ai_report = report_data.get("ai_report", "")
    success = report_data.get("success", False)
    error = report_data.get("error", "")

    if not success:
        content = f"# 周报 {start_date} ~ {end_date}\n\n> 生成失败: {error}\n"
    else:
        content = f"# 周报 {start_date} ~ {end_date}\n\n"

        # 概览
        content += f"**总时长**: {_seconds_to_hm(report_data.get('total_seconds', 0))}  "
        content += f"**日均**: {_seconds_to_hm(report_data.get('avg_daily_seconds', 0))}  "
        content += f"**记录数**: {report_data.get('total_records', 0)}\n\n"

        # 每日趋势
        content += "## 每日趋势\n\n"
        for d in report_data.get("trend", []):
            secs = d["total_seconds"]
            h = secs // 3600
            m = (secs % 3600) // 60
            if h > 0:
                content += f"- {d['date']}: {h}小时{m}分钟\n"
            else:
                content += f"- {d['date']}: {m}分钟\n"
        content += "\n"

        # 分类占比
        content += "## 分类占比\n\n"
        for cat in report_data.get("overall_categories", []):
            mins = cat["total_seconds"] // 60
            content += f"- {cat['icon']} {cat['name']}: {cat['percentage']}% ({mins}分钟)\n"
        content += "\n"

        # AI 报告解析
        if ai_report:
            import re
            # 过滤 AI 自带的标题前缀
            cleaned_lines = []
            for line in ai_report.split("\n"):
                stripped = line.strip()
                if stripped.startswith("#") and not re.match(r'^本周概览|^应用 TOP|^效率洞察|^下周建议|^一句话总结', stripped):
                    continue
                if stripped.startswith("### "):
                    stripped = stripped[4:]
                cleaned_lines.append(stripped)
            ai_report = "\n".join(cleaned_lines)

            section_keywords = ["本周概览", "应用 TOP", "效率洞察", "下周建议", "一句话总结"]
            sections = {}
            current_section = None
            current_lines = []

            for line in ai_report.split("\n"):
                found = None
                for kw in section_keywords:
                    if kw in line.strip():
                        found = kw
                        break
                if found:
                    if current_section:
                        sections[current_section] = "\n".join(current_lines).strip()
                    current_section = found
                    current_lines = []
                else:
                    current_lines.append(line)
            if current_section:
                sections[current_section] = "\n".join(current_lines).strip()

            titles = {
                "本周概览": "## 本周概览",
                "应用 TOP": "## 应用 TOP",
                "效率洞察": "## 效率洞察",
                "下周建议": "## 下周建议",
                "一句话总结": "## 总结",
            }
            for kw, title in titles.items():
                if kw in sections:
                    content += f"{title}\n\n{sections[kw]}\n\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath


def save_weekly_html_report(report_data: dict, start_date: Optional[date] = None) -> Optional[str]:
    """保存周报为 HTML 文件 — 紫粉流光仪表盘风格。"""
    if start_date is None:
        start_date = date.fromisoformat(report_data.get("start_date", date.today().isoformat()))

    end_date = date.fromisoformat(report_data.get("end_date", date.today().isoformat()))
    os.makedirs(REPORTS_DIR, exist_ok=True)
    filepath = os.path.join(REPORTS_DIR, f"week-dashboard-{start_date.isoformat()}.html")

    success = report_data.get("success", False)
    error = report_data.get("error", "")
    ai_report_raw = report_data.get("ai_report", "")

    # 复用 markdown.py 的清洗函数
    from output.markdown import _parse_and_render_ai_report
    ai_report = _parse_and_render_ai_report(ai_report_raw) if ai_report_raw else ""

    # 每日趋势数据
    trend_dates = [d["date"] for d in report_data.get("trend", [])]
    trend_hours = [round(d["total_seconds"] / 3600, 1) for d in report_data.get("trend", [])]
    max_hours = max(trend_hours) if trend_hours else 1

    # 分类占比
    pie_data = []
    for cat in report_data.get("overall_categories", []):
        pie_data.append({
            "name": cat["name"],
            "value": cat["total_seconds"] // 60,
            "itemStyle": {"color": _get_category_color(cat["category"])}
        })

    # 分类条形图 HTML（按百分比，与日报仪表盘风格一致）
    categories_bars_html = ""
    for cat in report_data.get("overall_categories", []):
        color = _get_category_color(cat["category"])
        pct = cat["percentage"]
        mins = cat["total_seconds"] // 60
        name = cat.get("name", cat["category"])
        _bar = (
            '        <div class="cat-bar">\n'
            '            <span class="cat-name"><span class="cat-dot" style="background:{color}"></span>{name}</span>\n'
            '            <div class="bar-track">\n'
            '                <div class="bar-fill" style="width:{pct:.1f}%;background:linear-gradient(90deg,{color}cc,{color})"></div>\n'
            '            </div>\n'
            '            <span class="cat-val">{pct:.1f}% ({mins}min)</span>\n'
            '        </div>\n'
        )
        categories_bars_html += _bar.format(color=color, name=name, pct=pct, mins=mins)

    # 每日分类占比（堆叠柱状图数据）
    daily_cat_series = []
    daily_cat_names = set()
    daily_dates = []
    for d in report_data.get("trend", []):
        daily_dates.append(d["date"])
        for cat in d.get("categories", []):
            cname = cat["category"]
            daily_cat_names.add(cname)
        daily_cat_series.append({
            "date": d["date"],
            "categories": {c["category"]: c["seconds"] for c in d.get("categories", [])}
        })

    # 每日效率评分
    from core.analyzer import analyze_day
    from config.settings import load_settings
    settings = load_settings()
    daily_efficiencies = []
    for d in report_data.get("trend", []):
        day_result = analyze_day(date.fromisoformat(d["date"]), settings)
        daily_efficiencies.append(day_result.get("efficiency", 0))

    chart_json = json.dumps({
        "pie_data": pie_data,
        "trend_dates": trend_dates,
        "trend_hours": trend_hours,
        "daily_cat_series": daily_cat_series,
        "daily_cat_names": list(daily_cat_names),
        "daily_efficiencies": daily_efficiencies,
        "daily_dates": daily_dates,
    }, ensure_ascii=False)

    total_hours_val = report_data.get('total_seconds', 0) // 3600
    avg_mins_val = report_data.get('avg_daily_seconds', 0) // 60

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📊 周报 {start_date} ~ {end_date} — AI Recorder</title>
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
}}

/* ===== 主内容区 ===== */
.container {{
    max-width: 900px;
    margin: 0 auto;
    padding: 40px 32px 80px;
}}

/* ===== 头部 ===== */
.header {{ margin-bottom: 32px; text-align: center; }}
.header h1 {{
    font-size: 28px;
    font-weight: 800;
    background: linear-gradient(135deg, #60a5fa, #a78bfa, #f472b6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}}
.header .subtitle {{ color: rgba(255,255,255,0.3); font-size: 13px; margin-top: 6px; }}

/* ===== 统计网格 ===== */
.stats-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin: 24px 0 36px;
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
.section {{ margin: 32px 0; }}
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
.chart-container {{ width: 100%; height: 300px; }}
.chart-caption {{
    font-size: 13px;
    color: rgba(255,255,255,0.5);
    margin-bottom: 12px;
}}

/* ===== 分类占比条 ===== */
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
    flex-shrink: 0;
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
    flex-shrink: 0;
}}

/* ===== 趋势条 ===== */
.trend-item {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 16px;
    margin: 4px 0;
    border-radius: 10px;
    font-size: 13px;
    background: rgba(255,255,255,0.02);
}}
.trend-date {{ color: rgba(255,255,255,0.5); width: 100px; font-size: 12px; }}
.trend-bar {{ flex: 1; height: 24px; background: rgba(255,255,255,0.04); border-radius: 6px; overflow: hidden; }}
.trend-fill {{ height: 100%; background: linear-gradient(90deg, #60a5fa, #a78bfa); border-radius: 6px; transition: width 1s ease; }}
.trend-value {{ color: rgba(255,255,255,0.4); width: 60px; text-align: right; font-size: 12px; }}

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

/* ===== 页脚 ===== */
.footer {{ text-align: center; padding: 40px 0 20px; color: rgba(255,255,255,0.15); font-size: 12px; letter-spacing: 1px; }}

/* ===== 响应式 ===== */
@media (max-width: 640px) {{
    .container {{ padding: 24px 16px 60px; }}
    .stats-grid {{ grid-template-columns: 1fr; }}
    .stat-card .value {{ font-size: 20px; }}
    .chart-container {{ height: 240px; }}
    .trend-date {{ width: 60px; font-size: 10px; }}
}}
</style>
</head>
<body>

<!-- WebGL 流光背景 -->
<div id="wgsl-bg"></div>

<div class="page-overlay">
<div class="container">

    <div class="header">
        <h1>📊 周报 {start_date} ~ {end_date}</h1>
        <p class="subtitle">AI Recorder · 自动生成</p>
    </div>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="label">总时长</div>
            <div class="value">{total_hours_val}h</div>
        </div>
        <div class="stat-card">
            <div class="label">日均</div>
            <div class="value">{avg_mins_val}m</div>
        </div>
        <div class="stat-card">
            <div class="label">记录数</div>
            <div class="value">{report_data.get('total_records', 0)}</div>
        </div>
    </div>

    <!-- ===== 1. 每日趋势 ===== -->
    <div class="section">
        <div class="section-header">
            <div class="section-icon">📅</div>
            <div class="section-title">每日趋势</div>
        </div>
        {''.join(f'''
        <div class="trend-item">
            <span class="trend-date">{d}</span>
            <div class="trend-bar"><div class="trend-fill" style="width:{max(h/max_hours*100, 1):.0f}%"></div></div>
            <span class="trend-value">{h}h</span>
        </div>''' for d, h in zip(trend_dates, trend_hours))}
    </div>

    <!-- ===== 2. 分类占比 ===== -->
    <div class="section">
        <div class="section-header">
            <div class="section-icon">📊</div>
            <div class="section-title">分类占比</div>
        </div>
        <div class="chart-card">
            <div class="chart-caption">时间分布</div>
            <div id="chart-weekly-pie" class="chart-container"></div>
        </div>
        <!-- 分类条形图（按百分比） -->
        {categories_bars_html}
    </div>

    <!-- ===== 3. 每日工作时长 ===== -->
    <div class="section">
        <div class="section-header">
            <div class="section-icon">📈</div>
            <div class="section-title">每日工作时长</div>
        </div>
        <div class="chart-card">
            <div class="chart-caption">小时趋势</div>
            <div id="chart-weekly-trend" class="chart-container"></div>
        </div>
    </div>

    <!-- ===== 4. 分类趋势对比 ===== -->
    <div class="section">
        <div class="section-header">
            <div class="section-icon">📊</div>
            <div class="section-title">每日分类对比</div>
        </div>
        <div class="chart-card">
            <div class="chart-caption">每天各分类时长（分钟）</div>
            <div id="chart-weekly-cat-stack" class="chart-container"></div>
        </div>
    </div>

    <!-- ===== 5. 效率排名 ===== -->
    <div class="section">
        <div class="section-header">
            <div class="section-icon">🏆</div>
            <div class="section-title">每日效率评分</div>
        </div>
        <div class="chart-card">
            <div class="chart-caption">效率评分 0-100</div>
            <div id="chart-weekly-efficiency" class="chart-container" style="height:250px;"></div>
        </div>
    </div>

    <!-- ===== 6. AI 分析 ===== -->
    {f'<div class="section"><div class="section-header"><div class="section-icon">🤖</div><div class="section-title">AI 分析</div></div><div class="ai-section">{ai_report}</div></div>' if ai_report else ''}

    <div class="footer">AI Recorder · 你的智能工作伙伴</div>

</div>
</div>

<!-- ECharts CDN -->
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>

<script>
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
    var colors = [[0.65,0.78,1.0],[0.32,0.15,1.0],[1.0,0.63,0.98]];
    var bgColor = [0.04,0.02,0.12];
    var canvas = document.createElement('canvas');
    container.appendChild(canvas);
    var gl = canvas.getContext('webgl',{{alpha:true,antialias:!isLowEnd}});
    if(!gl){{canvas.style.display='none';container.style.background='linear-gradient(135deg,#0a0a2e 0%,#1a0a2e 50%,#0a1a2e 100%)';return;}}
    var vertSrc=`attribute vec2 position;attribute vec2 uv;varying vec2 vUv;void main(){{vUv=uv;gl_Position=vec4(position,0.0,1.0);}}`;
    var fragSrc=`precision highp float;uniform vec3 iResolution;uniform vec2 iMouse;uniform float iTime;uniform vec3 uColor0;uniform vec3 uColor1;uniform vec3 uColor2;uniform vec3 uBgColor;uniform float uSpeed;uniform int uStreakCount;uniform float uStreakWidth;uniform float uStreakLength;uniform float uGlow;uniform float uDensity;uniform float uTwinkle;uniform float uZoom;uniform float uBgGlow;uniform float uMouseEnabled;uniform float uMouseStrength;uniform float uMouseRadius;varying vec2 vUv;vec3 palette(float h){{if(h<0.333)return uColor0;if(h<0.666)return uColor1;return uColor2;}}vec3 tanhv(vec3 x){{vec3 e=exp(-2.0*x);return(1.0-e)/(1.0+e);}}vec2 sceneC(vec2 frag,vec2 r){{vec2 P=(frag+frag-r)/r.x;float z=0.0;float d=1e3;vec4 O=vec4(0.0);for(int k=0;k<39;k++){{if(d<=1e-4)break;O=z*normalize(vec4(P,uZoom,0.0))-vec4(0.0,4.0,1.0,0.0)/4.5;d=1.0-sqrt(length(O*O));z+=d;}}return vec2(O.x,atan(O.z,O.y));}}void mainImage(out vec4 o,vec2 C){{vec2 r=iResolution.xy;vec2 uv0=(C+C-r)/r.x;float T=0.1*iTime*uSpeed+9.0;float angRings=max(1.0,floor(6.28318530718*max(uDensity,0.05)+0.5));vec2 Y=vec2(5e-3,6.28318530718/angRings);vec2 c0=sceneC(C,r);vec2 cdx=sceneC(C+vec2(1.0,0.0),r);vec2 cdy=sceneC(C+vec2(0.0,1.0),r);vec2 dCx=cdx-c0;vec2 dCy=cdy-c0;dCx.y-=6.28318530718*floor(dCx.y/6.28318530718+0.5);dCy.y-=6.28318530718*floor(dCy.y/6.28318530718+0.5);vec2 fw=abs(dCx)+abs(dCy);C=c0;vec2 P=vec2(2.0,1.0)*uv0-(r/r.x)*vec2(0.0,1.0);vec4 O=vec4(uBgColor*90.0*uBgGlow/(1e3*dot(P,P)+6.0),0.0);float mGlow=0.0;if(uMouseEnabled>0.5){{vec2 mN=(iMouse+iMouse-r)/r.x;float md=length(uv0-mN);mGlow=exp(-md*md/max(uMouseRadius*uMouseRadius,1e-4))*uMouseStrength;O.rgb+=uColor0*mGlow*0.25;}}float zr=5e-4*uStreakWidth;vec2 rr=vec2(max(length(fw),1e-5));float tail=19.0/max(uStreakLength,0.05);for(int m=0;m<16;m++){{if(m>=uStreakCount)break;float jf=float(m)+1.0;float ic=fract(sin(dot(vec2(jf,floor(C.x/Y.x+0.5)),vec2(7.0,11.0))*73.0));vec2 Pp=C-(T+T*ic)*vec2(0.0,1.0);Pp-=floor(Pp/Y+0.5)*Y;float h=fract(8663.0*ic);vec3 col=palette(h);float weight=mix(1.5,1.0+sin(T+7.0*h+4.0),uTwinkle);weight*=(1.0+mGlow*2.0);vec2 inner=vec2(length(max(Pp,vec2(-1.0,0.0))),length(Pp)-zr)-zr;vec2 sm=vec2(1.0)-smoothstep(-rr,rr,inner);O.rgb+=dot(sm,vec2(exp(tail*Pp.y),3.0))*col*weight;C.x+=Y.x/8.0;}}vec3 colr=sqrt(tanhv(max(O.rgb*uGlow-vec3(0.04,0.08,0.02),0.0)));o=vec4(colr,1.0);}}void main(){{vec4 color;mainImage(color,vUv*iResolution.xy);gl_FragColor=color;}}`;
    function compileShader(src,type){{var s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS)){{console.warn('Shader compile failed:',gl.getShaderInfoLog(s));return null;}}return s;}}
    var vert=compileShader(vertSrc,gl.VERTEX_SHADER),frag=compileShader(fragSrc,gl.FRAGMENT_SHADER);
    if(!vert||!frag){{container.style.background='linear-gradient(135deg,#0a0a2e 0%,#1a0a2e 50%,#0a1a2e 100%)';return;}}
    var prog=gl.createProgram();gl.attachShader(prog,vert);gl.attachShader(prog,frag);gl.linkProgram(prog);
    if(!gl.getProgramParameter(prog,gl.LINK_STATUS)){{container.style.background='linear-gradient(135deg,#0a0a2e 0%,#1a0a2e 50%,#0a1a2e 100%)';return;}}
    gl.useProgram(prog);
    var pos=new Float32Array([-1,-1,1,-1,-1,1,1,1]),uv=new Float32Array([0,0,1,0,0,1,1,1]);
    var posBuf=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,posBuf);gl.bufferData(gl.ARRAY_BUFFER,pos,gl.STATIC_DRAW);
    var posLoc=gl.getAttribLocation(prog,'position');gl.enableVertexAttribArray(posLoc);gl.vertexAttribPointer(posLoc,2,gl.FLOAT,false,0,0);
    var uvBuf=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,uvBuf);gl.bufferData(gl.ARRAY_BUFFER,uv,gl.STATIC_DRAW);
    var uvLoc=gl.getAttribLocation(prog,'uv');gl.enableVertexAttribArray(uvLoc);gl.vertexAttribPointer(uvLoc,2,gl.FLOAT,false,0,0);
    var locs={{}};['iResolution','iMouse','iTime','uColor0','uColor1','uColor2','uBgColor','uSpeed','uStreakCount','uStreakWidth','uStreakLength','uGlow','uDensity','uTwinkle','uZoom','uBgGlow','uMouseEnabled','uMouseStrength','uMouseRadius'].forEach(function(n,i){{locs[n]=gl.getUniformLocation(prog,n);}});
    var params={{speed:0.5,streakCount:2,streakWidth:1,streakLength:1,glow:1,density:0.6,twinkle:1,zoom:3,bgGlow:0.5,mouseEnabled:1,mouseStrength:0.5,mouseRadius:1,mouseDampening:0.15}};
    var mouseTarget=[0,0],mouseCurrent=[0,0],lastTime=0;
    canvas.addEventListener('mousemove',function(e){{var r=canvas.getBoundingClientRect();mouseTarget[0]=(e.clientX-r.left)*(canvas.width/r.width);mouseTarget[1]=(r.height-(e.clientY-r.top))*(canvas.height/r.height);}});
    canvas.addEventListener('mouseleave',function(){{mouseTarget=[0,0];}});
    function resize(){{var r=container.getBoundingClientRect();var w=Math.floor(r.width*(isLowEnd?1:2)),h=Math.floor(r.height*(isLowEnd?1:2));canvas.width=w;canvas.height=h;gl.viewport(0,0,w,h);gl.uniform3f(locs.iResolution,w,h,1);}}
    resize();new ResizeObserver(resize).observe(container);
    function animate(time){{requestAnimationFrame(animate);if(time-lastTime<33)return;lastTime=time;var tau=Math.max(0.001,params.mouseDampening),dt=0.016,fa=1-Math.exp(-dt/tau);mouseCurrent[0]+=(mouseTarget[0]-mouseCurrent[0])*fa;mouseCurrent[1]+=(mouseTarget[1]-mouseCurrent[1])*fa;gl.uniform2fv(locs.iMouse,mouseCurrent);gl.uniform3fv(locs.uColor0,colors[0]);gl.uniform3fv(locs.uColor1,colors[1]);gl.uniform3fv(locs.uColor2,colors[2]);gl.uniform3fv(locs.uBgColor,bgColor);gl.uniform1f(locs.uSpeed,params.speed);gl.uniform1i(locs.uStreakCount,params.streakCount);gl.uniform1f(locs.uStreakWidth,params.streakWidth);gl.uniform1f(locs.uStreakLength,params.streakLength);gl.uniform1f(locs.uGlow,params.glow);gl.uniform1f(locs.uDensity,params.density);gl.uniform1f(locs.uTwinkle,params.twinkle);gl.uniform1f(locs.uZoom,params.zoom);gl.uniform1f(locs.uBgGlow,params.bgGlow);gl.uniform1f(locs.uMouseEnabled,params.mouseEnabled);gl.uniform1f(locs.uMouseStrength,params.mouseStrength);gl.uniform1f(locs.uMouseRadius,params.mouseRadius);gl.drawArrays(gl.TRIANGLE_STRIP,0,4);}}
    requestAnimationFrame(animate);
    document.addEventListener('visibilitychange',function(){{if(document.hidden)cancelAnimationFrame(animate);}});
}})();

// ===== ECharts 图表 =====
(function() {{
    if(typeof echarts==='undefined')return;
    var chartData={chart_json};

    // 饼图
    var pieChart=echarts.init(document.getElementById('chart-weekly-pie'),null,{{renderer:'canvas'}});
    pieChart.setOption({{
        tooltip:{{trigger:'item',formatter:'{{b}}: {{c}}分钟 ({{d}}%)'}},
        series:[{{
            type:'pie',radius:['40%','70%'],center:['50%','55%'],avoidLabelOverlap:true,
            itemStyle:{{borderRadius:6,borderColor:'#000',borderWidth:2}},
            label:{{show:true,position:'outside',formatter:'{{b}}\\n{{d}}%',color:'rgba(255,255,255,0.6)',fontSize:11}},
            labelLine:{{lineStyle:{{color:'rgba(255,255,255,0.2)'}}}},
            data:chartData.pie_data
        }}]
    }});

    // 趋势折线图
    var trendChart=echarts.init(document.getElementById('chart-weekly-trend'),null,{{renderer:'canvas'}});
    trendChart.setOption({{
        tooltip:{{trigger:'axis'}},
        grid:{{left:'3%',right:'4%',bottom:'3%',top:'10%',containLabel:true}},
        xAxis:{{type:'category',data:chartData.trend_dates,axisLabel:{{color:'rgba(255,255,255,0.4)',fontSize:11}},axisLine:{{lineStyle:{{color:'rgba(255,255,255,0.1)'}}}},axisTick:{{show:false}}}},
        yAxis:{{type:'value',name:'小时',nameTextStyle:{{color:'rgba(255,255,255,0.3)',fontSize:10}},axisLabel:{{color:'rgba(255,255,255,0.4)'}},splitLine:{{lineStyle:{{color:'rgba(255,255,255,0.05)'}}}},axisLine:{{show:false}},axisTick:{{show:false}}}},
        series:[{{
            name:'工作时长',type:'line',data:chartData.trend_hours,smooth:true,symbol:'circle',symbolSize:8,
            lineStyle:{{color:'#60a5fa',width:2}},itemStyle:{{color:'#60a5fa'}},
            areaStyle:{{color:new echarts.graphic.LinearGradient(0,0,0,1,[{{offset:0,color:'rgba(96,165,250,0.3)'}},{{offset:1,color:'rgba(96,165,250,0.02)'}}])}}
        }}]
    }});

    // 分类堆叠柱状图
    var stackChart=echarts.init(document.getElementById('chart-weekly-cat-stack'),null,{{renderer:'canvas'}});
    var stackSeries = [];
    var catColors = {{
        development:'#3b82f6', browser:'#f97316', communication:'#eab308',
        design:'#a855f7', office:'#64748b', terminal:'#22c55e',
        gaming:'#ef4444', finance:'#10b981', network:'#06b6d4',
        system:'#8b5cf6', audio:'#ec4899', other:'#6b7280'
    }};
    var catNames = {{
        development:'开发', browser:'浏览器', communication:'通讯',
        design:'设计', office:'办公', terminal:'终端',
        gaming:'游戏', finance:'金融', network:'网络',
        system:'系统工具', audio:'音频', other:'其他'
    }};
    chartData.daily_cat_names.forEach(function(cat) {{
        stackSeries.push({{
            name: catNames[cat] || cat,
            type: 'bar',
            stack: 'total',
            emphasis: {{ focus: 'series' }},
            itemStyle: {{ color: catColors[cat] || '#64748b' }},
            data: chartData.daily_cat_series.map(function(d) {{ return ((d.categories[cat] || 0) / 60).toFixed(1); }})
        }});
    }});
    stackChart.setOption({{
        tooltip:{{trigger:'axis',axisPointer:{{type:'shadow'}},formatter:function(params) {{
            var t = params[0].name;
            var lines = params.map(function(p) {{ return p.marker + p.seriesName + ': ' + parseFloat(p.value).toFixed(1) + ' 分钟'; }}).join('<br/>');
            return t + '<br/>' + lines;
        }}}},
        legend:{{show:true,textStyle:{{color:'rgba(255,255,255,0.5)',fontSize:10}},top:0}},
        grid:{{left:'3%',right:'4%',bottom:'3%',top:'15%',containLabel:true}},
        xAxis:{{type:'category',data:chartData.daily_dates,axisLabel:{{color:'rgba(255,255,255,0.4)',fontSize:11}},axisLine:{{lineStyle:{{color:'rgba(255,255,255,0.1)'}}}},axisTick:{{show:false}}}},
        yAxis:{{type:'value',name:'分钟',nameTextStyle:{{color:'rgba(255,255,255,0.3)',fontSize:10}},axisLabel:{{color:'rgba(255,255,255,0.4)'}},splitLine:{{lineStyle:{{color:'rgba(255,255,255,0.05)'}}}},axisLine:{{show:false}},axisTick:{{show:false}}}},
        series: stackSeries
    }});

    // 效率评分柱状图
    var effChart=echarts.init(document.getElementById('chart-weekly-efficiency'),null,{{renderer:'canvas'}});
    var effColors = chartData.daily_efficiencies.map(function(s) {{
        if (s >= 70) return '#22c55e';
        if (s >= 50) return '#eab308';
        if (s >= 30) return '#f97316';
        return '#ef4444';
    }});
    effChart.setOption({{
        tooltip:{{trigger:'axis',axisPointer:{{type:'shadow'}},formatter:'{{b}}<br/>效率评分: {{c}}/100'}},
        grid:{{left:'3%',right:'4%',bottom:'3%',top:'10%',containLabel:true}},
        xAxis:{{type:'category',data:chartData.daily_dates,axisLabel:{{color:'rgba(255,255,255,0.4)',fontSize:11}},axisLine:{{lineStyle:{{color:'rgba(255,255,255,0.1)'}}}},axisTick:{{show:false}}}},
        yAxis:{{type:'value',name:'评分',nameTextStyle:{{color:'rgba(255,255,255,0.3)',fontSize:10}},min:0,max:100,axisLabel:{{color:'rgba(255,255,255,0.4)'}},splitLine:{{lineStyle:{{color:'rgba(255,255,255,0.05)'}}}},axisLine:{{show:false}},axisTick:{{show:false}}}},
        series:[{{
            name:'效率评分',type:'bar',data:chartData.daily_efficiencies,
            itemStyle:{{color:function(params) {{ return effColors[params.dataIndex]; }} }},
            barWidth: '50%',
            label:{{show:true,position:'top',color:'rgba(255,255,255,0.6)',fontSize:11,formatter:'{{c}}'}}
        }}]
    }});

    window.addEventListener('resize',function(){{
        pieChart.resize(); trendChart.resize(); stackChart.resize(); effChart.resize();
    }});
}})();
</script>

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
        "gaming": "#ef4444",
        "finance": "#10b981",
        "network": "#06b6d4",
        "system": "#8b5cf6",
        "audio": "#ec4899",
        "other": "#6b7280",
    }
    return colors.get(category, "#6b7280")
