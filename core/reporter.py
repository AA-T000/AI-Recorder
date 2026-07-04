"""AI 日报生成器 — 将本地分析结果发送给 Agnes API，生成智能日报。"""

import json
import logging
from datetime import date
from typing import Optional

import requests

from config.settings import load_settings
from core.analyzer import analyze_day

logger = logging.getLogger(__name__)


def _build_prompt(analysis: dict, settings: dict) -> str:
    """构建发送给 AI 的 prompt。"""
    ai_cfg = settings.get("ai", {})
    model = ai_cfg.get("model", "agnes-4.8-1m")

    # 构建简洁的分析数据
    timeline_items = []
    for block in analysis.get("timeline", [])[:30]:  # 最多30个块
        start = block["start"].strftime("%H:%M")
        duration_min = block.get("duration", 0) // 60
        icon = _get_icon(block["category"])
        name = _get_category_name(block["category"])
        app = block["app"]
        timeline_items.append(f"- {start} ({duration_min}min) {icon} {app} — {name}")

    categories = []
    for cat in analysis.get("category_stats", []):
        categories.append(f"- {cat['icon']} {cat['name']}: {cat['percentage']}% ({cat['seconds']//60}分钟)")

    holes = []
    for hole in analysis.get("holes", []):
        holes.append(f"- [{hole['severity']}] {hole['title']}: {hole['detail']}")

    prompt = f"""你是一个工作效率分析助手。根据以下本地分析数据，生成一份中文日报。

## 日期
{analysis['date']}

## 工作时长
最早活动: {analysis.get('earliest', '?')}
最晚活动: {analysis.get('latest', '?')}
总工作时长: {analysis.get('work_duration', 0) // 60} 分钟
记录数: {analysis.get('record_count', 0)}

## 时间分布
{chr(10).join(categories) if categories else '- 暂无数据'}

## 时间线（前30个块）
{chr(10).join(timeline_items) if timeline_items else '- 暂无数据'}

## 时间黑洞检测
{chr(10).join(holes) if holes else '- 未发现明显的时间黑洞'}

## 效率评分
{analysis.get('efficiency', 0)} / 100

请按以下格式生成日报：

### 📋 今日工作清单
按时间顺序列出主要活动（合并同类项，不要列太细）

### ⏰ 时间分布
用文字描述各主要类别的占比

### 🔍 时间黑洞报告
指出具体的时间浪费模式，给出原因

### 💡 效率建议
给出 2-3 条具体可行的改进建议

### 📈 一句话总结
用一句话概括今天的工作状态

注意：
- 语气自然，像一个聪明的同事在给你反馈
- 不要编造数据，只基于提供的数据进行分析
- 如果数据太少（少于3条记录），如实说明"""

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
            timeout=60,
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
