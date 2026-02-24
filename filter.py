import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

# 転売・個人感想関連の除外キーワード
EXCLUDE_KEYWORDS = [
    "メルカリ", "ラクマ", "フリマ", "ヤフオク", "転売", "出品中", "売ります",
    "買います", "欲しい", "誕生日", "個人的に", "感想"
]

# 優先カテゴリキーワード
CATEGORY_MAP = {
    "一番くじ": ["一番くじ", "ichibankuji", "ichiban kuji"],
    "コラボカフェ": ["コラボカフェ", "コラボカフェ", "collab cafe", "コラボ喫茶", "期間限定カフェ"],
    "グッズ": ["グッズ", "フィギュア", "アクスタ", "缶バッジ", "クリアファイル", "キーホルダー", "ぬいぐるみ", "タペストリー", "アパレル"],
    "コラボ": ["コラボ", "collaboration", "コラボレーション", "フェア"],
    "予約": ["予約", "受注", "先行", "予約開始", "予約受付"],
    "イベント": ["イベント", "展示", "原画展", "pop.up", "popup", "ポップアップ"]
}

# 信頼ドメイン（Googleスクレイピング用）
TRUSTED_DOMAINS = [
    "animate.co.jp", "gamers.co.jp", "jump.shueisha.co.jp",
    "natalie.mu", "ichibankuji.com", "lawson.co.jp",
    "bandaispirits.co.jp", "akibaoo.co.jp", "aniplex.co.jp",
    "collab-cafe.com", "ponycanyon.co.jp", "ufotablecinema.com",
    "nikkansports.com", "animatetimes.com", "nijigenfes.jp"
]

def detect_category(text: str) -> str:
    """テキストから情報カテゴリを判定する"""
    text_lower = text.lower()
    for category, keywords in CATEGORY_MAP.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                return category
    return "その他"

def is_trusted_source(item: dict) -> bool:
    """信頼できる情報源かどうかを判定する"""
    source_type = item.get("source_type", "")
    author = item.get("author", "").lower()
    url = item.get("source_url", "").lower()

    if source_type == "X":
        # X: アカウント名に公式キーワードが含まれるか
        trust_kws = ["公式", "official", "アニメイト", "ナタリー", "jump", "aniplex",
                     "bandai", "バンダイ", "lawson", "ローソン", "animate"]
        return any(kw in author for kw in trust_kws)
    elif source_type == "Google":
        # Google: 信頼ドメインからの記事か
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        return any(td in domain for td in TRUSTED_DOMAINS)
    return False

def has_filter_keywords(text: str) -> bool:
    """有益情報キーワードが含まれているか確認"""
    useful_kws = [
        "予約", "発売", "コラボ", "開催", "グッズ", "受注", "限定", "発表",
        "一番くじ", "コラボカフェ", "フェア", "キャンペーン", "イベント", "展示",
        "フィギュア", "アクスタ", "popup", "ポップアップ"
    ]
    return any(kw in text for kw in useful_kws)

def is_too_old(date_str: str, max_days: int = 365) -> bool:
    """1年以上前の情報か確認"""
    if not date_str:
        return False
    try:
        # 複数の日付フォーマットに対応
        for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"]:
            try:
                dt = datetime.strptime(date_str[:10], fmt)
                return dt < datetime.now() - timedelta(days=max_days)
            except ValueError:
                continue
    except Exception:
        pass
    return False

def has_exclude_keywords(text: str) -> bool:
    """除外キーワードが含まれているか確認"""
    return any(kw in text for kw in EXCLUDE_KEYWORDS)

def filter_items(items: list) -> list:
    """
    取得した全アイテムをフィルタリングして質を担保する。
    Returns: フィルタ済みアイテムリスト
    """
    results = []
    seen_urls = set()

    for item in items:
        url = item.get("source_url", "")
        content = item.get("content", "")
        date_str = item.get("date", "")

        # 重複URL除去
        if url in seen_urls or not url:
            continue
        seen_urls.add(url)

        # 転売・個人感想の除外
        if has_exclude_keywords(content):
            print(f"[FILTER] 除外(キーワード): {content[:40]}")
            continue

        # 古すぎる情報の除外
        if is_too_old(date_str):
            print(f"[FILTER] 除外(古い): {date_str} - {content[:40]}")
            continue

        # 有益キーワードチェック
        if not has_filter_keywords(content):
            print(f"[FILTER] 除外(無益): {content[:40]}")
            continue

        # カテゴリ付与
        item["category"] = detect_category(content)

        # 信頼度スコア付与（信頼源=2, 無名=1）
        item["trust_score"] = 2 if is_trusted_source(item) else 1

        results.append(item)

    # 信頼度・日付でソート
    results.sort(key=lambda x: (x.get("trust_score", 0), x.get("date", "")), reverse=True)
    print(f"[FILTER] {len(items)}件中 {len(results)}件が通過")
    return results

if __name__ == "__main__":
    # フィルタリングロジックのテスト
    test_items = [
        {"source_url": "https://x.com/test1", "content": "デスノート グッズ予約開始！限定コラボ！", "date": "2025-06-01", "author": "deathnote_official", "source_type": "X"},
        {"source_url": "https://mercari.com/xxx", "content": "デスノート グッズ売ります", "date": "2025-06-01", "author": "user123", "source_type": "X"},
        {"source_url": "https://natalie.mu/news/1", "content": "デスノート コラボカフェ開催決定！", "date": "2025-05-10", "author": "natalie.mu", "source_type": "Google"},
    ]
    filtered = filter_items(test_items)
    for f in filtered:
        print(f" -> [{f['category']}] {f['content'][:50]}")
    print("フィルタリングテスト完了")
