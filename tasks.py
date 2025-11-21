# tasks.py (確実性向上版)

import datetime
import os

# ログファイルは /tmp ディレクトリに書き出します
# 環境によっては書き込み権限がない場合もあるため、権限エラーの確認も必要です
OUTPUT_FILE = "/tmp/cron_tasks_log.txt"

def cleanup_expired_sessions():
    """
    クリーンアップDB接続ロジックの代わりに、ファイルに実行時刻を記録します。
    """
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    # ログメッセージを組み立て (f-stringではなく、.format() を使用し互換性を確保)
    log_message = "Tasks script executed successfully at: {}\n".format(timestamp)

    try:
        # ファイルに追記
        # with open(OUTPUT_FILE, "a") as f: の代わりに絶対パスを明示的に使用
        with open(os.path.abspath(OUTPUT_FILE), "a") as f:
            f.write(log_message)
        
        # 実行結果を標準出力にログとして残す（Cron実行時に確認可能）
        print("Test execution successful. Log written to {}.".format(OUTPUT_FILE))

    except IOError as e:
        # ファイルI/Oのエラーを特定 (Permission deniedなど)
        print("IOError: File writing failed: {} Check permissions or path.".format(e), flush=True)
    except Exception as e:
        # その他の予期せぬエラー
        print("General Error: {}".format(e), flush=True)


# ----------------------------------------------------------------------
# スクリプトとして直接実行された場合の処理 (Cron用)
# ----------------------------------------------------------------------
if __name__ == "__main__":
    cleanup_expired_sessions()