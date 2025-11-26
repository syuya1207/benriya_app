from flask import Blueprint, request, render_template, redirect, url_for
from linebot.models import TemplateSendMessage, ConfirmTemplate, MessageAction, TextSendMessage
from utils.db_utils import execute_sql
from utils.token_utils import create_token
from linebot import LineBotApi
import os
from dotenv import load_dotenv

load_dotenv()
admin_holiday_bp = Blueprint("admin_holiday", __name__)
HOST_URL = os.getenv("HOST_URL")

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)


# ---------------------------------------
# 1. 最初の質問（はい/いいえ）
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

    if not token:
        return "トークンがありません。アクセスできません。", 400

    # トークンが有効か確認
    sql = """
        SELECT expires_at 
        FROM auth_tokens 
        WHERE token = %s
    """
    result = execute_sql(sql, (token,), fetch_one=True)

    # トークン存在確認
    if not result:
        return "無効なトークンです。", 400

    expires_at = result[0]

    # 有効期限チェック
    if datetime.now() > expires_at:
        # 期限切れなら削除
        execute_sql("DELETE FROM auth_tokens WHERE token = %s", (token,))
        return "トークンの有効期限が切れています。", 400

    # HTML表示
    return render_template("admin_holiday_form.html", token=token)


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
    result = execute_sql(sql, (token,), fetch_one=True)

    if not result:
        return "無効なトークンです。", 400

    expires_at = result[0]

    if datetime.now() > expires_at:
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