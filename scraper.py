import json
import os
import time
import re

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def scrape_x(browser_agent_func) -> list:
    """
    X(Twitter)検索をブラウザエージェントで実行し、投稿リストを返す。
    browser_agent_func: ブラウザ操作を行うコールバック（main.pyから渡す）
    Returns: list of dict {date, title, content, author, source_url, source_type}
    """
    config = load_config()
    results = []

    for target in config["targets"]:
        title = target["name"]
        for keyword in target["keywords_x"]:
            print(f"[X] 検索中: '{keyword}' ({title})")
            try:
                items = browser_agent_func("x", keyword, title)
                results.extend(items)
                time.sleep(3)  # レート制限対策
            except Exception as e:
                print(f"[X] エラー ({keyword}): {e}")
                continue

    return results

def scrape_google(browser_agent_func) -> list:
    """
    Google検索をブラウザエージェントで実行し、検索結果リストを返す。
    Returns: list of dict {date, title, content, author, source_url, source_type}
    """
    config = load_config()
    results = []

    for target in config["targets"]:
        title = target["name"]
        for keyword in target["keywords_google"]:
            print(f"[Google] 検索中: '{keyword}' ({title})")
            try:
                items = browser_agent_func("google", keyword, title)
                results.extend(items)
                time.sleep(2)  # レート制限対策
            except Exception as e:
                print(f"[Google] エラー ({keyword}): {e}")
                continue

    return results
