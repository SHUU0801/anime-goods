import sqlite3
import csv
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "goods_info.db")
DATABASE_URL = os.getenv("DATABASE_URL")

class DBCursorWrapper:
    def __init__(self, cursor, is_postgres):
        self.cursor = cursor
        self.is_postgres = is_postgres
        self.lastrowid = None
        
    def execute(self, query, params=None):
        if self.is_postgres:
            # SQLite文法からPostgreSQL文法への簡易変換
            query = query.replace("?", "%s")
            query = query.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
            query = query.replace("datetime('now','localtime')", "CURRENT_TIMESTAMP")
            query = query.replace("INSERT OR IGNORE", "INSERT")
            
            is_insert = query.strip().upper().startswith("INSERT")
            if is_insert and " RETURNING " not in query.upper():
                query += " RETURNING id"
                
            if params:
                self.cursor.execute(query, params)
            else:
                self.cursor.execute(query)
                
            if is_insert and "RETURNING id" in query:
                try:
                    self.lastrowid = self.cursor.fetchone()[0]
                except Exception:
                    pass
        else:
            if params is not None:
                self.cursor.execute(query, params)
            else:
                self.cursor.execute(query)
            self.lastrowid = getattr(self.cursor, 'lastrowid', None)

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

class DBConnectionWrapper:
    def __init__(self, conn, is_postgres):
        self.conn = conn
        self.is_postgres = is_postgres

    @property
    def row_factory(self):
        if not self.is_postgres:
            return self.conn.row_factory
        return None

    @row_factory.setter
    def row_factory(self, val):
        if not self.is_postgres:
            self.conn.row_factory = val

    def cursor(self):
        if self.is_postgres:
            import psycopg
            return DBCursorWrapper(self.conn.cursor(row_factory=psycopg.rows.dict_row), True)
        else:
            return DBCursorWrapper(self.conn.cursor(), False)
            
    def commit(self):
        self.conn.commit()
        
    def close(self):
        self.conn.close()

def get_db_connection():
    if DATABASE_URL:
        import psycopg
        from urllib.parse import urlparse, unquote
        url = urlparse(DATABASE_URL)
        conn = psycopg.connect(
            host=url.hostname,
            port=url.port or 5432,
            dbname=url.path.lstrip('/'),
            user=url.username,
            password=unquote(url.password or ''),
            sslmode='require'
        )
        return DBConnectionWrapper(conn, True)
    else:
        conn = sqlite3.connect(DB_PATH)
        return DBConnectionWrapper(conn, False)

def get_integrity_error():
    if DATABASE_URL:
        import psycopg.errors
        return psycopg.errors.UniqueViolation
    else:
        return sqlite3.IntegrityError

def init_db():
    """データベースの初期化（テーブル作成）"""
    if DATABASE_URL:
        # PostgreSQLの場合：autocommit=TrueでDDLを直接実行（トランザクション中断を防ぐ）
        import psycopg
        from urllib.parse import urlparse, unquote
        url = urlparse(DATABASE_URL)
        conn = psycopg.connect(
            host=url.hostname,
            port=url.port or 5432,
            dbname=url.path.lstrip('/'),
            user=url.username,
            password=unquote(url.password or ''),
            sslmode='require',
            autocommit=True
        )
        cur = conn.cursor()
        tables = [
            '''CREATE TABLE IF NOT EXISTS goods_info (
                id SERIAL PRIMARY KEY,
                title TEXT, content TEXT, author TEXT, source_url TEXT,
                source_type TEXT, category TEXT, date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                freshness_score INTEGER DEFAULT 0, rarity_score INTEGER DEFAULT 0,
                reliability_score INTEGER DEFAULT 0, total_score INTEGER DEFAULT 0,
                priority_level TEXT DEFAULT '', image_url TEXT DEFAULT ''
            )''',
            '''CREATE TABLE IF NOT EXISTS search_queue (
                id SERIAL PRIMARY KEY,
                query TEXT UNIQUE, status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )''',
            '''CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE, password_hash TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )''',
            '''CREATE TABLE IF NOT EXISTS favorites (
                id SERIAL PRIMARY KEY,
                user_id INTEGER, anime_title TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, anime_title)
            )''',
            '''CREATE TABLE IF NOT EXISTS push_subscriptions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER, subscription_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, subscription_json)
            )''',
            '''CREATE TABLE IF NOT EXISTS anime_targets (
                id SERIAL PRIMARY KEY,
                name_ja TEXT UNIQUE, name_en TEXT, genre TEXT, reason TEXT
            )''',
        ]
        for sql in tables:
            cur.execute(sql)
        # image_urlカラム追加（既存テーブルへの移行）
        try:
            cur.execute("ALTER TABLE goods_info ADD COLUMN image_url TEXT DEFAULT ''")
        except Exception:
            pass  # 既にある場合は無視
        conn.close()
    else:
        # SQLiteの場合：従来の処理
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS goods_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT, content TEXT, author TEXT, source_url TEXT,
                source_type TEXT, category TEXT, date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                freshness_score INTEGER DEFAULT 0, rarity_score INTEGER DEFAULT 0,
                reliability_score INTEGER DEFAULT 0, total_score INTEGER DEFAULT 0,
                priority_level TEXT DEFAULT '', image_url TEXT DEFAULT ''
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS search_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT UNIQUE, status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE, password_hash TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, anime_title TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                UNIQUE(user_id, anime_title)
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, subscription_json TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                UNIQUE(user_id, subscription_json)
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS anime_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name_ja TEXT UNIQUE, name_en TEXT, genre TEXT, reason TEXT
            )
        ''')
        try:
            c.execute("ALTER TABLE goods_info ADD COLUMN image_url TEXT DEFAULT ''")
        except Exception:
            pass
        conn.commit()
        conn.close()
    print("[DB] 初期化完了")

def insert_item(item: dict) -> bool:
    """
    1件挿入。重複URL の場合は無視して False を返す。
    item keys: date, title, content, author, source_url, source_type, category
    """
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO goods_info (date, title, content, author, source_url, source_type, category, created_at, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.get("date", ""),
            item.get("title", ""),
            item.get("content", ""),
            item.get("author", ""),
            item.get("source_url", ""),
            item.get("source_type", ""),
            item.get("category", ""),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            item.get("image_url", "")
        ))
        conn.commit()
        return True
    except get_integrity_error():
        return False  # 重複URL
    finally:
        conn.close()

def get_all_items(title_filter=None, source_filter=None, category_filter=None) -> list:
    """全件取得。フィルタ引数が指定されていれば絞り込む。"""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row if getattr(conn, 'is_postgres', False) is False else None
    c = conn.cursor()
    query = "SELECT * FROM goods_info WHERE 1=1"
    params = []
    if title_filter:
        query += " AND title = ?"
        params.append(title_filter)
    if source_filter:
        query += " AND source_type = ?"
        params.append(source_filter)
    if category_filter:
        query += " AND category = ?"
        params.append(category_filter)
    query += " ORDER BY date DESC, created_at DESC"
    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def export_csv(filepath: str = None):
    """全データをCSVエクスポート"""
    if filepath is None:
        filepath = os.path.join(os.path.dirname(__file__), "export.csv")
    items = get_all_items()
    if not items:
        print("[DB] エクスポートするデータがありません")
        return
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=items[0].keys())
        writer.writeheader()
        writer.writerows(items)
    print(f"[DB] CSVをエクスポートしました: {filepath} ({len(items)}件)")

# ─── 通知（モック）機能 ──────────────────────────────────────────
def notify_favorited_users(query_title: str, item: dict):
    """
    お気に入り登録しているユーザーを検索し、新着情報のプッシュ/メール通知をシミュレーション（ログ出力）する
    """
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        SELECT u.email FROM favorites f
        JOIN users u ON f.user_id = u.id
        WHERE f.anime_title = ?
    ''', (query_title,))
    users = c.fetchall()
    conn.close()
    
    if users:
        print(f"\n[Notification Hook] 🌟 『{query_title}』のお気に入りユーザー({len(users)}名)に通知を送信します！")
        for u in users:
            email = u[0]
            print(f"   📧 [Web Push & Email Sent to {email}]")
            print(f"      To: {email}")
            print(f"      Subject: 『{query_title}』の新しいグッズ情報が届きました！")
            print(f"      Message: {item.get('title')}")
            # ※ここで実際のWeb Push API（pywebpush等）やSendGrid APIを叩く想定

# ─── 検索キュー機能 ──────────────────────────────────────────
def add_to_search_queue(query: str):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO search_queue (query, status) VALUES (?, 'pending')", (query,))
        conn.commit()
        return True
    except get_integrity_error():
        # 既にキューにある場合はPENDINGに戻す
        c.execute("UPDATE search_queue SET status='pending', created_at=CURRENT_TIMESTAMP WHERE query=?", (query,))
        conn.commit()
        return True
    finally:
        conn.close()

def get_next_from_queue():
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row if getattr(conn, 'is_postgres', False) is False else None
    c = conn.cursor()
    c.execute("SELECT id, query FROM search_queue WHERE status='pending' ORDER BY created_at ASC LIMIT 1")
    row = c.fetchone()
    if row:
        c.execute("UPDATE search_queue SET status='processing' WHERE id=?", (row['id'],))
        conn.commit()
        conn.close()
        return row['query']
    conn.close()
    return None

def mark_queue_done(query: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE search_queue SET status='completed' WHERE query=?", (query,))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("[DB] テスト完了")
