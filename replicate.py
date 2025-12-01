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

# ログ設定: 標準エラーに出力。INFOレベル以上（INFO, WARNING, ERROR, CRITICAL）を表示。
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stderr)
logger = logging.getLogger(__name__)

# 移行対象のCSVファイルのパス
CSV_FILE = "data/original_orders.csv" 

# ----------------------------------------------------------------------
# DB操作関数 (今回はテストのため、実行はせず、接続チェックのみ行う)
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
        # DB接続を試行
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
            # csv.DictReaderは、ヘッダー行をキーとして辞書形式でデータを読み込む
            csv_reader = csv.DictReader(f)
            for row in csv_reader:
                data.append(dict(row))
        
        logger.info(f"データ取得: 成功。合計 {len(data)} 行のデータをロードしました。")
        return data
        
    except Exception as e:
        logger.error(f"致命的エラー: CSVファイルの読み込みに失敗しました: {e}")
        return []

# ----------------------------------------------------------------------
# 移行関数 (データ整形とログ出力のテスト)
# ----------------------------------------------------------------------
def migrate_data():
    """CSVデータを読み込み、PostgreSQLの型に合うかテストする。
    
    CSVデータに混在する日付フォーマット（ハイフン/スラッシュ）に対応するため、
    try-exceptをネストして複数のフォーマットを試行する。
    """
    
    logger.info("--- 移行テスト開始 (CSV読み込み & データ型整形チェック) ---")
    
    data = fetch_csv_data()
    
    if not data:
        return False

    success_count = 0
    
    for row in data:
        try:
            # 1. 'ユーザーID' をそのまま文字列 (str) として使用
            user_id = row['ユーザーID'] 
            
            # 2. '注文対象日' を Pythonの date オブジェクトに変換
            order_date_str = row['注文対象日']
            try:
                # 試行1: ハイフン区切り (%Y-%m-%d)
                order_date = datetime.strptime(order_date_str, "%Y-%m-%d").date() 
            except ValueError:
                # 試行2: スラッシュ区切り (%Y/%m/%d)
                try:
                    order_date = datetime.strptime(order_date_str, "%Y/%m/%d").date() 
                except ValueError as e:
                    # 両方失敗した場合、外側の except に渡す
                    raise ValueError(f"'注文対象日'の日付形式が不正です: {order_date_str}") from e
            
            # 3. '商品名' を文字列 (str) のまま使用
            product_name = row['商品名']      

            # 4. '受信日時' を Pythonの datetime オブジェクトに変換
            received_at_str = row['受信日時']
            try:
                # 試行1: ハイフン区切り (%Y-%m-%d %H:%M:%S)
                received_at = datetime.strptime(received_at_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                # 試行2: スラッシュ区切り (%Y/%m/%d %H:%M:%S)
                try:
                    received_at = datetime.strptime(received_at_str, "%Y/%m/%d %H:%M:%S")
                except ValueError as e:
                    # 両方失敗した場合、外側の except に渡す
                    raise ValueError(f"'受信日時'の日時形式が不正です: {received_at_str}") from e

            # 🚨 整形結果をログに出力して確認
            # DEBUGレベルなので、INFO設定では出力されず非表示になる
            logger.debug(f"TEST SUCCESS: UserID='{user_id}' (str), OrderDate={order_date} (date), Product='{product_name}' (str), ReceivedAt={received_at} (datetime)")

            # 🚨 実際にはここに DB書き込みロジック (execute_sql) が入る
            success_count += 1
            
        except KeyError as e:
            # ヘッダーが合わない場合は、致命的エラーとして終了
            logger.error(f"FATAL: CSVヘッダーエラー。必要なカラム {e} が見つかりませんでした。")
            return False 
        except ValueError as e:
            # データ型変換が失敗した場合は、その行をスキップしてログに出力 (ERRORレベル)
            logger.error(f"SKIP: データ型変換エラー。データ: {row}、エラー: {e}")
            
    logger.info(f"移行テスト完了。正常に整形された行数: {success_count} / 全行数: {len(data)}")
    return True


def run_test():
    """全てのテスト処理を実行するメイン関数"""
    logger.info("========================================")
    logger.info("--- 移行テストスクリプト実行 ---")
    
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