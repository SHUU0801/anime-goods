#!/bin/bash
# DB初期化（テーブルが未存在の場合のみ作成）
python3 -c "import database; database.init_db()"
# アニメターゲット登録（重複自動スキップ）
python3 setup_targets.py
# クローラーをバックグラウンドで起動
python3 crawler.py &
# Webサーバー起動
gunicorn server:app --bind 0.0.0.0:${PORT:-5000}
