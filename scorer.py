"""
scorer.py — AIスコアリングエンジン
収集した情報に対して「新しさ」「希少性」「信頼度」を評価し、
総合優先度スコア(0-100)を付与する。
"""

import re
from datetime import datetime, timedelta

# ── 希少性キーワード（高スコア → 希少・限定） ────────────────
RARITY_HIGH = [
    "限定", "数量限定", "受注生産", "完全受注", "一番くじ", "抽選",
    "先着", "初回限定", "特典", "シリアル", "ナンバリング", "プレミアム",
    "コレクターズ", "レア", "exclusive", "limited"
]
RARITY_MED = [
    "受注", "予約", "先行", "コラボ", "期間限定", "店舗限定",
    "オンライン限定", "会場限定", "フェア"
]

# ── 信頼性ドメイン（スコア加点） ─────────────────────────────
TRUST_HIGH_DOMAINS = [
    "animate.co.jp", "ichibankuji.com", "bandaispirits.co.jp",
    "aniplex.co.jp", "jump.shueisha.co.jp", "natalie.mu",
    "animatetimes.com", "prtimes.jp", "famitsu.com",
    "nijigenfes.jp", "collab-cafe.com", "lawson.co.jp"
]
TRUST_MED_DOMAINS = [
    "gamers.co.jp", "akibaoo.co.jp", "xlarge.jp",
    "horipro-stage.jp", "ufotablecinema.com"
]

# ── 公式Xキーワード ──────────────────────────────────────────
OFFICIAL_X_KEYWORDS = [
    "公式", "official", "アニメイト", "バンダイ", "bandai",
    "aniplex", "ジャンプ", "jump", "ローソン", "lawson"
]

def score_freshness(date_str: str) -> int:
    """
    新しさスコア (0-40 点)
    直近7日:40 / 30日:30 / 90日:20 / 180日:10 / それ以上:0
    """
    if not date_str:
        return 5  # 日付不明は低め
    try:
        for fmt in ["%Y-%m-%d", "%Y/%m/%d"]:
            try:
                dt = datetime.strptime(date_str[:10], fmt)
                break
            except ValueError:
                continue
        else:
            return 5
        delta = (datetime.now() - dt).days
        if delta <= 7:   return 40
        if delta <= 30:  return 30
        if delta <= 90:  return 20
        if delta <= 180: return 10
        return 3
    except Exception:
        return 5

def score_rarity(content: str) -> int:
    """
    希少性スコア (0-35 点)
    高希少キーワード:+5/個(最大35) 中希少:+2/個
    """
    content_lower = content.lower()
    score = 0
    for kw in RARITY_HIGH:
        if kw.lower() in content_lower:
            score += 5
    for kw in RARITY_MED:
        if kw.lower() in content_lower:
            score += 2
    return min(score, 35)

def score_reliability(item: dict) -> int:
    """
    信頼度スコア (0-25 点)
    高信頼ドメイン:25 / 中信頼:15 / 公式Xアカウント:20 / その他:5
    """
    url    = item.get("source_url", "").lower()
    author = item.get("author", "").lower()
    source = item.get("source_type", "")

    # Googleソース: ドメイン判定
    if source == "Google":
        for d in TRUST_HIGH_DOMAINS:
            if d in url:
                return 25
        for d in TRUST_MED_DOMAINS:
            if d in url:
                return 15
        return 5

    # Xソース: アカウント名判定
    if source == "X":
        for kw in OFFICIAL_X_KEYWORDS:
            if kw in author:
                return 20
        return 8

    return 5

def compute_priority_level(total_score: int) -> str:
    """スコアから優先度ラベルを付与"""
    if total_score >= 75: return "🔴 最重要"
    if total_score >= 55: return "🟠 高"
    if total_score >= 35: return "🟡 中"
    return "⚪ 低"

def score_item(item: dict) -> dict:
    """
    1件のアイテムにスコアを付与して返す。
    追加フィールド: freshness_score, rarity_score, reliability_score,
                   total_score, priority_level
    """
    content = item.get("content", "")
    fresh   = score_freshness(item.get("date", ""))
    rarity  = score_rarity(content)
    trust   = score_reliability(item)
    total   = fresh + rarity + trust

    item["freshness_score"]   = fresh
    item["rarity_score"]      = rarity
    item["reliability_score"] = trust
    item["total_score"]       = total
    item["priority_level"]    = compute_priority_level(total)
    return item

def score_all(items: list) -> list:
    """全アイテムにスコアを付与して優先度降順でソート"""
    scored = [score_item(dict(i)) for i in items]
    scored.sort(key=lambda x: x["total_score"], reverse=True)
    return scored

if __name__ == "__main__":
    # テスト
    test = [
        {
            "date": "2025-11-29",
            "content": "一番くじ DEATH NOTE 数量限定！受注生産。死神リュークのフィギュア",
            "author": "1kuji.com",
            "source_url": "https://ichibankuji.com/test",
            "source_type": "Google"
        },
        {
            "date": "2024-01-01",
            "content": "デスノートグッズ紹介",
            "author": "user123",
            "source_url": "https://unknown.com/test",
            "source_type": "X"
        }
    ]
    for r in score_all(test):
        prio = r['priority_level'].encode('ascii', 'ignore').decode()
        print(f"[Score:{r['total_score']}] F:{r['freshness_score']} R:{r['rarity_score']} T:{r['reliability_score']} - {r['content'][:40]}")
