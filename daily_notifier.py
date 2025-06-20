import os
import requests
import json
from dotenv import load_dotenv
import database

# --- 必要な部品をインポート ---
# LINE Messaging API関連
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    PushMessageRequest,
    TextMessage,
    StickerSendMessage,
    FlexSendMessage
)
# app.pyから天気予報とスタンプの関数を拝借
from app import get_daily_forecast, get_weather_sticker

# --- 初期設定 ---
load_dotenv()
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")

# LINE Bot APIの準備
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
line_bot_api = MessagingApi(api_client)


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
        
        # 天気予報メッセージ（FlexSendMessageまたはTextMessage）を取得
        forecast_object = get_daily_forecast(lat, lon, city_name)
        
        # --- スタンプと天気予報を一緒に送るロジック ---
        messages_to_send = []
        
        # forecast_objectがFlexSendMessageの場合のみ、スタンプを追加する
        if isinstance(forecast_object, FlexSendMessage):
            # FlexMessageから天気の説明文を抽出
            weather_description = forecast_object.contents.body.contents[2].contents[0].contents[1].text
            # 説明文に合ったスタンプを取得
            sticker_info = get_weather_sticker(weather_description)
            sticker_message = StickerSendMessage(
                package_id=sticker_info["package_id"],
                sticker_id=sticker_info["sticker_id"]
            )
            # 送信リストにスタンプを先に追加
            messages_to_send.append(sticker_message)
        
        # 最後に、メインのメッセージ（FlexMessageまたはTextMessage）を追加
        if forecast_object:
            messages_to_send.append(forecast_object)

        # 最終的なメッセージリストをプッシュ通知で送信
        if messages_to_send:
            try:
                line_bot_api.push_message(
                    PushMessageRequest(
                        to=user_id,
                        messages=messages_to_send
                    )
                )
                print(f"ユーザー({user_id})への通知が成功しました。")
            except Exception as e:
                print(f"ユーザー({user_id})へのLINE通知エラー: {e}")
            
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
