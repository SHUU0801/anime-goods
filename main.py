"""
main.py — アニメグッズ情報収集 メインスクリプト
X（Twitter）と Google を並列でスクレイピングし、
フィルタリングして SQLite に保存する。

実行方法:
  python main.py

完了後:
  python server.py  → http://localhost:5000 で Web UI を確認
"""

import os
import sys
import json
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── 内部モジュール ─────────────────────────────────────────────
from database import init_db, insert_item
from filter   import filter_items

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

# ── ブラウザエージェント経由のスクレイピング ──────────────────
# ブラウザ操作はこのスクリプトからは呼び出せないため、
# ブラウザエージェントのセッション結果を受け取る方式を採用。
# scrape_with_browser() は browser_subagent が呼び出す。
RAW_RESULTS_PATH = os.path.join(BASE_DIR, "raw_results.json")

def load_raw_results() -> list:
    """browser_subagent が書き出した raw_results.json を読み込む"""
    if not os.path.exists(RAW_RESULTS_PATH):
        print("[MAIN] raw_results.json が見つかりません。スクレイピングを先に実行してください。")
        return []
    with open(RAW_RESULTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"[MAIN] raw_results.json を読込: {len(data)} 件")
    return data

def save_raw_results(items: list):
    """デバッグ用: スクレイピング結果を保存"""
    with open(RAW_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"[MAIN] raw_results.json に {len(items)} 件を保存")

def run_pipeline(raw_items: list):
    """フィルタ → DB保存のパイプライン"""
    if not raw_items:
        print("[MAIN] データが0件のため処理をスキップします")
        return 0

    print(f"[MAIN] フィルタリング開始: {len(raw_items)} 件")
    filtered = filter_items(raw_items)
    print(f"[MAIN] フィルタ通過: {len(filtered)} 件")

    saved = 0
    skipped = 0
    for item in filtered:
        if insert_item(item):
            saved += 1
        else:
            skipped += 1

    print(f"[MAIN] DB保存完了: {saved} 件保存 / {skipped} 件重複スキップ")
    return saved

if __name__ == "__main__":
    print("=" * 55)
    print("  アニメグッズ情報収集 - メインパイプライン")
    print("=" * 55)

    # DB 初期化
    init_db()

    # ブラウザエージェントが生成した raw_results.json を読み込む
    raw_items = load_raw_results()

    if not raw_items:
        print("[MAIN] ヒント: browser_subagent でスクレイピング後に再実行してください")
    else:
        saved = run_pipeline(raw_items)
        print(f"\n[MAIN] 完了! {saved} 件を新たにDBに保存しました")
        print("[MAIN] 次: python server.py → http://localhost:5000")
