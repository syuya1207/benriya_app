import logging
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
import csv 
import sys 

from dotenv import load_dotenv

# PostgreSQLとの接続にpsycopg2を使用 (venvにインストール済みと仮定)
try:
    import psycopg2 
    from psycopg2.extras import DictCursor
except ImportError:
    # psycopg2がない場合は、DB接続テストはスキップされるようにする
    print("Warning: psycopg2-binary is not installed. DB connection test will be skipped.", file=sys.stderr)
    psycopg2 = None

# 環境変数をファイルから読み込む
load_dotenv()
    
# ----------------------------------------------------------------------
# 必要な定数
# ----------------------------------------------------------------------
# 環境変数から取得
DATABASE_URL = os.getenv("DATABASE_URL")

# ログ設定: 標準エラーに出力。INFOレベル以上を表示。
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stderr)
logger = logging.getLogger(__name__)

# 移行対象のCSVファイルのパス (ユーザー情報)
CSV_FILE = "data/user_data.csv" 

# ----------------------------------------------------------------------
# ヘルパー関数
# ----------------------------------------------------------------------
def _parse_timestamp(timestamp_str: str) -> Optional[datetime]:
    """日時文字列をdatetimeオブジェクトに変換。空文字列の場合はNoneを返す。"""
    if not timestamp_str or timestamp_str.strip() == '':
        return None
    
    # 混在する日時フォーマットに対応（ハイフン/スラッシュのどちらか）
    timestamp_str = timestamp_str.strip()
    
    # 試行1: ハイフン区切り (%Y-%m-%d %H:%M:%S)
    try:
        return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass
    
    # 試行2: スラッシュ区切り (%Y/%m/%d %H:%M:%S)
    try:
        return datetime.strptime(timestamp_str, "%Y/%m/%d %H:%M:%S")
    except ValueError:
        pass

    # どちらも失敗した場合はエラー
    raise ValueError(f"日時形式が不正です: {timestamp_str}")


# ----------------------------------------------------------------------
# DB操作関数 (テスト用: 接続チェックのみ)
# ----------------------------------------------------------------------
def check_db_connection():
    """データベース接続の可否をテストする関数。"""
    if not psycopg2:
        logger.warning("DB接続テスト: psycopg2がロードされていないため、テストをスキップします。")
        return False
        
    if not DATABASE_URL:
        logger.error("DB接続テスト: DATABASE_URLが環境変数に設定されていません。")
        return False

    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        logger.info("DB接続テスト: データベース接続に成功しました。")
        return True
        
    except psycopg2.Error as e:
        logger.error(f"FATAL: データベース接続エラーが発生しました: {e}")
        return False
        
    finally:
        if conn:
            conn.close() 

# ----------------------------------------------------------------------
# データ取得関数 (CSV読み込み)
# ----------------------------------------------------------------------
def fetch_csv_data() -> List[Dict[str, Any]]:
    """CSVファイルからデータを取得する。"""
    logger.info(f"データ取得: CSVファイル '{CSV_FILE}' の読み込みを開始します。")
    data = []
    
    if not os.path.exists(CSV_FILE):
        logger.error(f"エラー: CSVファイルが見つかりません: {CSV_FILE}")
        return []

    try:
        with open(CSV_FILE, mode='r', encoding='utf-8') as f:
            csv_reader = csv.DictReader(f)
            for row in csv_reader:
                # 辞書のコピーを作成し、元のDictReaderの挙動に依存しないようにする
                data.append(dict(row))
        
        logger.info(f"データ取得: 成功。合計 {len(data)} 行のデータをロードしました。")
        return data
        
    except Exception as e:
        logger.error(f"致命的エラー: CSVファイルの読み込みに失敗しました: {e}")
        return []

# ----------------------------------------------------------------------
# 移行関数 (ユーザーデータ整形とログ出力のテスト)
# ----------------------------------------------------------------------
def migrate_data():
    """CSVデータを読み込み、PostgreSQLのusersテーブルの型に合うかテストする。"""
    
    logger.info("--- ユーザー移行テスト開始 (CSV読み込み & データ型整形チェック) ---")
    
    data = fetch_csv_data()
    
    if not data:
        return False

    success_count = 0
    
    # 必須のCSVヘッダー定義
    REQUIRED_HEADERS = ['ユーザーID', '学年', 'クラス', '姓', '名', 'ユーザー名', '登録日時']

    for row in data:
        try:
            # 1. 必須カラムの存在チェック (KeyErrorで捕捉される)
            user_line_id = row['ユーザーID'] 
            user_grade = row['学年']
            user_class = row['クラス']
            user_last_name = row['姓']
            user_first_name = row['名']
            user_line_name = row['ユーザー名']
            
            # 2. 日時カラムの変換 (必須/任意)
            # '登録日時' は必須（空文字列は許可しない）
            user_registered_at = _parse_timestamp(row['登録日時'])
            if user_registered_at is None:
                raise ValueError("'登録日時'が空です。必須項目です。")

            # '更新日', '通知停止日', '削除日' は任意（空文字列はNoneに変換）
            user_updated_at = _parse_timestamp(row.get('更新日', ''))
            user_notification_stopped_at = _parse_timestamp(row.get('通知停止日', ''))
            user_deleted_at = _parse_timestamp(row.get('削除日', ''))
            
            # 3. DBに挿入される想定のデータ構造
            validated_user_data = {
                # user_id は SERIAL なので含めない
                'user_line_id': user_line_id, 
                'user_grade': user_grade,
                'user_class': user_class,
                'user_last_name': user_last_name,
                'user_first_name': user_first_name,
                'user_line_name': user_line_name,
                
                # 日時データ
                'user_registered_at': user_registered_at,
                'user_updated_at': user_updated_at,
                'user_notification_stopped_at': user_notification_stopped_at,
                'user_deleted_at': user_deleted_at,
                
                # ⚠️ CSVにない項目: user_email, user_password_hash, user_typeなどはここではNoneとして扱う (NULL許容の場合)
                'user_email': None,
                'user_password_hash': None,
                'user_type': 'external', # 例: 外部データからの移行を示す
            }

            # 🚨 整形結果をログに出力して確認 (DEBUGレベルなので通常は非表示)
            logger.debug(f"TEST SUCCESS: ID='{user_line_id}', Grade='{user_grade}', Registered={user_registered_at}, Deleted={user_deleted_at}")
            logger.debug(f"FULL DATA: {validated_user_data}")

            # 🚨 実際にはここに DB書き込みロジック (INSERT INTO users ...) が入る
            success_count += 1
            
        except KeyError as e:
            # ヘッダーが合わない場合は、致命的エラーとして終了
            logger.error(f"FATAL: CSVヘッダーエラー。必要なカラム {e} が見つかりませんでした。")
            logger.error(f"想定ヘッダー: {REQUIRED_HEADERS}")
            return False 
        except ValueError as e:
            # データ型変換が失敗した場合は、その行をスキップしてログに出力 (ERRORレベル)
            logger.error(f"SKIP: データ型変換エラー。データ: {row}、エラー: {e}")
            
    logger.info(f"ユーザー移行テスト完了。正常に整形された行数: {success_count} / 全行数: {len(data)}")
    return True


def run_test():
    """全てのテスト処理を実行するメイン関数"""
    logger.info("========================================")
    logger.info("--- ユーザー移行テストスクリプト実行 ---")
    
    # 1. DB接続テスト
    db_ok = check_db_connection()
    if db_ok:
        logger.info("ステップ 1/2: DB接続テスト成功。")
    else:
        logger.warning("ステップ 1/2: DB接続テストスキップまたは失敗。続行します。")
        
    # 2. CSV読み込みとデータ整形テスト
    if migrate_data():
        logger.info("ステップ 2/2: CSV読み込み・データ整形テスト成功。")
    else:
        logger.error("ステップ 2/2: CSV読み込み・データ整形テスト失敗。")
        
    logger.info("--- 全テスト完了 ---")
    logger.info("========================================")

if __name__ == '__main__':
    run_test()