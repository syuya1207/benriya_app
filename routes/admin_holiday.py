from linebot.models import TemplateSendMessage, ConfirmTemplate, MessageAction, TextSendMessage
from utils.db_utils import execute_sql
from utils.token_utils import create_token
from linebot import LineBotApi
import os
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)


# ---------------------------------------
# 1. 最初の質問（はい/いいえ）
# ---------------------------------------
def register_store_holiday_form(event, user_id):

    # ① user_id（LINE ID）から admin_id を取得
    sql = "SELECT admin_id FROM admins WHERE admin_line_id = %s"
    rows = execute_sql(sql, (user_id,), fetch=True)

    if not rows:
        return TextSendMessage(text="管理者として登録されていません。")

    admin_id = rows[0]["admin_id"]

    # ② トークン生成
    token = create_token(admin_id=admin_id, ttl_minutes=10)
    if not token:
        return TextSendMessage(text="トークン生成に失敗しました。")

    # ③ URL 生成
    url = f"https://your-domain.com/admin/holiday?token={token}"

    # ④ URLを直接返信
    reply = TextSendMessage(text=f"休日登録フォームはこちら：\n{url}")
    line_bot_api.reply_message(event.reply_token, reply)