from flask import Flask, request, abort
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

# ★★★ 外部ファイルのインポート（現在は未実装のためコメントアウト） ★★★
# import constants
# import tasks


# =========================================================
# 1. 環境変数と認証情報の取得
# =========================================================
SECRET_KEY = os.environ.get('SECRET_KEY') 
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
DATABASE_URL = os.environ.get("DATABASE_URL")


# キーが不足していた場合の致命的なエラーチェック
if not all([LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, DATABASE_URL]):
    print("FATAL ERROR: 必要な環境変数が不足しています。LINE_... または DATABASE_URL を確認してください。")
    # 本番環境ではexit(1)などで停止させるべきですが、ここではprintに留めます


# =========================================================
# 2. Flask/SDKの初期化
# =========================================================
app = Flask(__name__)
if SECRET_KEY:
    app.secret_key = SECRET_KEY
else:
    # ユーザー提供コードのWARNINGを維持
    print("WARNING: SECRET_KEY is missing. Session and security features will be disabled.")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

app.logger.info(f"DEBUG: Database URL is set to: {DATABASE_URL}")
# =========================================================
# 3. Webhookの処理ルート
# =========================================================
@app.route("/webhook", methods=['POST'])
def webhook_handler():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)

    print("\n--- WEBHOOK REQUEST RECEIVED ---")
    app.logger.info("Request body: " + body) # 内部ログ

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Check your channel secret.")
        abort(400) 

    return 'OK', 200


# =========================================================
# 4. 🚨 PostgreSQL接続のための汎用関数（DictCursor前提）
# =========================================================

def execute_sql(sql_query, params=None, fetch=False):
    """
    SQLを実行し、結果が必要なら取得する汎用関数 (DictCursorを使用)
    """
    conn = None
    if not DATABASE_URL:
        return {"error": "DATABASE_URLが設定されていません。"}
        
    try:
        url = urlparse(DATABASE_URL)
        
        # 接続確立
        conn = psycopg2.connect(
            dbname=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname or None, 
            port=url.port or None 
        )
        # DictCursorを使用するため、結果は辞書形式で返る
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
    # 1. ユーザー認証ロジック：LINE IDの存在確認
    # ----------------------------------------------------
    USER_CHECK_SQL = "SELECT user_id FROM users WHERE user_line_id = %s;"
    user_result = execute_sql(USER_CHECK_SQL, params=(line_user_id,), fetch=True)
    
    # ユーザー検索でエラーが発生した場合
    if "error" in user_result:
        response_text = f"🚨 データベースエラーが発生しました。時間を置いてお試しください。"
        print(f"!!! ユーザー検索失敗: {user_result['error']} !!!")
    
    # ユーザーがDBに見つからなかった場合 (新規ユーザー)
    elif not user_result: 
        
        # LINE Profile APIからユーザー名を取得
        try:
            profile = line_bot_api.get_profile(line_user_id)
            user_line_name = profile.display_name
        except Exception:
            user_line_name = "お客様" # 取得失敗時のフォールバック
        
        # 登録誘導メッセージを構築
        print(f"新規ユーザーを検出: {user_line_name} ({line_user_id})")
        response_text = "{} さん、こんにちは！\n当サービスのご利用にはユーザー登録が必要です。\n\n『登録』と送っていただくと、登録フォームのURLをお送りします。".format(user_line_name)
    
    # ----------------------------------------------------
    # 2. 既存ユーザーの場合の処理（今後の実装箇所）
    # ----------------------------------------------------
    else:
        # user_result は辞書のリスト ([{'user_id': 123}]) なので、キーでIDを取得
        user_id = user_result[0]['user_id']
        
        # ★★★ 既存のDBテストロジックの保持 ★★★
        if user_text == "DBテスト":
            sql = "SELECT version();"
            result = execute_sql(sql, fetch=True)
            response_text = f"✅ DB接続成功！\nバージョン情報:\n{result[0]['version']}" if not "error" in result else f"🚨 DB接続失敗。\nエラー: {result['error']}"
        
        else:
            # 既存ユーザーのメッセージ処理本体（セッション管理や注文処理など）
            response_text = f"ユーザーID: {user_id} の既存ユーザーです。\nメッセージ: '{user_text}' を受け付けました。"

            
    # LINEに応答を返す
    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=response_text)
        )
        print(f"Reply sent successfully. Text: {response_text}")
    except Exception as e:
        print(f"REPLY API ERROR: {e}")