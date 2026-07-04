"""本地分析引擎 — 时间线重建、应用分类、时间黑洞检测、效率评分。"""

import logging
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional

from storage.database import get_records_by_date, get_daily_summary, get_recent_days

logger = logging.getLogger(__name__)

# 中文分类名映射
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


def _seconds_to_hm(seconds: int) -> str:
    """秒数转时:分。"""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0:
        return f"{h}h{m}m"
    return f"{m}m"


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


def build_timeline(records: List[Dict]) -> List[Dict]:
    """将原始记录合并为时间线块。

    相邻同窗口记录合并为一个块。
    """
    if not records:
        return []

    timeline = []
    current = {
        "app": records[0]["app_name"],
        "title": records[0]["window_title"],
        "category": records[0]["category"],
        "start": _parse_iso(records[0]["start_time"]),
        "end": _parse_iso(records[0]["start_time"]),
    }

    for rec in records[1:]:
        rec_start = _parse_iso(rec["start_time"])
        rec_end = _parse_iso(rec["end_time"]) if rec.get("end_time") else rec_start

        # 如果窗口相同且时间连续（间隔 <= 3 秒），合并
        if (current["app"] == rec["app_name"]
                and abs((rec_start - current["end"]).total_seconds()) <= 3):
            current["end"] = rec_end
        else:
            current["duration"] = int((current["end"] - current["start"]).total_seconds())
            timeline.append(current)
            current = {
                "app": rec["app_name"],
                "title": rec["window_title"],
                "category": rec["category"],
                "start": rec_start,
                "end": rec_end,
            }

    current["duration"] = int((current["end"] - current["start"]).total_seconds())
    timeline.append(current)
    return timeline


def detect_fragmentation(timeline: List[Dict], threshold: int = 3, window_minutes: int = 5) -> List[Dict]:
    """检测碎片化切换。

    在 window_minutes 分钟内切换了 >= threshold 个不同应用，即为碎片化。
    """
    fragments = []
    if len(timeline) < threshold:
        return fragments

    for i in range(len(timeline)):
        window_end = timeline[i]["start"] + timedelta(minutes=window_minutes)
        apps_in_window = set()
        apps_detail = []

        for j in range(i, len(timeline)):
            if timeline[j]["start"] > window_end:
                break
            apps_in_window.add(timeline[j]["app"])
            apps_detail.append(timeline[j]["app"])

        if len(apps_in_window) >= threshold:
            fragments.append({
                "start": timeline[i]["start"],
                "apps": list(set(apps_detail)),
                "count": len(apps_in_window),
                "detail": apps_detail[:threshold + 2],  # 最多显示几个
            })
            # 跳过这个窗口，避免重复报告
            i += len(apps_detail)

    return fragments


def detect_boreholes(timeline: List[Dict], settings: dict) -> List[Dict]:
    """检测时间黑洞。

    三类黑洞：
    1. 碎片化切换
    2. 长时无效切换（专注块不足）
    3. 会议陷阱（视频会议应用过长）
    """
    holes = []
    bh = settings.get("blackhole", {})
    focus_min = bh.get("focus_block_minutes", 20)
    frag_thresh = bh.get("fragment_threshold", 3)
    frag_win = bh.get("fragment_window_minutes", 5)

    # 1. 碎片化
    frags = detect_fragmentation(timeline, frag_thresh, frag_win)
    for frag in frags:
        holes.append({
            "type": "fragmentation",
            "title": "碎片化切换",
            "severity": "warning",
            "start": frag["start"].strftime("%H:%M"),
            "detail": f"在 {frag['count']} 个应用间切换: {' → '.join(frag['detail'])}",
            "suggestion": "集中处理消息，减少上下文切换",
        })

    # 2. 短块碎片（每个专注块都 < focus_min）
    short_blocks = [t for t in timeline if t.get("duration", 0) < focus_min * 60]
    if len(short_blocks) > len(timeline) * 0.5 and len(short_blocks) > 3:
        total_wasted = sum(t.get("duration", 0) for t in short_blocks)
        holes.append({
            "type": "micro_tasks",
            "title": "大量微任务",
            "severity": "info",
            "start": "",
            "detail": f"今天有 {len(short_blocks)} 个短块（<{focus_min}分钟），"
                      f"共 {seconds_to_readable(total_wasted)} 花在碎片任务上",
            "suggestion": "尝试批量处理类似任务，减少切换成本",
        })

    # 3. 会议陷阱
    comm_timeline = [t for t in timeline if t["category"] == "communication"]
    for ct in comm_timeline:
        if ct.get("duration", 0) > 3600:  # 超过1小时
            holes.append({
                "type": "meeting_trap",
                "title": "深度会议日",
                "severity": "info",
                "start": ct["start"].strftime("%H:%M"),
                "detail": f"连续会议 {seconds_to_readable(ct['duration'])}: {ct['app']}",
                "suggestion": "考虑将多个会议合并，或设置无会议时段",
            })

    return holes


def calculate_efficiency(timeline: List[Dict], holes: List[Dict]) -> int:
    """计算效率评分 0-100。"""
    if not timeline:
        return 0

    total_seconds = sum(t.get("duration", 0) for t in timeline)
    if total_seconds == 0:
        return 0

    # 专注时长（>= 20分钟的连续块）
    focus_blocks = [t for t in timeline if t.get("duration", 0) >= 1200]
    focus_seconds = sum(t.get("duration", 0) for t in focus_blocks)
    focus_ratio = focus_seconds / total_seconds

    # 分数构成: 专注占比 60%, 黑洞惩罚 40%
    score = int(focus_ratio * 60)

    # 黑洞扣分
    penalty = 0
    for hole in holes:
        if hole["severity"] == "warning":
            penalty += 10
        elif hole["severity"] == "info":
            penalty += 5
    score -= min(penalty, 40)

    return max(0, min(100, score))


def analyze_day(target_date: date, settings: Optional[dict] = None) -> Dict[str, Any]:
    """分析某一天的工作数据，返回完整的分析报告。"""
    if settings is None:
        from config.settings import load_settings
        settings = load_settings()

    # 获取原始记录
    records = get_records_by_date(target_date)
    if not records:
        return {
            "date": target_date.isoformat(),
            "has_data": False,
            "message": f"{target_date} 没有记录数据",
        }

    # 构建时间线
    timeline = build_timeline(records)

    # 按分类汇总
    summary = get_daily_summary(target_date)
    category_stats = []
    total_seconds = 0
    for item in summary:
        secs = item["total_seconds"]
        total_seconds += secs
        category_stats.append({
            "category": item["category"],
            "name": CATEGORY_NAMES.get(item["category"], item["category"]),
            "icon": CATEGORY_ICONS.get(item["category"], "⬜"),
            "seconds": secs,
            "count": item["record_count"],
            "percentage": round(secs / total_seconds * 100, 1) if total_seconds > 0 else 0,
        })

    # 检测时间黑洞
    holes = detect_boreholes(timeline, settings)

    # 计算效率
    efficiency = calculate_efficiency(timeline, holes)

    # 最早和最晚记录
    start_time = min(t["start"] for t in timeline)
    end_time = max(t["end"] for t in timeline)
    work_duration = int((end_time - start_time).total_seconds())

    return {
        "date": target_date.isoformat(),
        "has_data": True,
        "timeline": timeline,
        "category_stats": category_stats,
        "total_seconds": total_seconds,
        "work_duration": work_duration,
        "earliest": start_time.strftime("%H:%M"),
        "latest": end_time.strftime("%H:%M"),
        "hole_count": len(holes),
        "holes": holes,
        "efficiency": efficiency,
        "record_count": len(records),
    }


def analyze_week(days: int = 7) -> Dict[str, Any]:
    """分析最近 N 天的趋势。"""
    data = get_recent_days(days)
    trend = []
    for day_str in sorted(data.keys(), reverse=True)[:days]:
        day_data = data[day_str]
        total = sum(item["total_seconds"] for item in day_data)
        trend.append({
            "date": day_str,
            "total_seconds": total,
            "categories": day_data,
        })
    return {"trend": trend}


def seconds_to_readable(seconds: int) -> str:
    """秒数转可读格式。"""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0 and m > 0:
        return f"{h}小时{m}分钟"
    elif h > 0:
        return f"{h}小时"
    return f"{m}分钟"
