# DBアクセス用ファイル
import psycopg2
from psycopg2 import extras
from urllib.parse import urlparse
import os

DATABASE_URL = os.environ.get("DATABASE_URL")

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
            port=url.port or None,
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