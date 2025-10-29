from flask import Flask
import os

# アプリケーションインスタンスを作成（Gunicornが参照する名前は「app」）
app = Flask(__name__) # ★★★ この行があるか、変数名が「app」か確認 ★★★

@app.route('/')
def hello_world():
    # データベースがなくても動く、シンプルなテストメッセージ
    return "Hello from Flask! (via Gunicorn)"

if __name__ == '__main__':
    # この部分はGunicornでは使われませんが、開発時のテスト用です
    app.run(debug=True, host='0.0.0.0', port=5000)