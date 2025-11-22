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

import hashlib
import time
import secrets # ★ 追加: 安全なトークン生成用
from datetime import datetime, timedelta # ★ 修正: timedelta を追加
from datetime import timezone

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
SYSTEM_SECRET_SALT = os.environ.get("SYSTEM_SECRET_SALT")

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
# 4. PostgreSQL接続のための汎用関数（フリーズ対策・タイムゾーン設定済み）
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
        
        # ✅ 修正点 2: タイムゾーンをUTCに設定し、日時データのフリーズを回避
        conn.cursor().execute("SET TIME ZONE 'UTC'") 
        
        cursor = conn.cursor(cursor_factory=extras.DictCursor) 
        cursor.execute(sql_query, params)
        
        if fetch:
            result = cursor.fetchall()
            return result
        else:
            return {"success": True}
            
    except Exception as e:
        print(f"!!! データベースエラーが発生しました: {e} !!!", flush=True) # 強制出力
        print(f"!!! 実行失敗クエリ: {sql_query}", flush=True) # 強制出力
        if conn:
            conn.rollback() 
        return {"error": str(e)}

    finally:
        if conn:
            try:
                conn.close()
            except Exception as close_e:
                print(f"!!! 接続クローズエラー: {close_e} !!!", flush=True)


# ---------------------------------------------
# 🌟 トークン生成関数 (最終フリーズ対策・DB書き込み有効版)
# ---------------------------------------------
def generate_auth_key(id_type: str, id_value: str) -> str:
    """認証種別とID値を受け取り、自己検証型キーを生成し、NonceをDBに記録する。"""
    
    try:
        # 1. Nonce (ランダムな値) の生成
        nonce = secrets.token_hex(32) 
        
        # 2. 署名（Signature）を生成
        data_to_sign = f"{nonce}|{id_type}|{id_value}|{SYSTEM_SECRET_SALT}" 
        signature = hashlib.sha256(data_to_sign.encode()).hexdigest()
        
        # 3. URLキーの構築
        url_key = f"{nonce}.{id_type}.{id_value}.{signature}"
        
        print("DEBUG_AUTH_KEY: Key generation successful.", flush=True) # 🔑 トークン生成成功確認
        
        # =========================================================
        # 🚨 フリーズ対策のための分割代入とDB書き込みの再有効化 🚨
        # =========================================================
        
        # 4. 期限秒数を取得（constants参照直前のフリーズをテスト）
        seconds_to_expire = constants.TOKEN_EXPIRATION_SECONDS
        print(f"DEBUG_AUTH_KEY: Expiration seconds: {seconds_to_expire}", flush=True) # 🔑 constants参照確認

        # 5. 期限時刻を計算（datetime参照直後のフリーズをテスト）
        expiration_time = datetime.now(datetime.timezone.utc) + timedelta(seconds=seconds_to_expire)
        print(f"DEBUG_AUTH_KEY: Expiration time calculated: {expiration_time}", flush=True) # 🔑 日時計算確認
        
        # 6. DB用データ整理
        admin_id_for_db = id_value if id_type == 'admin_id' else None
        user_email_for_db = id_value if id_type == 'user_email' else None
        
        insert_query = """
        INSERT INTO auth_tokens (token, admin_id, user_email, created_at, expires_at)
        VALUES (%s, %s, %s, NOW(), %s);
        """
        
        # 7. DB書き込み実行（最終的にフリーズを引き起こす行）
        db_result = execute_sql(insert_query, (nonce, admin_id_for_db, user_email_for_db, expiration_time))
        print(f"DEBUG_AUTH_KEY: DB insert attempted. Result: {db_result}", flush=True) # 🔑 DB実行結果確認
        
        if "error" in db_result:
            # DBエラーが発生した場合、ERROR IN KEY GENERATIONを返す
            raise Exception(f"DB Error: {db_result['error']}")

        # =========================================================
        
        return url_key

    except Exception as e:
        import traceback
        print("\n!!!!!!!!!!!!!!!!!! generate_auth_keyでクラッシュ !!!!!!!!!!!!!!!!!!!", flush=True)
        print(f"致命的エラー: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!", flush=True)
        # エラー発生時は、無効なキーを返して handle_admin_holiday 側で処理させる
        return "ERROR_IN_KEY_GENERATION"

# ---------------------------------------------
# admin_line_id を使用して admin_id をデータベースから検索する関数。
# ---------------------------------------------
def get_admin_id_by_line_id(line_user_id: str) -> str | None:
    
    if not DATABASE_URL:
        print("Error: DATABASE_URL environment variable is not set.")
        return None

    # 1. DATABASE_URLをパースして接続パラメータを取得
    try:
        url = urlparse(DATABASE_URL)
        params = {
            'database': url.path[1:],  # スラッシュを除いたデータベース名
            'user': url.username,
            'password': url.password,
            'host': url.hostname,
            'port': url.port if url.port else 5432 # ポートが指定されていない場合はデフォルトの5432
        }
    except Exception as e:
        print(f"Error parsing DATABASE_URL: {e}")
        return None
    
    conn = None
    try:
        # 2. DBへの接続を確立
        conn = psycopg2.connect(**params)
        # 3. カーソルを作成
        with conn.cursor() as cur:
            # 4. クエリの実行
            # psycopg2ではプレースホルダに '%s' を使用します
            sql_query = "SELECT admin_id FROM admins WHERE admin_line_id = %s"
            
            # クエリ実行。line_user_idをタプルとして渡すことでSQLインジェクションを防止
            cur.execute(sql_query, (line_user_id,))
            
            # 5. 結果を取得
            result = cur.fetchone()

            if result:
                # 検索結果があれば admin_id を文字列に変換して返す
                # resultは (admin_id,) というタプルで返るため、result[0]を使用
                return str(result[0])
            else:
                return None

    except psycopg2.Error as e:
        print(f"PostgreSQL error occurred: {e}")
        return None

    finally:
        # 6. 接続を確実にクローズ
        if conn:
            conn.close()


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
# 5A. 応答処理ヘルパー関数群 (完全版)
# =========================================================

# 管理者キーワードに対する処理
def handle_admin_holiday(line_user_id):
    
    ADMIN_ID_SQL = "SELECT admin_id FROM admins WHERE admin_line_id = %s;"
    admin_data = execute_sql(ADMIN_ID_SQL, params=(line_user_id,), fetch=True)
    
    # DBエラーまたはデータがない場合のチェック
    if "error" in admin_data or not admin_data:
        if "error" in admin_data:
            return f"🚨 データベースエラーが発生しました。時間を置いてお試しください。（エラー詳細: {admin_data.get('error', '不明')}）"
        return "⚠️ 管理者IDが登録されていません。システム管理者に連絡してください。"
    
    try:
        admin_id = str(admin_data[0]['admin_id'])
    except (IndexError, KeyError) as e:
        print(f"DEBUG: admin_dataからのadmin_id抽出エラー: {e}, データ: {admin_data}")
        return "🚨 内部エラー: データベースから管理者IDを抽出できませんでした。"

    
    auth_key = generate_auth_key(id_type='admin_id', id_value=admin_id)
    holiday_url = f"{HOST_URL}/admin/holiday?key={auth_key}"
    
    expiration_minutes = constants.TOKEN_EXPIRATION_SECONDS / 60
    
    response_text = (
        f"✅ 管理者休日登録リンクが生成されました。\n"
        f"以下のURLをクリックし、登録を行ってください。\n\n"
        f"🔗 **休日登録URL:**\n"
        f"{holiday_url}\n\n"
        f"⚠️ **注意:** このリンクは**{expiration_minutes:.0f}分間**のみ有効です。\n"
        f"期限切れの場合は、再度「休み」と送ってください。"
    )
    
    return response_text


# ★★★ 削除されていた関数の復元 ★★★
def handle_admin_user_order(line_user_id):
    return "ユーザー別注文状況機能"

def handle_admin_daily_order(line_user_id):
    return "日別注文状況機能"

# 一般ユーザーキーワードに対するダミー関数
def handle_user_order(line_user_id):
    return "一般ユーザー向け注文機能"

# ---------------------------------------------
# 🌟 ディスパッチテーブル（キーワードと処理の対応付け）
# ---------------------------------------------

ADMIN_ACTIONS = {
    "休み": handle_admin_holiday,
    "テクマクマヤコン": handle_admin_user_order,
    "ゆりぴょんチェック": handle_admin_daily_order,
}

# =========================================================
# 5. 🚨 メッセージイベント発生時の処理（ディスパッチテーブル適用）
# =========================================================
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    line_user_id = event.source.user_id
    user_text = event.message.text
    response_text = None 
    
    DELETE_SQL = "DELETE FROM registration_states WHERE user_line_id = %s;"
    
    # ----------------------------------------------------
    # 1. ID 検索とステータス取得 (元のコードと同じ)
    # ----------------------------------------------------
    USER_CHECK_SQL = "SELECT user_id FROM users WHERE user_line_id = %s;" 
    user_result = execute_sql(USER_CHECK_SQL, params=(line_user_id,), fetch=True)
    is_user = bool(user_result)
    
    ADMIN_CHECK_SQL = "SELECT admin_id FROM admins WHERE admin_line_id = %s;"
    admin_result = execute_sql(ADMIN_CHECK_SQL, params=(line_user_id,), fetch=True)
    is_admin = bool(admin_result)
    
    # DBエラーチェック (ifは残る)
    if "error" in user_result or "error" in admin_result:
        response_text = f"🚨 データベースエラーが発生しました。時間を置いてお試しください。"
        
    # ----------------------------------------------------
    # 2. 応答決定ロジック（ディスパッチテーブルを使用）
    # ----------------------------------------------------
    
    # response_textが既に設定されている（DBエラーなど）場合はスキップ
    if response_text is None:
        
        # 🚨 判定値の確認 🚨
        print(f"DEBUG: is_user={is_user}, is_admin={is_admin}, Text='{user_text}'")
        # 2.1. ⭐ 管理者機能の最優先処理
        if is_user and is_admin:
            # 辞書から対応する関数を取得
            # 🚨 管理者ブロック到達確認 🚨
            print(f"DEBUG: ★★★ 管理者ブロックに到達 ★★★")
            handler = ADMIN_ACTIONS.get(user_text)
            # 🚨 辞書検索結果の確認 🚨
            print(f"DEBUG: 辞書検索結果 (handler): {handler}")
            if handler:
                response_text = handler(line_user_id) # 関数を実行し結果を取得
        
        # 2.2. 一般ユーザー機能の処理
        if response_text is None and is_user and user_text == "注文":
            response_text = handle_user_order(line_user_id)

        # 2.3. デフォルト応答（未登録ユーザーの処理と登録済みユーザーの誘導）
        if response_text is None:
            
            # 2.3A. 登録済みユーザーのデフォルト応答
            if is_user:
                response_text = "別のメッセージを送ってください"
            
            # 2.3B. 未登録ユーザーの処理 (元のelseブロックを関数化するのが望ましいが、ここではインデントリスク回避のため可能な限り元の構造を残す)
            else: 
                # ユーザー名取得 (try/exceptは残る)
                try:
                    profile = line_bot_api.get_profile(line_user_id)
                    user_line_name = profile.display_name
                except Exception:
                    user_line_name = "お客様"
                
                # 状態の取得 (DBアクセスは残る)
                STATE_SELECT_SQL = "SELECT * FROM registration_states WHERE user_line_id = %s;"
                state_result = execute_sql(STATE_SELECT_SQL, params=(line_user_id,), fetch=True)
                state_data = state_result[0] if state_result and "error" not in state_result else None
                
                # 登録継続フロー (if/elseが多層に残る部分)
                if state_data:
                    # ... 登録継続ロジック (元のコードのA-i, A-iiの部分) ...
                    # 💡 注意: この部分は手続き的なフロー制御のため、if/elseを完全に排除することは困難です。
                    # ここでは、元のコードの複雑な if/else 構造を維持します。
                    
                    temp_data = {
                        'grade': state_data.get('temp_user_grade'), 'class': state_data.get('temp_user_class'),
                        'last_name': state_data.get('temp_user_last_name'), 'first_name': state_data.get('temp_user_first_name'),
                    }
                    is_data_filled = temp_data['grade'] is not None 
                    
                    # データの最終確認待ち (A-i)
                    if is_data_filled: 
                        if user_text.lower() in ["はい", "yes"]:
                            # 最終登録処理の if/else
                            INSERT_USERS_SQL = "INSERT INTO users (user_line_id, user_grade, user_class, user_last_name, user_first_name, user_line_name) VALUES (%s, %s, %s, %s, %s, %s);"
                            final_reg_result = execute_sql(INSERT_USERS_SQL, (line_user_id, temp_data['grade'], temp_data['class'], temp_data['last_name'], temp_data['first_name'], user_line_name))
                            
                            if "success" in final_reg_result:
                                execute_sql(DELETE_SQL, (line_user_id,))
                                response_text = f"{user_line_name} さん、ユーザー登録が完了しました！🎉"
                            else:
                                execute_sql(DELETE_SQL, (line_user_id,))
                                response_text = f"🚨 最終登録処理中にデータベースエラーが発生しました。登録を中断しました。再度**「登録」**と送ってください。"
                        else: 
                            execute_sql(DELETE_SQL, (line_user_id,))
                            response_text = "登録を中断しました。再度**「登録」**と送ってください。"

                    # データ入力待ち (A-ii)
                    else: 
                        validation_result = parse_and_validate_registration_data(user_text)
                        if validation_result.get("success"):
                            # UPDATE SQLの実行
                            new_temp_data = validation_result.get("data")
                            UPDATE_SQL = "UPDATE registration_states SET temp_user_grade = %s, temp_user_class = %s, temp_user_last_name = %s, temp_user_first_name = %s, temp_user_line_name = %s WHERE user_line_id = %s;"
                            execute_sql(UPDATE_SQL, (new_temp_data['grade'], new_temp_data['class'], new_temp_data['last_name'], new_temp_data['first_name'], user_line_name, line_user_id))

                            d = new_temp_data
                            response_text = f"以下の内容で登録しますか？\n学年：**{d['grade']}**、クラス：**{d['class']}**\n氏名：**{d['last_name']} {d['first_name']}**\n\nよろしければ**「はい」**、やめる場合は「いいえ」と送ってください。"
                        else:
                            execute_sql(DELETE_SQL, (line_user_id,))
                            error_message = validation_result.get('error', '入力が不正です。')
                            response_text = f"⚠️ 入力エラー：{error_message}\n\n登録を中断しました。再度**「登録」**と送ってください。"

                # 登録開始 (B)
                else:
                    if user_text == "登録": 
                        INSERT_SQL = "INSERT INTO registration_states (user_line_id) VALUES (%s);"
                        start_result = execute_sql(INSERT_SQL, (line_user_id,))
                        
                        if "success" in start_result:
                            response_text = "登録を開始します。\n\n**学年（1〜3）・クラス・姓・名**をスペース区切りで一度に返信してください。\n例: 2 1 山田 太郎"
                        else:
                            response_text = "🚨 登録開始中にデータベースエラーが発生しました。再度「登録」と送ってください。"
                    else:
                        response_text = f"{user_line_name} さん、ユーザー情報が未登録です。\n登録をご希望の場合は、**「登録」**と送ってください。"

    # ----------------------------------------------------
    # 3. LINEに応答を返す (元のコードと同じ)
    # ----------------------------------------------------
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
    return 'OK'