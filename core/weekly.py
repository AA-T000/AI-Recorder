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
    weekly_data = analyze_week(7)

    if not weekly_data.get("trend"):
        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "weekly_data": weekly_data,
            "ai_report": None,
            "success": False,
            "error": "没有足够的数据生成周报",
        }

    # 构建周报数据供 AI 使用
    week_summary = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_days": weekly_data["total_days"],
        "total_hours": weekly_data["total_seconds"] // 3600,
        "total_minutes": weekly_data["total_seconds"] // 60,
        "avg_daily_minutes": weekly_data["avg_daily_seconds"] // 60,
        "total_records": weekly_data["total_records"],
        "overall_categories": weekly_data["overall_categories"],
        "trend": [],
    }

    for day in weekly_data.get("trend", []):
        day_total_mins = day["total_seconds"] // 60
        day_h = day_total_mins // 60
        day_m = day_total_mins % 60
        day_str = f"{day['date']} 共 {day_total_mins}分钟"
        if day_h > 0:
            day_str = f"{day['date']} 共 {day_h}小时{day_m}分钟"

        # 找当天最高效的分类
        if day.get("categories"):
            top_cat = max(day["categories"], key=lambda c: c.get("total_seconds", 0))
            top_cat_name = CATEGORY_NAMES.get(top_cat["category"], top_cat["category"])
            day_str += f"，主力：{top_cat_name}"
        week_summary["trend"].append(day_str)

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
        trend_str = "\n".join(week_summary["trend"])

        prompt = f"""你是一个个人成长复盘助手。根据以下一周的工作数据，生成一份中文周报。

## 周期
{week_summary['start_date']} ~ {week_summary['end_date']}

## 概览
- 总工作时长: {week_summary['total_minutes']}分钟（约{week_summary['total_hours']}小时）
- 日均时长: {week_summary['avg_daily_minutes']}分钟
- 记录总数: {week_summary['total_records']}

## 本周趋势
{trend_str}

## 分类占比
{categories_str}

请严格按照以下格式输出：

### 📋 本周概览
用 2-3 句话概括本周整体工作状态

### 🖥️ 本周应用 TOP 5
列出使用最多的 5 个应用（如果有数据），格式：
**应用名** · 使用时长：XX 分钟 · 主要用途：XXX

### 🔍 效率洞察
给出 1-2 条核心洞察（如"周三效率最高"、"工作日 vs 周末差异"等）

### 💡 下周建议
给出 2-3 条具体可行的改进建议

### 📈 一句话总结
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
            timeout=60,
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
        content = f"# 📊 周报 {start_date} ~ {end_date}\n\n> ⚠️ 生成失败: {error}\n"
    else:
        content = f"# 📊 周报 {start_date} ~ {end_date}\n\n"

        # 概览
        content += f"**总时长**: {_seconds_to_hm(report_data.get('total_seconds', 0))}  "
        content += f"**日均**: {_seconds_to_hm(report_data.get('avg_daily_seconds', 0))}  "
        content += f"**记录数**: {report_data.get('total_records', 0)}\n\n"

        # 每日趋势
        content += "## 📅 每日趋势\n\n"
        for day in report_data.get("trend", []):
            content += f"- {day}\n"
        content += "\n"

        # 分类占比
        content += "## 📊 分类占比\n\n"
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
                if stripped.startswith("#") and not re.match(r'^📋|🖥️|🔍|💡|📈', stripped):
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
                "本周概览": "## 📋 本周概览",
                "应用 TOP": "## 🖥️ 应用 TOP",
                "效率洞察": "## 🔍 效率洞察",
                "下周建议": "## 💡 下周建议",
                "一句话总结": "## 📌 总结",
            }
            for kw, title in titles.items():
                if kw in sections:
                    content += f"{title}\n\n{sections[kw]}\n\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath


def save_weekly_html_report(report_data: dict, start_date: Optional[date] = None) -> Optional[str]:
    """保存周报为 HTML 文件。"""
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
    trend_dates = [d.split(" ")[0] for d in report_data.get("trend", [])]
    trend_hours = []
    for day_str in report_data.get("trend", []):
        # 解析 "2026-07-06 共 XX小时XX分钟"
        import re
        match = re.search(r'共 (\d+)小时(\d+)分钟', day_str)
        if match:
            hours = int(match.group(1)) + int(match.group(2)) / 60
            trend_hours.append(round(hours, 1))
        else:
            trend_hours.append(0)

    # 分类占比
    pie_data = []
    for cat in report_data.get("overall_categories", []):
        pie_data.append({
            "name": cat["name"],
            "value": cat["total_seconds"] // 60,
            "itemStyle": {"color": _get_category_color(cat["category"])}
        })

    chart_json = json.dumps({
        "pie_data": pie_data,
        "trend_dates": trend_dates,
        "trend_hours": trend_hours,
    }, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📊 周报 {start_date} ~ {end_date} — AI Recorder</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0a0a1a;
    color: #e5e5e5;
}}
.container {{
    max-width: 900px;
    margin: 0 auto;
    padding: 40px 24px 80px;
}}
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

.overview-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin: 24px 0;
}}
.overview-card {{
    background: rgba(255,255,255,0.04);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 14px;
    padding: 20px 16px;
    text-align: center;
}}
.overview-card .label {{ font-size: 11px; color: rgba(255,255,255,0.35); text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 8px; }}
.overview-card .value {{ font-size: 28px; font-weight: 700; color: #f0f0f0; }}

.section {{ margin: 32px 0; }}
.section-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }}
.section-icon {{ width: 28px; height: 28px; background: linear-gradient(135deg, rgba(96,165,250,0.2), rgba(167,139,250,0.2)); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 14px; }}
.section-title {{ font-size: 17px; font-weight: 600; color: rgba(255,255,255,0.8); }}

.chart-card {{
    background: rgba(255,255,255,0.03);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 16px;
    padding: 20px;
    margin: 16px 0;
}}
.chart-container {{ width: 100%; height: 300px; }}

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

.footer {{ text-align: center; padding: 40px 0 20px; color: rgba(255,255,255,0.15); font-size: 12px; }}

@media (max-width: 640px) {{
    .container {{ padding: 24px 16px 60px; }}
    .overview-grid {{ grid-template-columns: 1fr; }}
    .overview-card .value {{ font-size: 22px; }}
}}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>📊 周报 {start_date} ~ {end_date}</h1>
        <p class="subtitle">AI Recorder · 自动生成</p>
    </div>

    <div class="overview-grid">
        <div class="overview-card">
            <div class="label">总时长</div>
            <div class="value">{report_data.get('total_hours', 0)}h</div>
        </div>
        <div class="overview-card">
            <div class="label">日均</div>
            <div class="value">{report_data.get('avg_daily_seconds', 0)//60}m</div>
        </div>
        <div class="overview-card">
            <div class="label">记录数</div>
            <div class="value">{report_data.get('total_records', 0)}</div>
        </div>
    </div>

    <div class="section">
        <div class="section-header">
            <div class="section-icon">📅</div>
            <div class="section-title">每日趋势</div>
        </div>
        {''.join(f'''
        <div class="trend-item">
            <span class="trend-date">{d}</span>
            <div class="trend-bar"><div class="trend-fill" style="width:{max(h/8*100, 1)}%"></div></div>
            <span class="trend-value">{h}h</span>
        </div>''' for d, h in zip(trend_dates, trend_hours))}
    </div>

    <div class="section">
        <div class="section-header">
            <div class="section-icon">📊</div>
            <div class="section-title">分类占比</div>
        </div>
        <div class="chart-card">
            <div id="chart-weekly-pie" class="chart-container"></div>
        </div>
    </div>

    <div class="section">
        <div class="section-header">
            <div class="section-icon">📈</div>
            <div class="section-title">每日工作时长趋势</div>
        </div>
        <div class="chart-card">
            <div id="chart-weekly-trend" class="chart-container"></div>
        </div>
    </div>

    {f'<div class="section"><div class="section-header"><div class="section-icon">🤖</div><div class="section-title">AI 分析</div></div><div class="ai-section">{ai_report}</div></div>' if ai_report else ''}

    <div class="footer">AI Recorder · 你的智能工作伙伴</div>
</div>

<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<script>
var chartData = {chart_json};

// 饼图
var pieChart = echarts.init(document.getElementById('chart-weekly-pie'));
pieChart.setOption({{
    tooltip: {{ trigger: 'item', formatter: '{{b}}: {{c}}分钟 ({{d}}%)' }},
    series: [{{
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['50%', '55%'],
        itemStyle: {{ borderRadius: 6, borderColor: '#000', borderWidth: 2 }},
        label: {{ show: true, position: 'outside', formatter: '{{b}}\\n{{d}}%', color: 'rgba(255,255,255,0.6)', fontSize: 11 }},
        labelLine: {{ lineStyle: {{ color: 'rgba(255,255,255,0.2)' }} }},
        data: chartData.pie_data
    }}]
}});

// 趋势折线图
var trendChart = echarts.init(document.getElementById('chart-weekly-trend'));
trendChart.setOption({{
    tooltip: {{ trigger: 'axis' }},
    grid: {{ left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true }},
    xAxis: {{
        type: 'category',
        data: chartData.trend_dates,
        axisLabel: {{ color: 'rgba(255,255,255,0.4)', fontSize: 11 }},
        axisLine: {{ lineStyle: {{ color: 'rgba(255,255,255,0.1)' }} }},
        axisTick: {{ show: false }}
    }},
    yAxis: {{
        type: 'value',
        name: '小时',
        nameTextStyle: {{ color: 'rgba(255,255,255,0.3)', fontSize: 10 }},
        axisLabel: {{ color: 'rgba(255,255,255,0.4)' }},
        splitLine: {{ lineStyle: {{ color: 'rgba(255,255,255,0.05)' }} }},
        axisLine: {{ show: false }},
        axisTick: {{ show: false }}
    }},
    series: [{{
        name: '工作时长',
        type: 'line',
        data: chartData.trend_hours,
        smooth: true,
        symbol: 'circle',
        symbolSize: 8,
        lineStyle: {{ color: '#60a5fa', width: 2 }},
        itemStyle: {{ color: '#60a5fa' }},
        areaStyle: {{
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                {{ offset: 0, color: 'rgba(96,165,250,0.3)' }},
                {{ offset: 1, color: 'rgba(96,165,250,0.02)' }}
            ])
        }}
    }}]
}});

window.addEventListener('resize', function() {{
    pieChart.resize();
    trendChart.resize();
}});
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
        "other": "#6b7280",
    }
    return colors.get(category, "#6b7280")
