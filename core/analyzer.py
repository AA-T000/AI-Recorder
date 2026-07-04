"""本地分析引擎 — 时间线重建、应用分类、时间黑洞检测、效率评分。

设计思路（参考 ActivityWatch 的 coalescing 理念）：
- 原始数据是窗口切换事件（原子记录）
- 分析时将同一应用的连续时间段合并为一个大块
- 短时间内的应用切换（< 3分钟）视为同一活动的上下文切换
"""

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


def build_coalesced_timeline(records: List[Dict], merge_gap_seconds: int = 180) -> List[Dict]:
    """将原始记录合并为粗粒度的时间线块。

    合并规则：
    1. 同一 category 的连续时间段合并为一个块
    2. 两个同 category 块之间的间隔 <= merge_gap_seconds 也合并
    3. 不同 category 的块不合并

    Args:
        records: 原始窗口切换记录
        merge_gap_seconds: 同一分类内允许的最大间隔秒数（默认3分钟）

    Returns:
        合并后的时间线块列表
    """
    if not records:
        return []

    # 先按时间排序
    records.sort(key=lambda r: _parse_iso(r["start_time"]))

    blocks = []
    current_block = {
        "category": records[0]["category"],
        "app_names": set(),
        "titles": set(),
        "start": _parse_iso(records[0]["start_time"]),
        "end": _parse_iso(records[0]["end_time"]) if records[0].get("end_time") else _parse_iso(records[0]["start_time"]),
        "total_seconds": records[0].get("duration_seconds", 0),
    }

    for rec in records[1:]:
        rec_start = _parse_iso(rec["start_time"])
        rec_end = _parse_iso(rec["end_time"]) if rec.get("end_time") else rec_start
        rec_duration = rec.get("duration_seconds", 0)

        # 判断是否可以合并到当前块
        gap = (rec_start - current_block["end"]).total_seconds()

        if (rec["category"] == current_block["category"]
                and gap <= merge_gap_seconds):
            # 合并到当前块
            current_block["app_names"].add(rec["app_name"])
            current_block["titles"].add(rec["window_title"])
            current_block["end"] = max(current_block["end"], rec_end)
            current_block["total_seconds"] += rec_duration
        else:
            # 结束当前块，开启新块
            current_block["app_names"] = list(current_block["app_names"])
            current_block["titles"] = list(current_block["titles"])[:3]  # 最多保留3个标题
            current_block["duration"] = int(current_block["total_seconds"])
            blocks.append(current_block)
            current_block = {
                "category": rec["category"],
                "app_names": {rec["app_name"]},
                "titles": {rec["window_title"]},
                "start": rec_start,
                "end": rec_end,
                "total_seconds": rec_duration,
            }

    # 最后一个块
    current_block["app_names"] = list(current_block["app_names"])
    current_block["titles"] = list(current_block["titles"])[:3]
    current_block["duration"] = int(current_block["total_seconds"])
    blocks.append(current_block)

    return blocks


def detect_fragmentation(blocks: List[Dict], threshold: int = 3, window_minutes: int = 5) -> List[Dict]:
    """检测碎片化切换。

    在 window_minutes 分钟内出现了 >= threshold 个不同分类，即为碎片化。
    """
    fragments = []
    if len(blocks) < threshold:
        return fragments

    i = 0
    while i < len(blocks):
        window_end = blocks[i]["start"] + timedelta(minutes=window_minutes)
        categories_in_window = set()
        block_indices = []

        for j in range(i, len(blocks)):
            if blocks[j]["start"] > window_end:
                break
            categories_in_window.add(blocks[j]["category"])
            block_indices.append(j)

        if len(categories_in_window) >= threshold:
            apps_involved = []
            for idx in block_indices:
                apps_involved.extend(blocks[idx].get("app_names", []))
            fragments.append({
                "start": blocks[i]["start"],
                "categories": list(categories_in_window),
                "count": len(categories_in_window),
                "apps": list(set(apps_involved))[:5],
                "blocks": block_indices,
            })
            # 跳过这个窗口
            i = block_indices[-1] + 1
        else:
            i += 1

    return fragments


def detect_boreholes(blocks: List[Dict], settings: dict) -> List[Dict]:
    """检测时间黑洞。

    三类黑洞：
    1. 碎片化切换 — 短时间内在不同分类间频繁切换
    2. 长时无效切换 — 专注块不足，大部分时间在碎片任务间切换
    3. 会议陷阱 — 视频会议应用连续使用超过1小时
    """
    holes = []
    bh = settings.get("blackhole", {})
    focus_min = bh.get("focus_block_minutes", 20)
    frag_thresh = bh.get("fragment_threshold", 3)
    frag_win = bh.get("fragment_window_minutes", 5)

    # 1. 碎片化
    frags = detect_fragmentation(blocks, frag_thresh, frag_win)
    for frag in frags:
        holes.append({
            "type": "fragmentation",
            "title": "碎片化切换",
            "severity": "warning",
            "start": frag["start"].strftime("%H:%M"),
            "detail": f"在 {frag['count']} 个应用分类间切换: {', '.join(frag['categories'])}",
            "suggestion": "集中处理消息，减少上下文切换。建议设定固定时间批量回复",
        })

    # 2. 短块碎片（大部分专注块都 < focus_min 分钟）
    total_blocks = len(blocks)
    if total_blocks > 0:
        short_blocks = [b for b in blocks if b.get("duration", 0) < focus_min * 60]
        if len(short_blocks) > total_blocks * 0.6 and len(short_blocks) > 3:
            total_wasted = sum(b.get("duration", 0) for b in short_blocks)
            holes.append({
                "type": "micro_tasks",
                "title": "大量微任务",
                "severity": "info",
                "start": "",
                "detail": f"今天有 {len(short_blocks)}/{total_blocks} 个短块（<{focus_min}分钟），"
                          f"共 {seconds_to_readable(total_wasted)} 花在碎片任务上",
                "suggestion": "尝试批量处理类似任务，减少切换成本",
            })

    # 3. 会议陷阱
    comm_blocks = [b for b in blocks if b["category"] == "communication"]
    for cb in comm_blocks:
        if cb.get("duration", 0) > 3600:  # 超过1小时
            holes.append({
                "type": "meeting_trap",
                "title": "深度会议日",
                "severity": "info",
                "start": cb["start"].strftime("%H:%M"),
                "detail": f"连续会议 {seconds_to_readable(cb['duration'])}: {', '.join(cb.get('app_names', []))}",
                "suggestion": "考虑将多个会议合并，或设置无会议时段保持专注",
            })

    return holes


def calculate_efficiency(blocks: List[Dict], holes: List[Dict]) -> int:
    """计算效率评分 0-100。

    评分构成：
    - 专注时长占比（60分）：>= 20分钟的连续块占总时长的比例
    - 黑洞惩罚（40分）：碎片化、微任务、会议陷阱等扣分
    """
    if not blocks:
        return 0

    total_seconds = sum(b.get("duration", 0) for b in blocks)
    if total_seconds == 0:
        return 0

    # 专注时长（>= 20分钟的连续块）
    focus_blocks = [b for b in blocks if b.get("duration", 0) >= 1200]
    focus_seconds = sum(b.get("duration", 0) for b in focus_blocks)
    focus_ratio = focus_seconds / total_seconds

    # 分数构成
    score = int(focus_ratio * 60)

    # 黑洞扣分
    penalty = 0
    for hole in holes:
        if hole["severity"] == "warning":
            penalty += 12
        elif hole["severity"] == "info":
            penalty += 6
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

    # 构建合并后的时间线（粗粒度）
    blocks = build_coalesced_timeline(records)

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
    holes = detect_boreholes(blocks, settings)

    # 计算效率
    efficiency = calculate_efficiency(blocks, holes)

    # 最早和最晚记录
    start_time = min(_parse_iso(r["start_time"]) for r in records)
    end_time = max(_parse_iso(r["end_time"]) for r in records if r.get("end_time"))
    work_duration = int((end_time - start_time).total_seconds())

    return {
        "date": target_date.isoformat(),
        "has_data": True,
        "timeline": blocks,  # 合并后的粗粒度时间线
        "category_stats": category_stats,
        "total_seconds": total_seconds,
        "work_duration": work_duration,
        "earliest": start_time.strftime("%H:%M"),
        "latest": end_time.strftime("%H:%M"),
        "hole_count": len(holes),
        "holes": holes,
        "efficiency": efficiency,
        "record_count": len(records),
        "block_count": len(blocks),  # 合并后的块数
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
