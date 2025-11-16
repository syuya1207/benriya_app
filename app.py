from flask import Flask, request, abort, render_template # ★ render_template を追加
import json
import os
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

import psycopg2
from psycopg2 import extras
from urllib.parse import urlparse
from dotenv import load_dotenv
import datetime 

# 環境変数（.envファイル）を読み込む
load_dotenv()

# import constants
# import tasks


# =========================================================
# 1. 環境変数と認証情報の取得
# =========================================================
SECRET_KEY = os.environ.get('SECRET_KEY') 
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
DATABASE_URL = os.environ.get("DATABASE_URL")
HOST_URL = os.environ.get("HOST_URL") # ★★★ HOST_URL を取得 ★★★


# キーが不足していた場合の致命的なエラーチェック
if not all([LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, DATABASE_URL]):
    print("FATAL ERROR: 必要な環境変数が不足しています。LINE_... または DATABASE_URL を確認してください。")

# 💡 デバッグ用（HOST_URLは正しく取得できています）
print(f"DEBUG: HOST_URL is set to: {HOST_URL}")

# =========================================================
# 2. Flask/SDKの初期化
# =========================================================
app = Flask(__name__)
if SECRET_KEY:
    app.secret_key = SECRET_KEY
else:
    print("WARNING: SECRET_KEY is missing. Session and security features will be disabled.")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


# =========================================================
# 3. Webhookの処理ルート（省略）
# =========================================================
@app.route("/webhook", methods=['POST'])
def webhook_handler():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)

    print("\n--- WEBHOOK REQUEST RECEIVED ---")
    app.logger.info("Request body: " + body) 

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Check your channel secret.")
        abort(400) 

    return 'OK', 200


# =========================================================
# 4. PostgreSQL接続のための汎用関数（省略）
# =========================================================
def execute_sql(sql_query, params=None, fetch=False):
    conn = None
    if not DATABASE_URL:
        return {"error": "DATABASE_URLが設定されていません。"}
        
    try:
        url = urlparse(DATABASE_URL)
        
        conn = psycopg2.connect(
            dbname=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname or None, 
            port=url.port or None 
        )
        cursor = conn.cursor(cursor_factory=extras.DictCursor) 
        cursor.execute(sql_query, params)
        
        if fetch:
            result = cursor.fetchall()
            conn.close()
            return result
        else:
            conn.commit()
            conn.close()
            return {"success": True}
            
    except Exception as e:
        print(f"!!! データベースエラーが発生しました: {e} !!!")
        if conn:
            conn.rollback() 
        return {"error": str(e)}


# =========================================================
# 5. 🚨 メッセージイベント発生時の処理（新規ユーザー認証ロジック）
# =========================================================
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    line_user_id = event.source.user_id
    user_text = event.message.text
    response_text = "コマンドが認識できませんでした。" 
    
    # ----------------------------------------------------
    # 1. ユーザー認証ロジック：ユーザー検索
    # ----------------------------------------------------
    USER_CHECK_SQL = "SELECT user_id FROM users WHERE user_line_id = %s;"
    user_result = execute_sql(USER_CHECK_SQL, params=(line_user_id,), fetch=True)
    
    # ユーザー検索でエラーが発生した場合
    if "error" in user_result:
        response_text = f"🚨 データベースエラーが発生しました。時間を置いてお試しください。"
        print(f"!!! ユーザー検索失敗: {user_result['error']} !!!")
    
    # ユーザーがDBに見つからなかった場合 (新規ユーザー)
    elif not user_result: 
        
        if user_text == "登録": # ★★★ ここでURLを返すロジックが実行されるはず ★★★
            if not HOST_URL:
                response_text = "🚨 設定エラー: フォームURLが設定されていません。"
            else:
                # /register_form は、次のルートで処理される
                registration_url = f"{HOST_URL}/register_form?line_id={line_user_id}" 

                response_text = "ユーザー登録ありがとうございます。\n以下のURLから必要事項を入力してください。\n\n"
                response_text += registration_url
        
        else:
            # 登録誘導メッセージを構築 (変更なし)
            try:
                profile = line_bot_api.get_profile(line_user_id)
                user_line_name = profile.display_name
            except Exception:
                user_line_name = "お客様" 
            
            print(f"新規ユーザーを検出: {user_line_name} ({line_user_id})")
            response_text = "{} さん、こんにちは！\n当サービスのご利用にはユーザー登録が必要です。\n\n『登録』と送っていただくと、登録フォームのURLをお送りします。".format(user_line_name)
    
    # ----------------------------------------------------
    # 2. 既存ユーザーの場合の処理（省略）
    # ----------------------------------------------------
    else:
        # ... 既存ユーザーのロジック ...
        user_id = user_result[0]['user_id']
        response_text = f"ユーザーID: {user_id} の既存ユーザーです。\nメッセージ: '{user_text}' を受け付けました。"
            
    # LINEに応答を返す（省略）
    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=response_text)
        )
        print(f"Reply sent successfully. Text: {response_text}")
    except Exception as e:
        print(f"REPLY API ERROR: {e}")


# =========================================================
# 6. 新しい Flask ルートの追加 (登録フォーム表示用)
# =========================================================
@app.route("/register_form", methods=['GET'])
def display_registration_form():
    """LINEから送られたURLクリック時にフォームを表示する"""
    line_user_id = request.args.get('line_id')
    
    if not line_user_id:
        return "エラー: LINE IDが不足しています。", 400

    # templates/register_form.html をレンダリングし、LINE IDを渡す
    return render_template('register_form.html', line_user_id=line_user_id)