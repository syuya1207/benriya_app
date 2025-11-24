import secrets
from datetime import datetime, timedelta
from utils.db_utils import execute_sql

#--------------------------------------------------------------
#ワンタイムトークンを作成して auth_tokens に保存する
#--------------------------------------------------------------
def create_token(admin_id=None, user_id=None, ttl_minutes=10):
    
    token = secrets.token_hex(32)
    expires_at = datetime.utcnow() + timedelta(minutes=ttl_minutes)

    sql = """
        INSERT INTO auth_tokens (token, admin_id, user_id, created_at, expires_at)
        VALUES (%s, %s, %s, NOW(), %s)
    """
    params = (token, admin_id, user_id, expires_at)

    res = execute_sql(sql, params)
    if "error" in res:
        return None

    return token

#--------------------------------------------------------------
#トークンが有効かどうかチェックし、OKなら情報を返す
#--------------------------------------------------------------
def verify_token(token: str):
    
    sql = """
        SELECT token, admin_id, user_id, created_at, expires_at
        FROM auth_tokens
        WHERE token = %s
    """
    rows = execute_sql(sql, (token,), fetch=True)

    if not rows:
        return None

    row = rows[0]
    if datetime.utcnow() > row["expires_at"]:
        return None

    return row