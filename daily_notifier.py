import os
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, PushMessageRequest, TextMessage
import database # 作成したdatabase.pyをインポート
# app.pyから天気予報を取得する関数をコピーしてくる
from app import get_daily_forecast 

# app.pyからキー情報をコピーしてくる
CHANNEL_ACCESS_TOKEN = "ここにあなたのLINEチャネルアクセストークン"

# LINE Bot APIの初期化
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
line_bot_api = MessagingApi(api_client)

def send_daily_forecasts():
    print("デイリー通知の送信を開始します...")
    # 登録地がある全ユーザーを取得
    users = database.get_all_users_with_location()
    
    for user in users:
        user_id, city_name, lat, lon = user
        print(f"{city_name}({user_id})の天気予報を送信中...")
        
        # 天気予報メッセージを取得
        forecast_message = get_daily_forecast(lat, lon, city_name)
        
        if forecast_message:
            # プッシュメッセージでユーザーに通知を送信
            line_bot_api.push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[TextMessage(text=forecast_message)]
                )
            )
    print("デイリー通知の送信が完了しました。")

if __name__ == "__main__":
    send_daily_forecasts()