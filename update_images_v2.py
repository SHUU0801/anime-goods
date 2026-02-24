"""
update_images_v2.py
既存記事のサムネイルを再取得する。
Google NewsのG=プレースホルダーや画像未設定の記事を対象に、
decode_google_news_url → fetch_ogp_image の順で再取得する。
"""
import sqlite3
import sys
import os
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import database
from crawler import fetch_ogp_image, decode_google_news_url

# G=アイコン（Google Newsプレースホルダー）を検出するキーワード
PLACEHOLDER_KEYWORDS = [
    'googleusercontent.com',
    'lh3.googleusercontent.com',
    'gstatic.com',
    'google.com',
    'news.google.com',
]

def is_placeholder(url: str) -> bool:
    """Google Newsのプレースホルダー画像かどうかを判定"""
    if not url:
        return True
    lower = url.lower()
    return any(kw in lower for kw in PLACEHOLDER_KEYWORDS)

def update_existing_images_v2():
    conn = sqlite3.connect(database.DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 画像が未設定、またはGoogleのロゴ/プレースホルダーになっている記事を取得
    rows_all = []
    for kw in PLACEHOLDER_KEYWORDS:
        c.execute(f"SELECT id, source_url, image_url FROM goods_info WHERE image_url LIKE ?", (f'%{kw}%',))
        rows_all.extend(c.fetchall())

    # 画像なし
    c.execute("SELECT id, source_url, image_url FROM goods_info WHERE image_url IS NULL OR image_url = ''")
    rows_all.extend(c.fetchall())

    # 重複除去
    seen = set()
    rows = []
    for row in rows_all:
        if row['id'] not in seen:
            seen.add(row['id'])
            rows.append(row)

    print(f"対象記事数: {len(rows)} 件")

    updated = 0
    failed = 0
    for i, row in enumerate(rows):
        item_id = row['id']
        url = row['source_url']
        if not url:
            continue

        print(f"[{i+1}/{len(rows)}] ID:{item_id} 取得中... {url[:80]}")

        # Google NewsのURLをデコードして本物の記事URLを取得
        real_url = decode_google_news_url(url)
        if real_url != url:
            print(f"   -> デコード: {real_url[:80]}")

        img_url = fetch_ogp_image(real_url)

        if img_url and not is_placeholder(img_url):
            c.execute("UPDATE goods_info SET image_url = ? WHERE id = ?", (img_url, item_id))
            conn.commit()
            updated += 1
            print(f"   -> 成功: {img_url[:80]}")
        else:
            failed += 1
            print(f"   -> 取得失敗または不適切な画像（スキップ）")

        time.sleep(0.5)  # レートリミット対策

    conn.close()
    print(f"\n✅ 更新完了: {updated} 件成功 / {failed} 件失敗")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    update_existing_images_v2()
