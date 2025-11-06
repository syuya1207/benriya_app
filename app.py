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
load_dotenv()

import constants
import tasks

app = Flask(__name__)

SECRET_KEY = os.environ.get('SECRET_KEY') # ★★★ 追加: SECRET_KEYを明示的に取得 ★★★
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
DATABASE_URL = os.environ.get("DATABASE_URL")





# キーが不足していた場合の致命的なエラーチェック
if not all([LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, DATABASE_URL]):
    print("FATAL ERROR: 必要な環境変数が不足しています。LINE_... または DATABASE_URL を確認してください。")


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
# 3. Webhookの処理ルート（変更なし）
# =========================================================
@app.route("/webhook", methods=['POST'])
def webhook_handler():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)

    print("\n--- WEBHOOK REQUEST RECEIVED ---")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Check your channel secret.")
        abort(400) 

    return 'OK', 200


# =========================================================
# 4. 🚨 PostgreSQL接続のための汎用関数（新規追加）
# =========================================================

def execute_sql(sql_query, params=None, fetch=False):
    """
    SQLを実行し、結果が必要なら取得する汎用関数
    """
    conn = None
    if not DATABASE_URL:
        return {"error": "DATABASE_URLが設定されていません。"}
        
    try:
        url = urlparse(DATABASE_URL)
        
        # 接続確立: ポート番号を省略した形式（UNIXソケット接続を意図）
        conn = psycopg2.connect(
            dbname=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname or None,  # ホスト名が空の場合 None を渡す
            port=url.port or None       # ポート番号が空の場合 None を渡す
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
# 5. 🚨 メッセージイベント発生時の処理（DB機能に置換）
# =========================================================
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text
    response_text = "コマンドが認識できませんでした。" # デフォルトの応答
    
    # 🚨 DB接続テストコマンドのチェック
    if user_text == "DBテスト":
        # 接続が成功するか、簡単なSQLで確認（DBバージョン取得）
        sql = "SELECT version();"
        result = execute_sql(sql, fetch=True)
        
        if "error" in result:
            # 接続エラーの場合
            response_text = f"🚨 DB接続に失敗しました。\nエラー: {result['error']}"
        else:
            # 接続成功の場合
            response_text = f"✅ DB接続成功！\nバージョン情報:\n{result[0][0]}"
            
    # 🚨 オウム返しロジックはここで完全に削除されています。
    #    「DBテスト」以外のメッセージは、デフォルト応答（「コマンドが認識できませんでした。」）になります。
    
    
    # LINEに応答を返す
    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=response_text)
        )
        print(f"Reply sent successfully. Text: {response_text}")
    except Exception as e:
        print(f"REPLY API ERROR: {e}")