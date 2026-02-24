"""
setup_targets.py — アニメ作品マスタ登録スクリプト
anime_targets.json を読み込み、DBの targets テーブルに登録する。
"""
import json, os, sqlite3, database

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DB_PATH     = os.path.join(BASE_DIR, "goods_info.db")
TARGETS_FILE = os.path.join(BASE_DIR, "anime_targets.json")

def setup_targets_table():
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS anime_targets (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name_ja  TEXT UNIQUE,
            name_en  TEXT,
            genre    TEXT,
            reason   TEXT,
            enabled  INTEGER DEFAULT 1,
            added_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.commit()

    with open(TARGETS_FILE, "r", encoding="utf-8") as f:
        targets = json.load(f)

    inserted = 0
    for t in targets:
        try:
            c.execute("""
                INSERT INTO anime_targets (name_ja, name_en, genre, reason)
                VALUES (?, ?, ?, ?)
            """, (t["name_ja"], t["name_en"], t["genre"], t["reason"]))
            inserted += 1
        except database.get_integrity_error():
            pass  # 重複スキップ

    conn.commit()
    conn.close()
    print(f"[TARGETS] {inserted}/{len(targets)} 件を登録しました。")

# goods_info テーブルに score/priority カラムを追加
def upgrade_goods_table():
    conn = database.get_db_connection()
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE goods_info ADD COLUMN freshness_score INTEGER DEFAULT 0")
        print("[DB] freshness_score カラムを追加")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE goods_info ADD COLUMN rarity_score INTEGER DEFAULT 0")
        print("[DB] rarity_score カラムを追加")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE goods_info ADD COLUMN reliability_score INTEGER DEFAULT 0")
        print("[DB] reliability_score カラムを追加")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE goods_info ADD COLUMN total_score INTEGER DEFAULT 0")
        print("[DB] total_score カラムを追加")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE goods_info ADD COLUMN priority_level TEXT DEFAULT ''")
        print("[DB] priority_level カラムを追加")
    except Exception:
        pass
    conn.commit()
    conn.close()

if __name__ == "__main__":
    setup_targets_table()
    upgrade_goods_table()
    print("[SETUP] 完了!")
