import os
import requests # requestsを直接使うのでインポート
import json     # JSONデータを扱うためにインポート
from dotenv import load_dotenv
import database

# daily_notifier.pyがapp.pyの関数を使えるように、少し工夫します
from app import get_daily_forecast

# --- 初期設定 ---
load_dotenv()
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")

def send_line_push_notification(user_id, message):
    """【修正箇所】requestsを直接使い、指定したユーザーIDにプッシュ通知を送信する関数"""
    
    # LINEのPush Message APIのエンドポイントURL
    push_api_url = "https://api.line.me/v2/bot/message/push"
    
    # リクエストに必要なヘッダー
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }
    
    # 送信するデータ本体（JSON形式）
    body = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }

    try:
        # requests.postで、LINEのサーバーに直接通知リクエストを送信
        response = requests.post(push_api_url, headers=headers, data=json.dumps(body))
        response.raise_for_status() # エラーがあればここで停止
        print(f"ユーザー({user_id})への通知が成功しました。")
    except requests.exceptions.RequestException as e:
        print(f"ユーザー({user_id})へのLINE通知エラー: {e}")
        # サーバーからの詳細なエラー内容も表示
        print(f"応答内容: {e.response.text}")


def send_daily_forecasts():
    """登録ユーザー全員に天気予報を通知するメイン関数"""
    print("デイリー通知の送信を開始します...")
    
    # データベースから登録ユーザーを取得
    users = database.get_all_users_with_location()
    
    if not users:
        print("通知対象のユーザーが見つかりませんでした。")
    
    for user in users:
        user_id, city_name, lat, lon = user
        print(f"{city_name}({user_id})の天気予報を送信中...")
        
        # 天気予報メッセージを取得
        forecast_message = get_daily_forecast(lat, lon, city_name)
        
        if forecast_message:
            # 新しい通知関数を呼び出す
            send_line_push_notification(user_id, forecast_message)
            
    print("デイリー通知の送信が完了しました。")

# --- メインの実行部分 ---
if __name__ == "__main__":
    if not CHANNEL_ACCESS_TOKEN:
        print("エラー: .envファイルにLINE_CHANNEL_ACCESS_TOKENが設定されていません。")
    else:
        # データベースを初期化
        database.init_db()
        # 通知処理を開始
        send_daily_forecasts()