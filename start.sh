#!/bin/bash
# Render上でのバックグラウンドクローラーとWebサーバーの同時起動
python crawler.py &
gunicorn server:app
