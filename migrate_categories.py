"""迁移脚本 — 将历史 'other' 分类的记录按新配置重新分类。"""

import sqlite3
from datetime import date
from pathlib import Path


def migrate():
    db_path = Path(__file__).parent / "data" / "records.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 加载分类配置
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from config.settings import load_settings
    cats = load_settings().get("categories", {})

    # 构建关键词 -> 分类的映射（小写）
    kw_to_cat = {}
    for cat, kws in cats.items():
        if cat == "other":
            continue
        for kw in kws:
            kw_to_cat[kw.lower()] = cat

    def classify(app_name: str, window_title: str) -> str:
        combined = f"{app_name.lower()} {window_title.lower()}"
        for kw, cat in kw_to_cat.items():
            if kw in combined:
                return cat
        return "other"

    # 查询所有 category='other' 的记录
    rows = conn.execute(
        "SELECT id, app_name, window_title FROM records WHERE category = 'other'"
    ).fetchall()

    updated = 0
    skipped = 0
    for row in rows:
        new_cat = classify(row["app_name"], row["window_title"])
        if new_cat != "other":
            conn.execute(
                "UPDATE records SET category = ? WHERE id = ?",
                (new_cat, row["id"]),
            )
            updated += 1
        else:
            skipped += 1

    conn.commit()
    conn.close()

    print(f"[OK] Migration complete: updated {updated} records, skipped {skipped}")


if __name__ == "__main__":
    migrate()
