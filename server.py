import os
import sys
import sqlite3
import csv
from flask import Flask, jsonify, request, send_from_directory, Response, send_file, redirect, session
from flask_cors import CORS
import uuid
import hashlib
import time
import random
import urllib.parse

# メール配信用モジュール
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import database
from scorer import score_all

# サーバー起動時にDBテーブルを自動作成（存在しない場合のみ）
database.init_db()

app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "web"))
app.secret_key = os.getenv("FLASK_SECRET_KEY", "animation-roastery-secret-key-dev")
CORS(app, supports_credentials=True)

# ブラウザの強力なキャッシュを回避
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, public, max-age=0"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    return r

# 簡易的なインメモリセッションストア (token -> user_id)
# ※本来はDBやRedis、または標準のJWT等を用いますがプロトタイプ実装のためメモリ管理
SESSION_STORE = {}

# 二段階認証用のOTPストア (email -> {otp: "123456", expires: 123456789, id: user_id})
import time
import random
OTP_STORE = {}
REGISTRATION_STORE = {} # 新規登録（仮登録）用ストア

def get_current_user_id():
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ")[1]
    return SESSION_STORE.get(token)

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def generate_otp():
    return str(random.randint(100000, 999999))

def send_otp_email(to_email, otp, is_registration=False):
    mail_username = os.getenv("MAIL_USERNAME")
    mail_password = os.getenv("MAIL_PASSWORD")
    
    if not mail_username or not mail_password or "ここ" in mail_password:
        raise ValueError("SMTP configuration is missing or incomplete in .env file.")
        
    subject = "【Animation Roastery】アカウント本登録の認証コード" if is_registration else "【Animation Roastery】ログイン用認証コード"
    
    body = f"""
Animation Roastery をご利用いただきありがとうございます。

以下の6桁の認証コードを画面に入力してください。
----------------------------------------
認証コード: {otp}
----------------------------------------

※このコードの有効期限は5分間です。
※お心当たりのない場合は、このメールを破棄してください。
    """
    
    msg = MIMEMultipart()
    msg['From'] = mail_username
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(mail_username, mail_password)
    server.send_message(msg)
    server.quit()

# ─── API: Auth ────────────────────────────────────────────────
@app.route("/api/auth/register", methods=["POST"])
def api_auth_register():
    data = request.json
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    
    if not email or not password:
        return jsonify({"status": "error", "message": "Email and Password are required"}), 400

    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email=?", (email,))
    existing = c.fetchone()
    conn.close()
    
    if existing:
        return jsonify({"status": "error", "message": "Email already exists"}), 400
        
    otp = generate_otp()
    
    # 実際のメール送信を試みる
    try:
        send_otp_email(email, otp, is_registration=True)
    except Exception as e:
        print(f"[SMTP Error] {e}")
        return jsonify({"status": "error", "message": "Failed to send verification email. Please try again later or contact support."}), 500

    REGISTRATION_STORE[email] = {
        "otp": otp,
        "password_hash": hash_password(password),
        "expires": time.time() + 300 # 5分有効
    }
    
    return jsonify({"status": "verification_required", "email": email, "message": "Verification code sent to email"})

@app.route("/api/auth/verify_registration", methods=["POST"])
def api_auth_verify_registration():
    data = request.json
    email = data.get("email", "").strip()
    otp_input = data.get("otp", "").strip()
    
    reg_data = REGISTRATION_STORE.get(email)
    if not reg_data:
        return jsonify({"status": "error", "message": "Registration session not found or expired"}), 400
        
    if time.time() > reg_data["expires"]:
        del REGISTRATION_STORE[email]
        return jsonify({"status": "error", "message": "Verification code has expired"}), 400
        
    if reg_data["otp"] == otp_input:
        conn = database.get_db_connection()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (email, reg_data["password_hash"]))
            conn.commit()
            user_id = c.lastrowid
            
            token = str(uuid.uuid4())
            SESSION_STORE[token] = user_id
            del REGISTRATION_STORE[email]
            return jsonify({"status": "ok", "token": token, "email": email})
        except database.get_integrity_error():
            return jsonify({"status": "error", "message": "Email already exists"}), 400
        finally:
            conn.close()
    else:
        return jsonify({"status": "error", "message": "Invalid verification code"}), 401

@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    data = request.json
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, password_hash FROM users WHERE email=?", (email,))
    user = c.fetchone()
    conn.close()
    
    if user and user[1] == hash_password(password):
        # 2FA: トークンを即座に発行せず、OTPを生成して保持する
        otp = generate_otp()
        
        # 実際のメール送信を試みる
        try:
            send_otp_email(email, otp, is_registration=False)
        except Exception as e:
            print(f"[SMTP Error] {e}")
            return jsonify({"status": "error", "message": "Failed to send 2FA email. Please try again later."}), 500

        OTP_STORE[email] = {
            "otp": otp,
            "expires": time.time() + 300, # 5分間有効
            "id": user[0]
        }
        
        return jsonify({"status": "2fa_required", "email": email, "message": "OTP sent to your email"})
    else:
        return jsonify({"status": "error", "message": "Invalid email or password"}), 401

@app.route("/api/auth/verify_otp", methods=["POST"])
def api_auth_verify_otp():
    data = request.json
    email = data.get("email", "").strip()
    otp_input = data.get("otp", "").strip()
    
    auth_data = OTP_STORE.get(email)
    if not auth_data:
        return jsonify({"status": "error", "message": "OTP session not found or expired"}), 400
        
    if time.time() > auth_data["expires"]:
        del OTP_STORE[email]
        return jsonify({"status": "error", "message": "OTP has expired"}), 400
        
    if auth_data["otp"] == otp_input:
        # 認証成功、トークンを発行
        user_id = auth_data["id"]
        token = str(uuid.uuid4())
        SESSION_STORE[token] = user_id
        del OTP_STORE[email] # 使用済みOTPを破棄
        return jsonify({"status": "ok", "token": token, "email": email})
    else:
        return jsonify({"status": "error", "message": "Invalid OTP code"}), 401

@app.route("/api/auth/social_login", methods=["POST"])
def social_login():
    data = request.get_json()
    provider = data.get("provider") # "google", "x", "line" etc.
    email = data.get("email")
    # user_id from social provider is not directly used for our internal user_id,
    # but can be stored in a separate table for linking if needed.
    
    if not provider or not email:
        return jsonify({"status": "error", "message": "Provider or email missing"}), 400
        
    conn = database.get_db_connection()
    c = conn.cursor()
    try:
        # 既存ユーザーか確認
        c.execute("SELECT id, email FROM users WHERE email=?", (email,))
        user = c.fetchone()
        
        if user:
            # トークン発行してログイン
            token = str(uuid.uuid4())
            SESSION_STORE[token] = user[0]
            return jsonify({"status": "ok", "token": token, "email": email, "message": f"Logged in with {provider}"})
        else:
            # ユーザーが存在しない場合は自動作成
            random_password_hash = hash_password(str(uuid.uuid4())) # Generate a random password hash for social users
            try:
                c.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (email, random_password_hash))
                conn.commit()
                new_user_id = c.lastrowid
                
                token = str(uuid.uuid4())
                SESSION_STORE[token] = new_user_id
                return jsonify({"status": "ok", "token": token, "email": email, "message": f"Account created and logged in with {provider}"})
            except database.get_integrity_error():
                return jsonify({"status": "error", "message": "Failed to create account (email might already exist)"}), 500
    finally:
        conn.close()

@app.route("/api/auth/social/login/<provider>", methods=["GET"])
def social_login_redirect(provider):
    """各SNSのOAuth認証画面へリダイレクトする入り口
    APIキーが設定済み関は本物のOAuth、未設定ならモックモードにフォールバック
    """
    # --- Google ---
    if provider == "google":
        client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        if client_id:
            # 本物のGoogle OAuth 2.0
            redirect_url = os.getenv("APP_BASE_URL", "http://localhost:5000") + "/api/auth/social/callback/google"
            state = str(uuid.uuid4())
            session['oauth_state'] = state
            params = urllib.parse.urlencode({
                "client_id": client_id,
                "redirect_uri": redirect_url,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "access_type": "offline",
            })
            return redirect(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")
        else:
            # モックフロー: デモ用メールを作成して直接ログイン
            return _mock_social_login_redirect(provider)

    # --- X (Twitter / OAuth 2.0 PKCE) ---
    elif provider == "x":
        client_id = os.getenv("X_CLIENT_ID", "")
        if client_id:
            redirect_url = os.getenv("APP_BASE_URL", "http://localhost:5000") + "/api/auth/social/callback/x"
            state = str(uuid.uuid4())
            session['oauth_state'] = state
            params = urllib.parse.urlencode({
                "client_id": client_id,
                "redirect_uri": redirect_url,
                "response_type": "code",
                "scope": "tweet.read users.read offline.access",
                "state": state,
                "code_challenge": "challenge",
                "code_challenge_method": "plain",
            })
            return redirect(f"https://twitter.com/i/oauth2/authorize?{params}")
        else:
            return _mock_social_login_redirect(provider)

    # --- LINE ---
    elif provider == "line":
        client_id = os.getenv("LINE_CLIENT_ID", "")
        if client_id:
            redirect_url = os.getenv("APP_BASE_URL", "http://localhost:5000") + "/api/auth/social/callback/line"
            state = str(uuid.uuid4())
            session['oauth_state'] = state
            params = urllib.parse.urlencode({
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_url,
                "state": state,
                "scope": "profile openid email",
            })
            return redirect(f"https://access.line.me/oauth2/v2.1/authorize?{params}")
        else:
            return _mock_social_login_redirect(provider)

    else:
        return jsonify({"status": "error", "message": "Unknown provider"}), 400


def _mock_social_login_redirect(provider: str):
    """APIキー未設定時のモックフロー: デモメールで即時ログインし、トークン付リでTOPページへ滝す"""
    mock_email = f"demo_{provider}_{random.randint(1000, 9999)}@example.com"
    token = str(uuid.uuid4())
    conn = database.get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT id FROM users WHERE email=?", (mock_email,))
        user = c.fetchone()
        if user:
            SESSION_STORE[token] = user[0]
        else:
            pw_hash = hash_password(str(uuid.uuid4()))
            c.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (mock_email, pw_hash))
            conn.commit()
            SESSION_STORE[token] = c.lastrowid
    except Exception:
        session['mock_error'] = True
    finally:
        conn.close()
    # トークンとメールをURLパラメータで渡す
    base_url = os.getenv("APP_BASE_URL", "http://localhost:5000")
    return redirect(f"{base_url}/?token={token}&email={urllib.parse.quote(mock_email)}&provider={provider}")


@app.route("/api/auth/social/callback/<provider>", methods=["GET"])
def social_callback(provider):
    """各SNSのOAuth認証が完了し、コールバックされる受け皿エンドポイント"""
    import requests as rq
    
    code = request.args.get("code", "")
    state = request.args.get("state", "")
    error = request.args.get("error")
    base_url = os.getenv("APP_BASE_URL", "http://localhost:5000")
    
    if error:
        return redirect(f"{base_url}/?social_error={error}")

    try:
        sns_email = ""
        provider_user_id = ""
        display_name = ""

        if provider == "google":
            redirect_url = base_url + "/api/auth/social/callback/google"
            token_res = rq.post("https://oauth2.googleapis.com/token", data={
                "code": code,
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "redirect_uri": redirect_url,
                "grant_type": "authorization_code",
            })
            token_json = token_res.json()
            user_info_res = rq.get("https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {token_json.get('access_token')}"}
            )
            user_info = user_info_res.json()
            sns_email = user_info.get("email", "")
            provider_user_id = user_info.get("sub", "")
            display_name = user_info.get("name", "")

        elif provider == "x":
            redirect_url = base_url + "/api/auth/social/callback/x"
            token_res = rq.post("https://api.twitter.com/2/oauth2/token", data={
                "code": code,
                "grant_type": "authorization_code",
                "client_id": os.getenv("X_CLIENT_ID"),
                "redirect_uri": redirect_url,
                "code_verifier": "challenge",
            }, auth=(os.getenv("X_CLIENT_ID"), os.getenv("X_CLIENT_SECRET")))
            access_token = token_res.json().get("access_token", "")
            user_info_res = rq.get("https://api.twitter.com/2/users/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user_data = user_info_res.json().get("data", {})
            provider_user_id = user_data.get("id", "")
            display_name = user_data.get("username", "x_user")
            sns_email = f"{display_name}@x.social"

        elif provider == "line":
            redirect_url = base_url + "/api/auth/social/callback/line"
            token_res = rq.post("https://api.line.me/oauth2/v2.1/token", data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_url,
                "client_id": os.getenv("LINE_CLIENT_ID"),
                "client_secret": os.getenv("LINE_CLIENT_SECRET"),
            })
            token_data = token_res.json()
            access_token = token_data.get("access_token", "")
            
            # プロフィール取得（userIdとdisplayName）
            profile_res = rq.get("https://api.line.me/v2/profile",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            profile_data = profile_res.json()
            provider_user_id = profile_data.get("userId", "")
            display_name = profile_data.get("displayName", "LINE User")
            
            # LINE は emailスコープが別途審査が必要なため、userIdベースのIDを使用
            sns_email = f"{provider_user_id}@line.social"
        else:
            return jsonify({"status": "error", "message": "Unknown provider"}), 400

        if not provider_user_id and not sns_email:
            return redirect(f"{base_url}/?social_error=no_user_info")

        # 共通処理: social_accounts テーブル優先 → fallback で email で検索
        conn = database.get_db_connection()
        c = conn.cursor()
        try:
            # social_accountsテーブルがなければ作成
            c.execute('''
                CREATE TABLE IF NOT EXISTS social_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    provider TEXT NOT NULL,
                    provider_user_id TEXT NOT NULL,
                    display_name TEXT,
                    UNIQUE(provider, provider_user_id)
                )
            ''')
            conn.commit()

            # 1. provider_user_id で既存紐付けを探す
            user_id_db = None
            if provider_user_id:
                c.execute("SELECT user_id FROM social_accounts WHERE provider=? AND provider_user_id=?",
                          (provider, provider_user_id))
                row = c.fetchone()
                if row:
                    user_id_db = row[0]

            # 2. なければ email で検索
            if user_id_db is None and sns_email:
                c.execute("SELECT id FROM users WHERE email=?", (sns_email,))
                row = c.fetchone()
                if row:
                    user_id_db = row[0]

            # 3. 全く新規ならユーザー作成
            if user_id_db is None:
                pw_hash = hash_password(str(uuid.uuid4()))
                c.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (sns_email, pw_hash))
                conn.commit()
                user_id_db = c.lastrowid

            # 4. social_accounts に紐付けを保存/更新
            if provider_user_id:
                c.execute('''
                    INSERT INTO social_accounts (user_id, provider, provider_user_id, display_name)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(provider, provider_user_id) DO UPDATE SET display_name=excluded.display_name
                ''', (user_id_db, provider, provider_user_id, display_name))
                conn.commit()

            token = str(uuid.uuid4())
            SESSION_STORE[token] = user_id_db

            # 表示メールを取得
            c.execute("SELECT email FROM users WHERE id=?", (user_id_db,))
            row = c.fetchone()
            show_email = row[0] if row else sns_email
        finally:
            conn.close()

        return redirect(f"{base_url}/?token={token}&email={urllib.parse.quote(show_email)}&provider={provider}&name={urllib.parse.quote(display_name)}")

    except Exception as e:
        print(f"[OAuth Callback Error] {provider}: {e}")
        import traceback; traceback.print_exc()
        return redirect(f"{base_url}/?social_error=callback_failed")



@app.route("/api/auth/me", methods=["GET"])
def api_auth_me():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    conn.close()
    return jsonify({"status": "ok", "email": user[0]})

# ─── API: Favorites ──────────────────────────────────────────
@app.route("/api/favorites", methods=["GET", "POST", "DELETE"])
def api_favorites():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    conn = database.get_db_connection()
    c = conn.cursor()
    
    if request.method == "GET":
        c.execute("SELECT anime_title FROM favorites WHERE user_id=?", (user_id,))
        favs = [row[0] for row in c.fetchall()]
        conn.close()
        return jsonify({"status": "ok", "favorites": favs})
        
    if request.method == "POST":
        title = request.json.get("anime_title", "").strip()
        if not title:
            conn.close()
            return jsonify({"status": "error", "message": "Title required"}), 400
        try:
            c.execute("INSERT INTO favorites (user_id, anime_title) VALUES (?, ?)", (user_id, title))
            conn.commit()
            return jsonify({"status": "ok", "message": f"Added {title} to favorites"})
        except database.get_integrity_error():
            return jsonify({"status": "ok", "message": "Already in favorites"})
        finally:
            conn.close()
            
    if request.method == "DELETE":
        title = request.json.get("anime_title", "").strip()
        c.execute("DELETE FROM favorites WHERE user_id=? AND anime_title=?", (user_id, title))
        conn.commit()
        conn.close()
        return jsonify({"status": "ok", "message": f"Removed {title} from favorites"})

# ─── API: 情報一覧 ─────────────────────────────────────────────
@app.route("/api/items", methods=["GET"])
def api_items():
    title_filter    = request.args.get("title")
    source_filter   = request.args.get("source")
    category_filter = request.args.get("category")
    sort_by         = request.args.get("sort", "date")  # date | score
    items = database.get_all_items(title_filter, source_filter, category_filter)

    # スコアが未設定のアイテムにリアルタイムスコアリング
    for item in items:
        if not item.get("total_score"):
            from scorer import score_item
            scored = score_item(dict(item))
            item.update(scored)

    # スコア順ソート
    if sort_by == "score":
        items.sort(key=lambda x: x.get("total_score", 0), reverse=True)

    return jsonify({"status": "ok", "count": len(items), "items": items})

# ─── API: 作品名一覧 ────────────────────────────────────────────
@app.route("/api/titles", methods=["GET"])
def api_titles():
    conn = database.get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT DISTINCT title FROM goods_info ORDER BY title")
    titles = [r["title"] for r in c.fetchall()]
    conn.close()
    return jsonify({"titles": titles})

# ─── API: カテゴリ一覧 ──────────────────────────────────────────
@app.route("/api/categories", methods=["GET"])
def api_categories():
    conn = database.get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT DISTINCT category FROM goods_info ORDER BY category")
    cats = [r["category"] for r in c.fetchall()]
    conn.close()
    return jsonify({"categories": cats})

# ─── API: 追跡作品数（anime_targetsテーブル） ──────────────────
@app.route("/api/targets", methods=["GET"])
def api_targets():
    conn = database.get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT COUNT(*) FROM anime_targets WHERE enabled=1")
        count = c.fetchone()[0]
        c.execute("SELECT name_ja, genre FROM anime_targets WHERE enabled=1 ORDER BY name_ja")
        rows = c.fetchall()
        targets = [{"name": r[0], "genre": r[1]} for r in rows]
    except sqlite3.OperationalError:
        count = 0
        targets = []
    conn.close()
    return jsonify({"count": count, "targets": targets})

# ─── API: 優先度上位のみ取得 ───────────────────────────────────
@app.route("/api/urgent", methods=["GET"])
def api_urgent():
    items = database.get_all_items()
    scored = score_all(items)
    urgent = [i for i in scored if i.get("total_score", 0) >= 55]
    return jsonify({"status": "ok", "count": len(urgent), "items": urgent})

# ─── API: 新規検索・自動追加リクエスト ───────────────────────
@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.json
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"status": "error", "message": "検索キーワードが空です"}), 400

    # anime_targets テーブルに存在しない場合は追加して追跡対象にする
    conn = database.get_db_connection()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO anime_targets (name_ja, name_en, genre, reason)
            VALUES (?, ?, ?, ?)
        ''', (query, "", "ユーザー追加", "UIからの手動検索"))
        conn.commit()
    except database.get_integrity_error():
        pass # 既に存在
    finally:
        conn.close()

    # 検索キューに追加してクローラの優先順位を上げる
    database.add_to_search_queue(query)
    
    return jsonify({"status": "ok", "message": f"「{query}」をキューに追加しました"})

# ─── CSVエクスポート ──────────────────────────────────────
@app.route("/api/export", methods=["GET"])
def api_export():
    export_path = os.path.join(BASE_DIR, "export.csv")
    database.export_csv(export_path)
    with open(export_path, "r", encoding="utf-8-sig") as f:
        content = f.read()
    return Response(
        content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=goods_info.csv"}
    )

# ─── 静的ファイル ──────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(app.static_folder, path)

# ─── 起動 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
            
    database.init_db()
    # DB拡張（スコアカラムが未追加の場合に追加）
    try:
        from setup_targets import upgrade_goods_table
        upgrade_goods_table()
    except Exception as e:
        print(f"[Server] DBアップグレードをスキップ: {e}")
    print("[Server] http://localhost:5000 で起動中...")
    app.run(host="0.0.0.0", port=5000, debug=False)
