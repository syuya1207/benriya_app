-- 一般ユーザーテーブル
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    user_line_id VARCHAR(100) UNIQUE, 
    user_email VARCHAR(255) UNIQUE,
    user_password_hash VARCHAR(255),
    
    user_type VARCHAR(50), 
    user_grade VARCHAR(50),
    user_class VARCHAR(50),
    user_last_name VARCHAR(100),
    user_first_name VARCHAR(100),
    user_line_name VARCHAR(100),
    
    user_email_verified_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    user_registered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    user_updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    user_notification_stopped_at TIMESTAMP WITH TIME ZONE,
    user_deleted_at TIMESTAMP WITH TIME ZONE
);

-- 管理者テーブル
CREATE TABLE admins (
    admin_id SERIAL PRIMARY KEY,
    admin_line_id VARCHAR(100) UNIQUE,  
    admin_email VARCHAR(255) UNIQUE,
    admin_password_hash VARCHAR(255),
    admin_last_name VARCHAR(100) NOT NULL,
    admin_first_name VARCHAR(100) NOT NULL
);

-- スーパーアドミンテーブル
CREATE TABLE super_admins (
    super_admin_id SERIAL PRIMARY KEY,
    super_admin_line_id VARCHAR(100) UNIQUE,  -- 新規追加
    super_admin_email VARCHAR(255) UNIQUE NOT NULL,
    secret_phrase_hash VARCHAR(255) NOT NULL,
    super_admin_last_name VARCHAR(100) NOT NULL,
    super_admin_first_name VARCHAR(100) NOT NULL
);
----------------------------------------------


CREATE TABLE orders (
    order_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    
    product_id VARCHAR(50) NOT NULL, 
    product_name VARCHAR(255) NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price INTEGER NOT NULL,
    has_options BOOLEAN NOT NULL DEFAULT FALSE, 
    
    option_total_amount INTEGER NOT NULL DEFAULT 0, -- option_detailsの合計
    total_amount INTEGER NOT NULL DEFAULT 0,        -- 注文全体の確定総額
    
    order_date DATE NOT NULL,
    order_received_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    order_updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    order_deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE option_details ( 
    option_detail_id SERIAL PRIMARY KEY, 
    order_id INTEGER NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE, 
    option_name VARCHAR(100) NOT NULL,     
    option_value VARCHAR(100) NOT NULL,    
    price INTEGER NOT NULL DEFAULT 0       
);

CREATE TABLE products (
    product_id VARCHAR(50) PRIMARY KEY,
    product_name VARCHAR(255) NOT NULL,
    image_url VARCHAR(255),
    price INTEGER NOT NULL,
    schedule_type VARCHAR(50) NOT NULL, 
    schedule_day VARCHAR(50), 
    is_deleted BOOLEAN DEFAULT FALSE
);


-- パスワードリセット等の汎用認証トークン
CREATE TABLE auth_tokens (
    token_id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(user_id),
    user_line_id VARCHAR(100),
    user_email VARCHAR(255) ,
    token VARCHAR(64) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);


CREATE TABLE key_words (
    keyword_id SERIAL PRIMARY KEY,
    key_word VARCHAR(255) UNIQUE NOT NULL,
    related_table VARCHAR(50) NOT NULL,
    function_name VARCHAR(100) NOT NULL,
    key_note VARCHAR(255)
);


-- セッション管理テーブル
CREATE TABLE sessions (
    session_id VARCHAR(128) PRIMARY KEY,
    data TEXT NOT NULL,          
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);


-- 休日設定テーブル
CREATE TABLE holidays (
    holiday_date DATE PRIMARY KEY,
    note VARCHAR(255)
);

--初回ユーザー登録用の情報一時記録テーブル
CREATE TABLE registration_states (
    user_line_id VARCHAR(100) PRIMARY KEY,
    temp_user_grade VARCHAR(50),
    temp_user_class VARCHAR(50),
    temp_user_last_name VARCHAR(100),
    temp_user_first_name VARCHAR(100),
    temp_user_line_name VARCHAR(100)
);