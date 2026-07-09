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


def _get_phosphor_palette(category: str) -> str:
    """磷光终端风格配色。"""
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
    return hue_shifts.get(category, "#00ff88")


def save_weekly_html_report(report_data: dict, start_date: Optional[date] = None) -> Optional[str]:
    """保存周报为 HTML 文件 — 磷光终端风。"""
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
        color = _get_phosphor_palette(cat["category"])
        pie_data.append({
            "name": cat["name"],
            "value": cat["total_seconds"] // 60,
            "itemStyle": {"color": color}
        })

    chart_json = json.dumps({
        "pie_data": pie_data,
        "trend_dates": trend_dates,
        "trend_hours": trend_hours,
    }, ensure_ascii=False)

    total_hours_val = report_data.get('total_seconds', 0) // 3600
    avg_mins_val = report_data.get('avg_daily_seconds', 0) // 60

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>周报 {start_date} ~ {end_date}</title>
<style>
/* ===== 基础 ===== */
* {{ margin:0; padding:0; box-sizing:border-box; }}

/* ===== 字体：JetBrains Mono（终端） ===== */
body {{
    font-family: 'JetBrains Mono', 'SF Mono', 'Fira Code', monospace;
    background: #0a0e0a;
    color: #c8ffc8;
    line-height: 1.6;
}}

/* ===== Grain 噪点层 ===== */
body::before {{
    content: '';
    position: fixed;
    inset: 0;
    z-index: 100;
    pointer-events: none;
    opacity: 0.03;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
    background-repeat: repeat;
    background-size: 256px 256px;
}}

/* ===== 暗角 ===== */
body::after {{
    content: '';
    position: fixed;
    inset: 0;
    z-index: 99;
    pointer-events: none;
    background: radial-gradient(ellipse at 50% 30%, transparent 50%, rgba(0,0,0,0.3) 100%);
}}

/* ===== WebGL 流光背景容器 ===== */
#bg-canvas {{
    position: fixed;
    top: 0; left: 0;
    width: 100vw; height: 100vh;
    z-index: 0;
    opacity: 0.7;
}}

/* ===== 暗角叠加层 ===== */
.page-overlay {{
    position: relative;
    z-index: 1;
    background: radial-gradient(ellipse at 50% 0%, transparent 50%, rgba(10,14,10,0.5) 80%, #0a0e0a 100%);
    min-height: 100vh;
    pointer-events: none;
}}
.page-overlay > * {{
    pointer-events: auto;
}}

/* ===== 容器 ===== */
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
    text-align: center;
}}
.header-period {{
    font-size: 11px;
    color: rgba(0,255,136,0.3);
    letter-spacing: 0.15em;
    margin-bottom: 8px;
}}
.header-title {{
    font-size: 24px;
    font-weight: 700;
    color: #e0ffe0;
    letter-spacing: -0.01em;
}}
.header-brand {{
    font-size: 11px;
    color: rgba(0,255,136,0.2);
    margin-top: 8px;
    letter-spacing: 0.1em;
}}

/* ===== 统计行 ===== */
.stats-row {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
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
    font-size: 24px;
    font-weight: 600;
    color: #d0ffd0;
    font-variant-numeric: tabular-nums;
}}

/* ===== 分区 ===== */
.section {{ margin: 36px 0; }}
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
.chart-card {{
    padding: 16px;
    border: 1px solid rgba(0,255,136,0.06);
    border-radius: 2px;
    background: rgba(0,255,136,0.01);
    margin: 16px 0;
}}
.chart-container {{ width: 100%; height: 280px; }}
.chart-caption {{
    font-size: 11px;
    color: rgba(200,255,200,0.35);
    margin-bottom: 12px;
    letter-spacing: 0.05em;
}}

/* ===== 趋势条 ===== */
.trend-item {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 0;
    font-size: 12px;
}}
.trend-date {{ color: rgba(200,255,200,0.45); width: 80px; font-size: 11px; flex-shrink: 0; }}
.trend-bar {{ flex: 1; height: 16px; background: rgba(0,255,136,0.03); border-radius: 1px; overflow: hidden; }}
.trend-fill {{ height: 100%; border-radius: 1px; transition: width 1s cubic-bezier(0.16, 1, 0.3, 1); }}
.trend-value {{ color: rgba(200,255,200,0.4); width: 50px; text-align: right; font-size: 11px; font-variant-numeric: tabular-nums; flex-shrink: 0; }}

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
@media (max-width: 640px) {{
    .wrap {{ padding: 0 16px; }}
    .header {{ padding: 32px 0 24px; }}
    .header-title {{ font-size: 20px; }}
    .stats-row {{ grid-template-columns: 1fr; }}
    .stat-item {{ padding: 12px 8px; border-right: none; border-bottom: 1px solid rgba(0,255,136,0.04); }}
    .stat-item:last-child {{ border-bottom: none; }}
    .chart-container {{ height: 240px; }}
    .trend-date {{ width: 60px; font-size: 10px; }}
}}

@media (prefers-reduced-motion: reduce) {{
    .trend-fill {{ transition: none; }}
}}
</style>
</head>
<body>
<canvas id="bg-canvas"></canvas>

<div class="page-overlay">
<div class="wrap">

    <!-- ===== 头部 ===== -->
    <div class="header">
        <div class="header-period">{start_date.strftime('%Y.%m.%d')} ~ {end_date.strftime('%Y.%m.%d')}</div>
        <div class="header-title">周报</div>
        <div class="header-brand">AI RECORDER</div>
    </div>

    <!-- ===== 统计行 ===== -->
    <div class="stats-row">
        <div class="stat-item">
            <div class="label">总时长</div>
            <div class="value">{total_hours_val}h</div>
        </div>
        <div class="stat-item">
            <div class="label">日均</div>
            <div class="value">{avg_mins_val}m</div>
        </div>
        <div class="stat-item">
            <div class="label">记录数</div>
            <div class="value">{report_data.get('total_records', 0)}</div>
        </div>
    </div>

    <!-- ===== 1. 每日趋势 ===== -->
    <div class="section">
        <div class="section-header">
            <span class="section-num">01</span>
            <span class="section-title">每日趋势</span>
        </div>
        {''.join(f'''
        <div class="trend-item">
            <span class="trend-date">{d}</span>
            <div class="trend-bar"><div class="trend-fill" style="width:{max(h/max_hours*100, 1):.0f}%;background:#00ff88;"></div></div>
            <span class="trend-value">{h}h</span>
        </div>''' for d, h in zip(trend_dates, trend_hours))}
    </div>

    <!-- ===== 2. 分类占比 ===== -->
    <div class="section">
        <div class="section-header">
            <span class="section-num">02</span>
            <span class="section-title">分类占比</span>
        </div>
        <div class="chart-card">
            <div class="chart-caption">时间分布</div>
            <div id="chart-weekly-pie" class="chart-container"></div>
        </div>
    </div>

    <!-- ===== 3. 每日工作时长 ===== -->
    <div class="section">
        <div class="section-header">
            <span class="section-num">03</span>
            <span class="section-title">每日工作时长</span>
        </div>
        <div class="chart-card">
            <div class="chart-caption">小时趋势</div>
            <div id="chart-weekly-trend" class="chart-container"></div>
        </div>
    </div>

    <!-- ===== 4. AI 分析 ===== -->
    {f'''
    <div class="section">
        <div class="section-header">
            <span class="section-num">04</span>
            <span class="section-title">AI 分析</span>
        </div>
        <div class="ai-section">{ai_report}</div>
    </div>''' if ai_report else ''}

    <div class="footer">AI RECORDER</div>

</div><!-- /.wrap -->
</div><!-- /.page-overlay -->

<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<script>
// ===== WebGL 流光背景（磷光终端绿） =====
(function() {{
    var container = document.getElementById('bg-canvas');
    if (!container) return;
    var gl = container.getContext('webgl', {{ alpha: true, antialias: false }});
    if (!gl) {{ container.style.display = 'none'; return; }}

    var colors = [[0.0,1.0,0.53],[0.2,0.8,0.4],[0.5,0.9,0.3]];
    var bgColor = [0.04,0.06,0.04];

    var vertSrc = `attribute vec2 position;attribute vec2 uv;varying vec2 vUv;void main(){{vUv=uv;gl_Position=vec4(position,0.0,1.0);}}`;
    var fragSrc = `precision highp float;uniform vec3 iResolution;uniform float iTime;uniform vec3 uColor0;uniform vec3 uColor1;uniform vec3 uColor2;uniform vec3 uBgColor;uniform float uStreakCount;uniform float uSpeed;uniform float uGlow;uniform float uDensity;uniform float uTwinkle;varying vec2 vUv;
        vec3 pal(float h){{if(h<0.333)return uColor0;if(h<0.666)return uColor1;return uColor2;}}
        void main(){{
            vec2 uv=vUv*iResolution.xy;float T=iTime*uSpeed;
            float angRings=max(1.0,floor(6.28*max(uDensity,0.05)+0.5));
            vec2 Y=vec2(0.005,6.283/angRings);
            float bgGlow=exp(-dot(uv-iResolution.xy*0.5,uv-iResolution.xy*0.5)/max(dot(iResolution.xy,iResolution.xy)*0.3,1e-4))*0.15;
            vec3 col=uBgColor+vec3(bgGlow);
            for(int m=0;m<16;m++){{if(float(m)>=uStreakCount)break;float jf=float(m)+1.0;float ic=fract(sin(dot(vec2(jf,7.0),vec2(7.0,11.0)))*73.0);float h=fract(8663.0*ic);vec3 c=pal(h);float weight=mix(1.5,1.0+sin(T+7.0*h+4.0),uTwinkle);float phase=fract((T+T*ic)/Y.y+0.5);float trail=exp(-abs(uv.y-phase*iResolution.y)/max(Y.x*iResolution.y,1.0));float fade=smoothstep(0.0,0.1,phase)*smoothstep(1.0,0.7,phase);col+=c*trail*weight*0.6*fade;}}
            gl_FragColor=vec4(col*uGlow,1.0);
        }}`;

    function cs(src,type){{var s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);return gl.getShaderParameter(s,gl.COMPILE_STATUS)?s:null;}}
    var v=cs(vertSrc,gl.VERTEX_SHADER),f=cs(fragSrc,gl.FRAGMENT_SHADER);
    if(!v||!f){{container.style.display='none';return;}}
    var p=gl.createProgram();gl.attachShader(p,v);gl.attachShader(p,f);gl.linkProgram(p);
    if(!gl.getProgramParameter(p,gl.LINK_STATUS)){{container.style.display='none';return;}}
    gl.useProgram(p);
    var pos=new Float32Array([-1,-1,1,-1,-1,1,1,1]),uv=new Float32Array([0,0,1,0,0,1,1,1]);
    var pb=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,pb);gl.bufferData(gl.ARRAY_BUFFER,pos,gl.STATIC_DRAW);
    var pl=gl.getAttribLocation(p,'position');gl.enableVertexAttribArray(pl);gl.vertexAttribPointer(pl,2,gl.FLOAT,false,0,0);
    var ub=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,ub);gl.bufferData(gl.ARRAY_BUFFER,uv,gl.STATIC_DRAW);
    var ul=gl.getAttribLocation(p,'uv');gl.enableVertexAttribArray(ul);gl.vertexAttribPointer(ul,2,gl.FLOAT,false,0,0);
    var locs={{}};['iResolution','iTime','uColor0','uColor1','uColor2','uBgColor','uStreakCount','uSpeed','uGlow','uDensity','uTwinkle'].forEach(function(n){{locs[n]=gl.getUniformLocation(p,n);}});
    var params={{speed:0.3,streakCount:3,glow:1.0,density:0.4,twinkle:0.8}};
    var lt=0;
    function resize(){{var r=container.getBoundingClientRect();var w=Math.floor(r.width*window.devicePixelRatio),h=Math.floor(r.height*window.devicePixelRatio);container.width=w;container.height=h;gl.viewport(0,0,w,h);gl.uniform3f(locs.iResolution,w,h,1);}}
    resize();new ResizeObserver(resize).observe(container);
    function animate(t){{requestAnimationFrame(animate);if(t-lt<33)return;lt=t;gl.uniform1f(locs.iTime,t*0.001);gl.uniform3fv(locs.uColor0,colors[0]);gl.uniform3fv(locs.uColor1,colors[1]);gl.uniform3fv(locs.uColor2,colors[2]);gl.uniform3fv(locs.uBgColor,bgColor);gl.uniform1f(locs.uSpeed,params.speed);gl.uniform1i(locs.uStreakCount,params.streakCount);gl.uniform1f(locs.uGlow,params.glow);gl.uniform1f(locs.uDensity,params.density);gl.uniform1f(locs.uTwinkle,params.twinkle);gl.drawArrays(gl.TRIANGLE_STRIP,0,4);}}
    requestAnimationFrame(animate);
    document.addEventListener('visibilitychange',function(){{if(document.hidden)cancelAnimationFrame(animate);}});
}})();

var chartData = {chart_json};

// 饼图
var pieChart = echarts.init(document.getElementById('chart-weekly-pie'), null, {{ renderer: 'canvas' }});
pieChart.setOption({{
    tooltip: {{ trigger: 'item', formatter: '{{b}}: {{c}}分钟 ({{d}}%)' }},
    series: [{{
        type: 'pie',
        radius: ['35%', '65%'],
        center: ['50%', '55%'],
        itemStyle: {{ borderRadius: 2, borderColor: '#0a0e0a', borderWidth: 2 }},
        label: {{ show: true, position: 'outside', formatter: '{{b}}\\n{{d}}%', color: 'rgba(200,255,200,0.5)', fontSize: 10, fontFamily: "'JetBrains Mono', monospace" }},
        labelLine: {{ lineStyle: {{ color: 'rgba(200,255,200,0.15)' }} }},
        data: chartData.pie_data
    }}]
}});

// 趋势折线图
var trendChart = echarts.init(document.getElementById('chart-weekly-trend'), null, {{ renderer: 'canvas' }});
trendChart.setOption({{
    tooltip: {{ trigger: 'axis' }},
    grid: {{ left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true }},
    xAxis: {{
        type: 'category',
        data: chartData.trend_dates,
        axisLabel: {{ color: 'rgba(200,255,200,0.3)', fontSize: 10, fontFamily: "'JetBrains Mono', monospace" }},
        axisLine: {{ lineStyle: {{ color: 'rgba(0,255,136,0.08)' }} }},
        axisTick: {{ show: false }}
    }},
    yAxis: {{
        type: 'value',
        name: '',
        axisLabel: {{ color: 'rgba(200,255,200,0.3)', fontSize: 10, fontFamily: "'JetBrains Mono', monospace" }},
        splitLine: {{ lineStyle: {{ color: 'rgba(0,255,136,0.04)' }} }},
        axisLine: {{ show: false }},
        axisTick: {{ show: false }}
    }},
    series: [{{
        name: '工作时长',
        type: 'line',
        data: chartData.trend_hours,
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: {{ color: '#00ff88', width: 2 }},
        itemStyle: {{ color: '#00ff88' }},
        areaStyle: {{
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                {{ offset: 0, color: 'rgba(0,255,136,0.15)' }},
                {{ offset: 1, color: 'rgba(0,255,136,0.01)' }}
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
