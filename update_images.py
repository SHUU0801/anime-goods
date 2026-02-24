import sqlite3
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import database
from crawler import fetch_ogp_image

def update_existing_images():
    conn = sqlite3.connect(database.DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # 画像が未設定の記事を取得
    c.execute("SELECT id, source_url FROM goods_info WHERE image_url IS NULL OR image_url = ''")
    rows = c.fetchall()
    
    print(f"対象記事数: {len(rows)} 件")
    
    updated = 0
    for row in rows:
        item_id = row['id']
        url = row['source_url']
        if url:
            print(f"[{item_id}] 取得中... {url}")
            img_url = fetch_ogp_image(url)
            if img_url:
                c.execute("UPDATE goods_info SET image_url = ? WHERE id = ?", (img_url, item_id))
                conn.commit()
                updated += 1
                print(f" -> 成功: {img_url}")
            else:
                print(" -> 画像が見つかりませんでした")
                
    conn.close()
    print(f"\n✅ 更新完了: {updated} 件の画像を追加しました。")

if __name__ == "__main__":
    update_existing_images()
