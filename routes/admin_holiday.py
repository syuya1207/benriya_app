from flask import Blueprint, request, render_template, redirect, url_for, current_app
from linebot.models import TemplateSendMessage, ConfirmTemplate, MessageAction, TextSendMessage
from utils.db_utils import execute_sql
from utils.token_utils import create_token
from linebot import LineBotApi
from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

load_dotenv()
admin_holiday_bp = Blueprint("admin_holiday", __name__)
HOST_URL = os.getenv("HOST_URL")

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)


# ---------------------------------------
# 1. 最初の質問
# ---------------------------------------
def register_store_holiday_form(event, line_user_id):

    sql = "SELECT admin_id FROM admins WHERE admin_line_id = %s"
    rows = execute_sql(sql, (line_user_id,), fetch=True)

    if not rows:
        reply = TextSendMessage(text="管理者として登録されていません。")
        line_bot_api.reply_message(event.reply_token, reply)
        return

    admin_id = rows[0]["admin_id"]

    token = create_token(admin_id=admin_id, ttl_minutes=10)
    current_app.logger.debug(f"DEBUG: token generated: {token}")

    if not token:
        reply = TextSendMessage(text="トークン生成に失敗しました。")
        line_bot_api.reply_message(event.reply_token, reply)
        return

    url = f"{HOST_URL}/admin/holiday?token={token}"

    reply = TextSendMessage(text=f"休日登録フォームはこちら：\n{url}")
    line_bot_api.reply_message(event.reply_token, reply)

# 休日登録フォーム（表示）
@admin_holiday_bp.route("/admin/holiday", methods=["GET"])
def admin_holiday_form():
    token = request.args.get("token")
    print("DEBUG: token from URL:", token)
    logger.debug(f"DEBUG: token from URL: {token}")

    if not token:
        return "トークンがありません。アクセスできません。", 400

    # トークンが有効か確認
    sql = """
        SELECT expires_at 
        FROM auth_tokens 
        WHERE token = %s
    """
    result = execute_sql(sql, (token,), fetch=True)
    logger.debug(f"DEBUG: result from DB: {result}")

    # トークン存在確認
    if not result:
        return "無効なトークンです。", 400

    expires_at = result[0]["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    # 有効期限チェック（UTC-awareで比較）
    now_utc = datetime.now(timezone.utc)
    if now_utc > expires_at:
       execute_sql("DELETE FROM auth_tokens WHERE token = %s", (token,))
       return "トークンの有効期限が切れています。", 400

    # 1. 休日データをDBから取得する（既存の execute_sql を使用）
    sql = "SELECT holiday_date FROM holidays ORDER BY holiday_date ASC"
    holiday_rows = execute_sql(sql, fetch=True)

    # 2. datetimeオブジェクトをJinjaに渡すために文字列に変換（Pythonのリストに格納）
    # (例: '2025-12-25')
    existing_holidays = [row["holiday_date"].strftime("%Y-%m-%d") for row in holiday_rows]

    # HTML表示
    return render_template(
        "admin_holiday_form.html", 
        token=token,
        # 🚨 修正: テンプレートが必要としている変数を渡す
        existing_holidays=existing_holidays 
    )


# フォーム送信処理
@admin_holiday_bp.route("/admin/holiday", methods=["POST"])
def admin_holiday_submit():
    token = request.form.get("token")
    holiday_date = request.form.get("holiday_date")
    note = request.form.get("note", "")

    if not token:
        return "トークンがありません。", 400

    # トークン再チェック
    sql = """
        SELECT expires_at 
        FROM auth_tokens 
        WHERE token = %s
    """
    result = execute_sql(sql, (token,), fetch=True)

    if not result:
        return "無効なトークンです。", 400

    expires_at = result[0]["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    # 有効期限チェック（UTC-awareで比較）
    now_utc = datetime.now(timezone.utc)
    if now_utc > expires_at:
       execute_sql("DELETE FROM auth_tokens WHERE token = %s", (token,))
       return "トークンの有効期限が切れています。", 400

    # holidays に登録
    sql = """
        INSERT INTO holidays (holiday_date, note)
        VALUES (%s, %s)
        ON CONFLICT (holiday_date) DO UPDATE SET note = EXCLUDED.note
    """
    execute_sql(sql, (holiday_date, note))

    # トークン削除（1回だけ有効）
    execute_sql("DELETE FROM auth_tokens WHERE token = %s", (token,))

    return "登録が完了しました！"    