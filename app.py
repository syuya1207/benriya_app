from flask import Flask, request, abort, render_template # ★ render_template を追加
import re             # 正規表現処理用
import unicodedata    # 全角・半角変換用
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

import secrets # ★ 追加: 安全なトークン生成用
from datetime import datetime, timedelta # ★ 修正: timedelta を追加

import constants
# import tasks

# 環境変数（.envファイル）を読み込む
load_dotenv()

# =========================================================
# 1. 環境変数と認証情報の取得
# =========================================================
SECRET_KEY = os.environ.get('SECRET_KEY') 
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
DATABASE_URL = os.environ.get("DATABASE_URL")
HOST_URL = os.environ.get("HOST_URL") # ★★★ HOST_URL を取得 ★★★

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

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
        
        # ✅ 修正点 1: autocommit を有効化し、ロック待ちによるフリーズを回避
        conn.set_session(autocommit=True)
        
        cursor = conn.cursor(cursor_factory=extras.DictCursor) 
        cursor.execute(sql_query, params)
        
        if fetch:
            result = cursor.fetchall()
            # conn.commit() は autocommit=True のため削除
            return result
        else:
            # conn.commit() は autocommit=True のため削除
            return {"success": True}
            
    except Exception as e:
        print(f"!!! データベースエラーが発生しました: {e} !!!")
        print(f"!!! 実行失敗クエリ: {sql_query}") 
        if conn:
            # autocommit=True のため rollback は効果が薄いが、念のため残す
            conn.rollback() 
        return {"error": str(e)}

    # ✅ 修正点 2: 成功・失敗にかかわらず、接続を確実に閉じる (finallyブロック)
    finally:
        if conn:
            try:
                conn.close()
            except Exception as close_e:
                # 接続クローズエラーは致命的ではないため、printのみ
                print(f"!!! 接続クローズエラー: {close_e} !!!")

# =========================================================
#★ 新規ユーザー登録のためのデータ検証関数
# =========================================================

def parse_and_validate_registration_data(user_text):
    """
    ユーザー入力をパースし、指定された厳格なルールで検証する
    """
    
    # 1. 前処理: 全角スペースを半角に変換し、連続するスペースを1つにまとめる
    normalized_text = user_text.replace("　", " ").strip()
    
    # 【検証 1: 分割と要素数のチェック】
    # 複数のスペースを1つのスペースに置き換え、分割する
    parts = re.split(r'\s+', normalized_text)
    
    if len(parts) != 4:
        return {"error": "入力された情報が不足しています。**学年・クラス・姓・名**をすべてスペース区切りで入力してください。"}
    
    grade, user_class, last_name, first_name = parts
    
    # 【検証 2: 学年とクラスの厳格なチェック（「年」や「組」の混入防止）】
    
    # 学年 (1〜3の数字)
    grade_num_str = unicodedata.normalize('NFKC', grade) # 全角数字を半角に
    if not grade_num_str.isdigit() or not (1 <= int(grade_num_str) <= 3):
        return {"error": "学年は1から3の数字のみを入力してください。（例: '2'）"}
    
    # クラス (数字のみ)
    user_class_num_str = unicodedata.normalize('NFKC', user_class) # 全角数字を半角に
    if not user_class_num_str.isdigit():
        return {"error": "クラスは数字のみを入力してください。（例: 'A'ではなく'1'）"}
    
    # 【検証 3: 姓・名のチェック（数字、記号の禁止）】
    # 漢字、ひらがな、カタカナ、英字以外を禁止する正規表現
    # ただし、姓や名が空の場合は弾く
    name_pattern = re.compile(r'^[ぁ-んァ-ヶ一-龠a-zA-Z]+$')
    
    if not name_pattern.match(last_name):
        return {"error": f"姓（{last_name}）に数字や記号を含めることはできません。文字のみで入力してください。"}

    if not name_pattern.match(first_name):
        return {"error": f"名（{first_name}）に数字や記号を含めることはできません。文字のみで入力してください。"}
    
    # 検証にすべて成功した場合
    return {
        "success": True,
        "data": {
            "grade": int(grade_num_str),
            "class": int(user_class_num_str),
            "last_name": last_name,
            "first_name": first_name
        }
    }        

# =========================================================
# 5. 🚨 メッセージイベント発生時の処理（新規ユーザー認証ロジック）
# =========================================================
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    line_user_id = event.source.user_id
    user_text = event.message.text
    response_text = None 
    
    # DBリセット用のSQL (全体で共有)
    DELETE_SQL = "DELETE FROM registration_states WHERE user_line_id = %s;"
    
    # ----------------------------------------------------
    # 1. ユーザー認証ロジック：usersテーブルのチェック
    # ----------------------------------------------------
    USER_CHECK_SQL = "SELECT user_id FROM users WHERE user_line_id = %s;"
    user_result = execute_sql(USER_CHECK_SQL, params=(line_user_id,), fetch=True)
    
    if "error" in user_result:
        # DB接続エラーが発生した場合
        response_text = f"🚨 データベースエラーが発生しました。時間を置いてお試しください。"
        
    # ----------------------------------------------------
    # 2. 既存ユーザーの場合の処理
    # ----------------------------------------------------
    elif user_result:
        # usersテーブルにレコードがあった場合
        user_id = user_result[0]['user_id']
        response_text = f"ユーザーID: {user_id} の既存ユーザーです。\n通常の機能をご利用ください。"
        
    # ----------------------------------------------------
    # 3. 未登録ユーザーの場合 (新規登録フロー)
    # ----------------------------------------------------
    else: 
        # ユーザー名の取得
        try:
            profile = line_bot_api.get_profile(line_user_id)
            user_line_name = profile.display_name
        except Exception:
            user_line_name = "お客様" 
            
        # 状態の取得 (★変更点 1: JSONではなく個別カラムをSELECT)
        STATE_SELECT_SQL = """
        SELECT 
            temp_user_grade, temp_user_class, temp_user_last_name, 
            temp_user_first_name, temp_user_line_name
        FROM registration_states WHERE user_line_id = %s;
        """
        state_result = execute_sql(STATE_SELECT_SQL, params=(line_user_id,), fetch=True)
        
        state_data = state_result[0] if state_result and "error" not in state_result else None
        
        # ----------------------------------------------
        # A. 状態レコードが存在する場合（登録継続）
        # ----------------------------------------------
        if state_data:
            # ★★★ 変更点 2: DBから取得した個別カラムをtemp_data辞書に格納 ★★★
            temp_data = {
                'grade': state_data.get('temp_user_grade'),
                'class': state_data.get('temp_user_class'),
                'last_name': state_data.get('temp_user_last_name'),
                'first_name': state_data.get('temp_user_first_name'),
            }
            # 'grade'がNoneでないかを見て、データが揃っているか否かを判定（簡略化）
            is_data_filled = temp_data['grade'] is not None 
            
            # --- A-i. 最終確認待ち (データがすべて揃っている場合) ---
            if is_data_filled: 
                
                if user_text.lower() in ["はい", "yes"]:
                    # ★★★ 最終登録処理 (INSERT users, DELETE state) ★★★
                    
                    INSERT_USERS_SQL = """
                    INSERT INTO users (user_line_id, user_grade, user_class, user_last_name, user_first_name, user_line_name)
                    VALUES (%s, %s, %s, %s, %s, %s);
                    """
                    final_reg_result = execute_sql(INSERT_USERS_SQL, (
                        line_user_id, temp_data['grade'], temp_data['class'], 
                        temp_data['last_name'], temp_data['first_name'], user_line_name
                    ))
                    
                    if "success" in final_reg_result:
                        execute_sql(DELETE_SQL, (line_user_id,))
                        response_text = f"{user_line_name} さん、ユーザー登録が完了しました！🎉"
                    else:
                        execute_result = execute_sql(DELETE_SQL, (line_user_id,))
                        # エラー時にDELETEが成功したかを確認するロジックを念のため追加
                        if "success" not in execute_result:
                             print(f"!!! 最終登録失敗後のDELETEにも失敗: {execute_result.get('error')} !!!")
                        response_text = f"🚨 最終登録処理中にデータベースエラーが発生しました。登録を中断しました。再度**「登録」**と送ってください。"
                        
                else: 
                    # 「いいえ」またはその他のメッセージ -> 状態を破棄してリセット
                    execute_sql(DELETE_SQL, (line_user_id,))
                    response_text = "登録を中断しました。再度**「登録」**と送ってください。"

            # --- A-ii. データ入力待ち (まだデータが未入力/不足している場合) ---
            else: 
                # statesがある場合のみ、parse_and_validate_registration_dataを実行
                validation_result = parse_and_validate_registration_data(user_text)

                if validation_result.get("success"):
                    # 検証成功 -> 個別カラムに保存し、確認メッセージを返す
                    new_temp_data = validation_result.get("data")
                    
                    # ★★★ 変更点 3: JSONではなく個別カラムをUPDATE ★★★
                    UPDATE_SQL = """
                    UPDATE registration_states 
                    SET temp_user_grade = %s, temp_user_class = %s, 
                        temp_user_last_name = %s, temp_user_first_name = %s,
                        temp_user_line_name = %s -- LINE名も保存
                    WHERE user_line_id = %s;
                    """
                    execute_sql(UPDATE_SQL, (
                        new_temp_data['grade'], new_temp_data['class'], 
                        new_temp_data['last_name'], new_temp_data['first_name'],
                        user_line_name, # LINE名
                        line_user_id
                    ))

                    d = new_temp_data
                    response_text = f"以下の内容で登録しますか？\n"
                    response_text += f"学年：**{d['grade']}**、クラス：**{d['class']}**\n"
                    response_text += f"氏名：**{d['last_name']} {d['first_name']}**\n"
                    response_text += "\nよろしければ**「はい」**、やめる場合は「いいえ」と送ってください。"

                else:
                    # 検証失敗 -> 状態を破棄してリセット
                    execute_sql(DELETE_SQL, (line_user_id,))
                    error_message = validation_result.get('error', '入力が不正です。')
                    response_text = f"⚠️ 入力エラー：{error_message}\n\n登録を中断しました。再度**「登録」**と送ってください。"


        # ----------------------------------------------
        # B. 状態レコードがない場合（登録トリガー or 誘導）
        # ----------------------------------------------
        else:
            # キーワード「登録」のチェックがトリガーとなる
            if user_text == "登録": 
                
                # ★★★ 変更点 4: 空のJSONではなくNULL値でINSERT ★★★
                INSERT_SQL = """
                INSERT INTO registration_states (user_line_id) 
                VALUES (%s);
                """
                start_result = execute_sql(INSERT_SQL, (line_user_id,))
                
                if "success" in start_result:
                    response_text = f"{user_line_name} さん、登録を開始します。\n\n**学年（1〜3）・クラス・姓・名**をスペース区切りで一度に返信してください。\n例: 2 1 山田 太郎"
                else:
                    response_text = "🚨 登録開始中にデータベースエラーが発生しました。再度「登録」と送ってください。"

            # ユーザーが「登録」以外のメッセージを送った場合（通常の会話）
            else:
                response_text = f"{user_line_name} さん、ユーザー情報が未登録です。\n登録をご希望の場合は、**「登録」**と送ってください。"

    # ----------------------------------------------------
    # 4. LINEに応答を返す
    # ----------------------------------------------------
    # 🚨 変更点: response_textが設定されているかチェック
    if response_text:
        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=response_text)
            )
            return 'OK'
        except Exception as e:
            print(f"REPLY API ERROR: {e}")
            return 'Error'
    return 'OK' # response_textがNoneの場合も安全に終了