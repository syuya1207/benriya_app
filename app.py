from flask import Flask, request, abort, render_template  # ★ render_template を追加

import json
import os

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    TextMessage,
    TextSendMessage,
    TemplateSendMessage,
    ConfirmTemplate,
    MessageAction,
)

from dotenv import load_dotenv
import datetime

import secrets  # ★ 追加: 安全なトークン生成用
from datetime import datetime, timedelta, timezone
import constants


from utils.db_utils import execute_sql
from utils.validation import parse_and_validate_registration_data
from routes.admin_holiday import register_store_holiday_form
from routes.admin_holiday import admin_holiday_bp

DATABASE_URL = os.environ.get("DATABASE_URL")

# import tasks

# 環境変数（.envファイル）を読み込む
load_dotenv()

# =========================================================
# 1. 環境変数と認証情報の取得
# =========================================================
SECRET_KEY = os.environ.get("SECRET_KEY")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")

HOST_URL = os.environ.get("HOST_URL")  # ★★★ HOST_URL を取得 ★★★

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# キーが不足していた場合の致命的なエラーチェック
if not all([LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, DATABASE_URL]):
    print(
        "FATAL ERROR: 必要な環境変数が不足しています。LINE_... または DATABASE_URL を確認してください。"
    )

# 💡 デバッグ用（HOST_URLは正しく取得できています）
print(f"DEBUG: HOST_URL is set to: {HOST_URL}")


# =========================================================
# 2. Flask/SDKの初期化
# =========================================================
app = Flask(__name__)
app.register_blueprint(admin_holiday_bp)
if SECRET_KEY:
    app.secret_key = SECRET_KEY
else:
    print(
        "WARNING: SECRET_KEY is missing. Session and security features will be disabled."
    )


# =========================================================
# 3. Webhookの処理ルート（省略）
# =========================================================
@app.route("/webhook", methods=["POST"])
def webhook_handler():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    print("\n--- WEBHOOK REQUEST RECEIVED ---")
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Check your channel secret.")
        abort(400)

    return "OK", 200


# ============================================================
# プレ5 まずここを追加（ファイル先頭〜handle_message より上）
# ============================================================



def admin_order_by_user(event, user_id):
    # 後でここにユーザー別注文状況処理を書く
    return "（管理者）テクマクマヤコン：あとで実装"


def admin_daily_status(event, user_id):
    # 後でここに日別集計処理を書く
    return "（管理者）ゆりぴょんチェック：あとで実装"


# ---------------------- 一般ユーザー機能 --------------------
def user_order(event, user_id):
    # 後でここに注文処理を書く
    return "（一般ユーザー）注文機能：あとで実装"


# ---------------------- デフォルト応答 ------------------------
def user_default(event, user_id):
    return "別のメッセージを送ってください"


# ---------------------- ディスパッチ辞書 ----------------------
ADMIN_DISPATCH = {
    "休み": register_store_holiday_form,
    "テクマクマヤコン": admin_order_by_user,
    "ゆりぴょんチェック": admin_daily_status,
}

USER_DISPATCH = {
    "注文": user_order,
}


# =========================================================
# 5. 🚨 メッセージイベント発生時の処理（最終構造：ID状態とキーワードの組み合わせ）
# =========================================================
# ※ 外部で定義された line_bot_api, handler, execute_sql, parse_and_validate_registration_data を使用
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    line_user_id = event.source.user_id
    user_text = event.message.text
    response_text = None

    # DBリセット用のSQL (全体で共有)
    DELETE_SQL = "DELETE FROM registration_states WHERE user_line_id = %s;"

    # ----------------------------------------------------
    # 1. ID 検索とステータス取得 (テーブル検索はここで完了)
    # ----------------------------------------------------
    USER_CHECK_SQL = "SELECT user_id FROM users WHERE user_line_id = %s;"
    user_result = execute_sql(USER_CHECK_SQL, params=(line_user_id,), fetch=True)
    is_user = bool(user_result)

    ADMIN_CHECK_SQL = "SELECT admin_id FROM admins WHERE admin_line_id = %s;"
    admin_result = execute_sql(ADMIN_CHECK_SQL, params=(line_user_id,), fetch=True)
    is_admin = bool(admin_result)

    # DBエラーチェック
    if "error" in user_result or "error" in admin_result:
        response_text = (
            f"🚨 データベースエラーが発生しました。時間を置いてお試しください。"
        )

    # ----------------------------------------------------
    # 2. 応答決定ロジック（ディスパッチ方式）
    # ----------------------------------------------------

    # ⭐ 1. 管理者（ユーザー登録済み）
    if is_user and is_admin:
        handler = ADMIN_DISPATCH.get(user_text)

        if handler:
            response_text = handler(event, line_user_id)
        else:
            # 管理者は一般ユーザー機能も使える→この書き方が違う。
            #ユーザーでもあり管理者でもある者が送った言葉が管理者用でなければユーザー機能や登録フローに移る。
            handler = USER_DISPATCH.get(user_text)
            if handler:
                response_text = handler(event, line_user_id)
            else:
                response_text = user_default(event, line_user_id)

    # ⭐ 2. 一般ユーザー（ユーザー登録済み）
    elif is_user:
        handler = USER_DISPATCH.get(user_text)
        if handler:
            response_text = handler(event, line_user_id)
        else:
            response_text = user_default(event, line_user_id)

    # 2.2B. 未登録ユーザーの処理 (is_userがFalseのすべて)
    else:
        # is_adminが真/偽に関わらず、is_userが偽ならここに入り登録フローを優先する

        # ユーザー名の取得 (LINE Bot APIから取得)
        try:
            profile = line_bot_api.get_profile(line_user_id)
            user_line_name = profile.display_name
        except Exception:
            user_line_name = "お客様"

        # 状態の取得 (登録継続中かチェック)
        STATE_SELECT_SQL = """
        SELECT 
            temp_user_grade, temp_user_class, temp_user_last_name, 
            temp_user_first_name, temp_user_line_name
        FROM registration_states WHERE user_line_id = %s;
        """
        state_result = execute_sql(STATE_SELECT_SQL, params=(line_user_id,), fetch=True)
        state_data = (
            state_result[0] if state_result and "error" not in state_result else None
        )

        # ----------------------------------------------
        # A. 状態レコードが存在する場合（登録継続）
        # ----------------------------------------------
        if state_data:

            temp_data = {
                "grade": state_data.get("temp_user_grade"),
                "class": state_data.get("temp_user_class"),
                "last_name": state_data.get("temp_user_last_name"),
                "first_name": state_data.get("temp_user_first_name"),
            }
            # 'grade'がNoneでないかを見て、データが揃っているか否かを判定（簡略化）
            is_data_filled = temp_data["grade"] is not None

            # --- A-i. 最終確認待ち (データがすべて揃っている場合) ---
            if is_data_filled:

                if user_text.lower() in ["はい", "yes"]:
                    # 最終登録処理 (INSERT users, DELETE state)
                    INSERT_USERS_SQL = """
                    INSERT INTO users (user_line_id, user_grade, user_class, user_last_name, user_first_name, user_line_name)
                    VALUES (%s, %s, %s, %s, %s, %s);
                    """
                    final_reg_result = execute_sql(
                        INSERT_USERS_SQL,
                        (
                            line_user_id,
                            temp_data["grade"],
                            temp_data["class"],
                            temp_data["last_name"],
                            temp_data["first_name"],
                            user_line_name,
                        ),
                    )

                    if "success" in final_reg_result:
                        execute_sql(DELETE_SQL, (line_user_id,))
                        response_text = (
                            f"{user_line_name} さん、ユーザー登録が完了しました！🎉"
                        )
                    else:
                        execute_sql(DELETE_SQL, (line_user_id,))
                        response_text = f"🚨 最終登録処理中にデータベースエラーが発生しました。登録を中断しました。再度**「登録」**と送ってください。"

                else:
                    # 「いいえ」またはその他のメッセージ -> 状態を破棄してリセット
                    execute_sql(DELETE_SQL, (line_user_id,))
                    response_text = (
                        "登録を中断しました。再度**「登録」**と送ってください。"
                    )

            # --- A-ii. データ入力待ち (まだデータが未入力/不足している場合) ---
            else:
                # parse_and_validate_registration_data は外部関数として定義済みと仮定
                validation_result = parse_and_validate_registration_data(user_text)

                if validation_result.get("success"):
                    # 検証成功 -> 個別カラムに保存し、確認メッセージを返す
                    new_temp_data = validation_result.get("data")

                    UPDATE_SQL = """
                    UPDATE registration_states 
                    SET temp_user_grade = %s, temp_user_class = %s, 
                        temp_user_last_name = %s, temp_user_first_name = %s,
                        temp_user_line_name = %s
                    WHERE user_line_id = %s;
                    """
                    execute_sql(
                        UPDATE_SQL,
                        (
                            new_temp_data["grade"],
                            new_temp_data["class"],
                            new_temp_data["last_name"],
                            new_temp_data["first_name"],
                            user_line_name,
                            line_user_id,
                        ),
                    )

                    d = new_temp_data
                    response_text = f"以下の内容で登録しますか？\n"
                    response_text += (
                        f"学年：**{d['grade']}**、クラス：**{d['class']}**\n"
                    )
                    response_text += f"氏名：**{d['last_name']} {d['first_name']}**\n"
                    response_text += "\nよろしければ**「はい」**、やめる場合は「いいえ」と送ってください。"

                else:
                    # 検証失敗 -> 状態を破棄してリセット
                    execute_sql(DELETE_SQL, (line_user_id,))
                    error_message = validation_result.get("error", "入力が不正です。")
                    response_text = f"⚠️ 入力エラー：{error_message}\n\n登録を中断しました。再度**「登録」**と送ってください。"

        # ----------------------------------------------
        # B. 状態レコードがない場合（登録トリガー or 誘導）
        # ----------------------------------------------
        else:
            if user_text == "登録":
                # INSERT_SQL のロジック
                INSERT_SQL = """
                INSERT INTO registration_states (user_line_id) 
                VALUES (%s);
                """
                start_result = execute_sql(INSERT_SQL, (line_user_id,))

                if "success" in start_result:
                    response_text = "登録を開始します。\n\n**学年（1〜3）・クラス・姓・名**をスペース区切りで一度に返信してください。\n例: 2 1 山田 太郎"
                else:
                    response_text = "🚨 登録開始中にデータベースエラーが発生しました。再度「登録」と送ってください。"
            else:
                # 登録誘導メッセージ (管理者キーワードであってもここに来る)
                response_text = f"{user_line_name} さん、ユーザー情報が未登録です。\n登録をご希望の場合は、**「登録」**と送ってください。"

    # ----------------------------------------------------
    # 3. LINEに応答を返す (最終処理)
    # ----------------------------------------------------
    if response_text:
        print("DEBUG:", type(response_text))
        try:
            if isinstance(response_text, TemplateSendMessage):
                line_bot_api.reply_message(event.reply_token, response_text)
            else:
                line_bot_api.reply_message(
                    event.reply_token, TextSendMessage(text=str(response_text))
                )
        except Exception as e:
            print("REPLY ERROR:", e)
            raise e


    return "OK"
