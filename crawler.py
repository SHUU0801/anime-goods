"""
crawler.py — 無限サーチ常駐ワーカー
検索キューまたはターゲットリストから作品を選び、
Google News RSS等を用いてグッズ情報を収集しDBに登録し続ける。
"""

import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import time
import sqlite3
import re
import datetime
import os
import sys
try:
    import requests as req_lib
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import database
import filter as goods_filter

def decode_google_news_url(gnews_url: str) -> str:
    """Google Newsの間接URLを実際の記事URLにデコードする"""
    if "news.google.com" not in gnews_url:
        return gnews_url
    try:
        from googlenewsdecoder import new_decoderv1
        decoded_res = new_decoderv1(gnews_url)
        if decoded_res.get("status") and decoded_res.get("decoded_url"):
            return decoded_res["decoded_url"]
    except Exception:
        pass
    # フォールバック: requestsでリダイレクト先を追う
    if HAS_REQUESTS:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            r = req_lib.get(gnews_url, headers=headers, timeout=8, allow_redirects=True)
            if "news.google.com" not in r.url:
                return r.url
        except Exception:
            pass
    return gnews_url


def fetch_google_news(query: str) -> list:
    """Google News RSS から指定キーワードのニュースを取得"""
    encoded_query = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})

    # media名前空間の定義
    MEDIA_NS = "http://search.yahoo.com/mrss/"

    results = []
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            ET.register_namespace('media', MEDIA_NS)
            root = ET.fromstring(xml_data)
            for item in root.findall('./channel/item'):
                title = item.find('title').text if item.find('title') is not None else ""
                link = item.find('link').text if item.find('link') is not None else ""
                pubDate = item.find('pubDate').text if item.find('pubDate') is not None else ""
                source = item.find('source').text if item.find('source') is not None else "Google News"

                # dateをパース (RFC822形式)
                try:
                    parts = pubDate.split()
                    if len(parts) >= 4:
                        month_map = {"Jan":"01","Feb":"02","Mar":"03","Apr":"04","May":"05","Jun":"06",
                                     "Jul":"07","Aug":"08","Sep":"09","Oct":"10","Nov":"11","Dec":"12"}
                        y = parts[3]
                        m = month_map.get(parts[2][:3], "01")
                        d = parts[1].zfill(2)
                        parsed_date = f"{y}-{m}-{d} {parts[4]}"
                    else:
                        parsed_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                except:
                    parsed_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # --- 画像取得: RSSのmedia:contentを最優先 ---
                rss_image = ""
                # media:content
                mc = item.find(f'{{{MEDIA_NS}}}content')
                if mc is not None and mc.get('url'):
                    img = mc.get('url', '')
                    if img and 'google' not in img.lower():
                        rss_image = img
                # media:thumbnail
                if not rss_image:
                    mt = item.find(f'{{{MEDIA_NS}}}thumbnail')
                    if mt is not None and mt.get('url'):
                        img = mt.get('url', '')
                        if img and 'google' not in img.lower():
                            rss_image = img
                # enclosure
                if not rss_image:
                    enc = item.find('enclosure')
                    if enc is not None and enc.get('url'):
                        img = enc.get('url', '')
                        if img and 'google' not in img.lower():
                            rss_image = img

                # RSS画像がなければ実際の記事URLを取得してog:imageを探す
                image_url = rss_image
                if not image_url and link:
                    # Google News URLをデコードして実際の記事URLを取得
                    real_url = decode_google_news_url(link)
                    # デコードできた場合のみ画像を取得（news.google.comのままならGEアイコンになるのでスキップ）
                    if "news.google.com" not in real_url:
                        image_url = fetch_ogp_image(real_url)

                results.append({
                    "title": title,
                    "content": title,  # RSSは本文が短いためタイトルを代用
                    "author": source,
                    "date": parsed_date,
                    "source_url": link,
                    "source_type": "Google",
                    "image_url": image_url
                })
    except Exception as e:
        print(f"[Crawler Error] RSS Fetch failed for '{query}': {e}")

    return results


def fetch_ogp_image(url: str) -> str:
    """指定URLのPageからOGP(og:image)タグの画像URLを取得する。
    フォールバック順: og:image → twitter:image → 記事内最初のimgタグ
    """
    # Google News / GoogleコメントのURLはスキップ（GEアイコンになるので必ず除外）
    if not url or "news.google.com" in url or url.lower().startswith("https://news.google"):
        return ""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
        'Accept-Language': 'ja,en;q=0.9',
    }
    original_url = url
    try:
        # Google Newsの中間URL(CBMi...)の場合は、本物の記事URLにデコードする
        if "news.google.com" in url:
            try:
                from googlenewsdecoder import new_decoderv1
                decoded_res = new_decoderv1(url)
                if decoded_res.get("status") and decoded_res.get("decoded_url"):
                    url = decoded_res["decoded_url"]
            except Exception:
                pass  # パッケージ無しやエラー時はそのままフォールバック

        if HAS_REQUESTS:
            r = req_lib.get(url, headers=headers, timeout=8, allow_redirects=True)
            html = r.text
            # 実際のリダイレクト先URLを取得（相対URL解決に使う）
            final_url = r.url
        else:
            req_obj = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req_obj, timeout=8) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
                final_url = resp.url

        # ベースURLを取得（相対URLの解決用）
        try:
            from urllib.parse import urlparse, urljoin
            parsed = urlparse(final_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            base_url = ""

        def normalize_img_url(img_url: str) -> str:
            """画像URLを正規化（相対URLを絶対URLに変換）"""
            img_url = img_url.strip()
            if img_url.startswith('http'):
                return img_url
            elif img_url.startswith('//'):
                return 'https:' + img_url
            elif img_url.startswith('/') and base_url:
                return base_url + img_url
            return ""

        # --- 1. og:image を試みる ---
        match = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](.*?)["\']',
            html, re.IGNORECASE
        )
        if not match:
            match = re.search(
                r'<meta[^>]+content=["\'](.*?)["\'][^>]+property=["\']og:image["\']',
                html, re.IGNORECASE
            )
        if match:
            img_url = normalize_img_url(match.group(1))
            if img_url and "google.com" not in img_url:
                return img_url

        # --- 2. twitter:image を試みる ---
        match = re.search(
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\'](.*?)["\']',
            html, re.IGNORECASE
        )
        if not match:
            match = re.search(
                r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']twitter:image["\']',
                html, re.IGNORECASE
            )
        if match:
            img_url = normalize_img_url(match.group(1))
            if img_url and "google.com" not in img_url:
                return img_url

        # --- 3. 記事本文内の最初の<img>タグを試みる ---
        # Google広告・アイコン・1px用トラッキングピクセル等を除外するため
        # src が http(s)で始まり、サイズが小さすぎないものを優先
        img_matches = re.findall(
            r'<img[^>]+src=["\']([^"\'<>]+)["\'][^>]*>',
            html, re.IGNORECASE
        )
        for src in img_matches:
            img_url = normalize_img_url(src)
            if not img_url:
                continue
            # 除外条件: トラッキングピクセル・アイコン・google系を除く
            lower = img_url.lower()
            if any(skip in lower for skip in ['google', 'gstatic', 'doubleclick', 'adsystem',
                                               'blank', 'spacer', 'pixel', '1x1', 'icon',
                                               'favicon', 'logo', 'avatar', 'gravatar']):
                continue
            # 拡張子チェック（画像らしいURLを優先）
            if any(lower.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                return img_url
            # 拡張子がなくても画像ホスティングサービスのURLはOK
            if any(host in lower for host in ['images.', 'img.', 'cdn.', 'media.', 'assets.',
                                               'photo', 'image', 'pics', 'static']):
                return img_url

    except Exception:
        pass  # 画像取得失敗はサイレントにスキップ
    return ""

def get_random_target():
    """テーブルからランダム（または古い順等）に収集ターゲットを取得"""
    conn = database.get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT name_ja FROM anime_targets WHERE enabled=1 ORDER BY RANDOM() LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row["name_ja"] if row else None

def process_target(title: str):
    """指定されたタイトルで検索し、フィルタ＆DB保存を行う"""
    print(f"\n[Crawler] 🔍 対象: {title}")
    
    # 検索クエリ構築: タイトルを含みつつ、グッズ・コラボ・アニメなどのいずれかが入っている記事を探す
    # Google Newsでは "AND" は不要（スペースでAND扱いされる）。また広く拾うために「アニメ」「フィギュア」も追加。
    search_query = f'"{title}" (グッズ OR コラボ OR 一番くじ OR カフェ OR ポップアップ OR 予約 OR アニメ OR フィギュア)'
    
    raw_items = fetch_google_news(search_query)
    print(f"   -> RSS結果: {len(raw_items)} 件")
    
    if not raw_items:
        return
        
    filtered = goods_filter.filter_items(raw_items)
    print(f"   -> フィルタ通過: {len(filtered)} 件")
    
    from scorer import score_item
    
    saved = 0
    for item in filtered:
        # スコアリング
        scored_item = score_item(dict(item))
        # DB保存
        if database.insert_item(scored_item):
            saved += 1
            # 新規保存時：お気に入りユーザーへ通知フックを発火
            database.notify_favorited_users(title, scored_item)
            
    print(f"   -> DB新規保存: {saved} 件")

def run_crawler():
    print("="*60)
    print(" 🚀 無限サーチ（常駐クローラ）起動")
    print("="*60)
    
    while True:
        try:
            # 1. まず優先検索キューをチェック
            queued_query = database.get_next_from_queue()
            if queued_query:
                print(f"\n[Queue Priority] 🚨 ユーザー検索: {queued_query}")
                process_target(queued_query)
                database.mark_queue_done(queued_query)
            else:
                # 2. キューが空なら既存ターゲットからランダムで巡回
                target = get_random_target()
                if target:
                    process_target(target)
                else:
                    print("[Crawler] ターゲットがいません。10秒待機...")
            
            # APIやRSSのレート制限を避けるためスリープ（キュー処理後は少し短め）
            time.sleep(8 if queued_query else 15)
            
        except KeyboardInterrupt:
            print("\n[Crawler] 終了します。")
            break
        except Exception as e:
            print(f"\n[Crawler Exception] {e}")
            time.sleep(30)

if __name__ == "__main__":
    # goods_infoのDBセットアップ
    database.init_db()
    
    # Python実行時のエンコーディングエラー回避
    sys.stdout.reconfigure(encoding='utf-8')
    run_crawler()
