"""命令行入口 — ai-recorder 命令。"""

import argparse
import sys
from datetime import date, timedelta


def cmd_start(args):
    """启动后台采集（托盘模式）。"""
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    from tray import TrayIcon
    print("✅ AI Recorder 已启动，请在系统托盘中右键菜单操作")
    print("   - 右键托盘图标 → 开始记录")
    print("   - 右键托盘图标 → 生成昨天日报")
    print("   - 右键托盘图标 → 退出")
    TrayIcon().run()


def cmd_stop(args):
    """停止后台采集。"""
    from core.recorder import WindowRecorder
    r = WindowRecorder()
    r.stop()
    print("✅ 数据采集已停止")


def cmd_report(args):
    """生成指定日期的日报。"""
    from core.reporter import generate_report
    from output.markdown import save_markdown_report
    from output.html import save_html_report

    target = date.fromisoformat(args.date) if args.date else date.today() - timedelta(days=1)

    print(f"📊 正在生成 {target} 的日报...")
    report_data = generate_report(target)

    if not report_data.get("success"):
        print(f"❌ 生成失败: {report_data.get('error', '未知错误')}")
        return

    md_path = save_markdown_report(report_data, target)
    html_path = save_html_report(report_data, target)

    print(f"\n✅ 日报已生成:")
    if md_path:
        print(f"   📝 Markdown: {md_path}")
    if html_path:
        print(f"   🌐 HTML: {html_path}")


def cmd_stats(args):
    """查看统计数据。"""
    from storage.database import get_total_records, get_recent_days
    from core.analyzer import analyze_day
    from datetime import date, timedelta

    total = get_total_records()
    print(f"📊 AI Recorder 统计")
    print(f"   总记录数: {total}")

    if total == 0:
        print("\n   还没有数据。运行 'ai-recorder start' 开始采集。")
        return

    # 显示最近 7 天
    days = get_recent_days(7)
    print(f"\n   最近 7 天:")
    for day_str in sorted(days.keys(), reverse=True):
        day_data = days[day_str]
        total_secs = sum(item["total_seconds"] for item in day_data)
        hours = total_secs // 3600
        mins = (total_secs % 3600) // 60
        cats = ", ".join(
            f"{item['category']}:{item['total_seconds']//60}min" for item in day_data[:3]
        )
        print(f"   {day_str} — {hours}h{mins}m ({cats})")


def cmd_clear(args):
    """清除所有数据。"""
    from storage.database import clear_all_data
    clear_all_data()
    print("🗑️  所有数据已清除")


def main():
    parser = argparse.ArgumentParser(
        prog="ai-recorder",
        description="AI 工作轨迹记录与日报生成器",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # start
    sp = subparsers.add_parser("start", help="启动后台采集（托盘模式）")
    sp.set_defaults(func=cmd_start)

    # stop
    sp = subparsers.add_parser("stop", help="停止后台采集")
    sp.set_defaults(func=cmd_stop)

    # report
    sp = subparsers.add_parser("report", help="生成日报")
    sp.add_argument("--date", help="日期 (YYYY-MM-DD)，默认为昨天")
    sp.set_defaults(func=cmd_report)

    # stats
    sp = subparsers.add_parser("stats", help="查看统计数据")
    sp.set_defaults(func=cmd_stats)

    # clear
    sp = subparsers.add_parser("clear", help="清除所有数据")
    sp.set_defaults(func=cmd_clear)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
