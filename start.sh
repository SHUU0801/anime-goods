#!/bin/bash
# Render上でのクローラー + Webサーバー同時起動
python3 crawler.py &
gunicorn server:app --bind 0.0.0.0:${PORT:-5000}
