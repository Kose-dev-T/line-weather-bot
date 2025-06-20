import os
import requests
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage
)
# 【追加】様々なイベントに対応するために、インポートを追加します
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent, PostbackEvent
from datetime import datetime
from dotenv import load_dotenv
import database # 作成したdatabase.pyをインポート
import re

# --- 初期設定 ---
load_dotenv()
database.init_db() # データベースを初期化（なければテーブルが作成される）

# 環境変数からキー情報を取得
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")

# FlaskサーバーとLINE Bot APIの準備
app = Flask(__name__)
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
line_bot_api = MessagingApi(api_client)
handler = WebhookHandler(CHANNEL_SECRET)

# --- 天気予報を取得するための関数 ---
def get_location_coords(city_name):
    api_url = "http://api.openweathermap.org/geo/1.0/direct"
    params = {"q": city_name, "limit": 1, "appid": OPENWEATHER_API_KEY}
    try:
        response = requests.get(api_url, params=params)
        response.raise_for_status()
        data = response.json()
        if data:
            japanese_name = data[0].get("local_names", {}).get("ja", city_name)
            return {"lat": data[0]["lat"], "lon": data[0]["lon"], "name": japanese_name}
        return None
    except Exception as e:
        print(f"Geocoding API Error: {e}")
        return None

def get_daily_forecast(lat, lon, city_name):
    api_url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY, "units": "metric", "lang": "ja"}
    try:
        response = requests.get(api_url, params=params)
        response.raise_for_status()
        data = response.json()
        today_str = datetime.now().strftime('%Y-%m-%d')
        temp_max, temp_min, pop = -1000, 1000, 0
        weather_descriptions = []
        for forecast in data["list"]:
            if today_str in forecast["dt_txt"]:
                temp_max = max(temp_max, forecast["main"]["temp_max"])
                temp_min = min(temp_min, forecast["main"]["temp_min"])
                pop = max(pop, forecast["pop"])
                if forecast["weather"][0]["description"] not in weather_descriptions:
                    weather_descriptions.append(forecast["weather"][0]["description"])
        message = (
            f"【{city_name}の天気予報】\n\n"
            f"天気: {' / '.join(weather_descriptions) if weather_descriptions else '情報なし'}\n"
            f"最高気温: {temp_max:.1f}°C\n"
            f"最低気温: {temp_min:.1f}°C\n"
            f"降水確率: {pop * 100:.0f}%"
        )
        return message
    except Exception as e:
        print(f"Forecast API Error: {e}")
        return "天気情報の取得に失敗しました。"

# --- LINEからのアクセス（Webhook）を処理 ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- ここからがボットの対話ロジック ---

# 1. 友達追加（フォロー）されたときの処理
@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    # ユーザーの状態を「地点登録待ち」に設定
    database.set_user_state(user_id, 'waiting_for_location')
    
    reply_message = (
        "友達追加ありがとうございます！\n"
        "毎日の天気予報を通知するために、まずはお住まいの地名（例: 大阪市）を教えてください。"
    )
    line_bot_api.reply_message(
        ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply_message)])
    )

# 2. リッチメニューのボタンが押されたときの処理
@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    # ボタンに設定したデータ`action=change_location`と一致するかチェック
    if event.postback.data == 'action=change_location':
        # ユーザーの状態を「地点登録待ち」に設定
        database.set_user_state(user_id, 'waiting_for_location')
        reply_message = "新しい通知先の地名を教えてください。（例: 横浜市）"
        line_bot_api.reply_message(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply_message)])
        )

# 3. テキストメッセージが送られてきたときの処理
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text
    
    # データベースから現在のユーザーの状態を取得
    user_state = database.get_user_state(user_id)
    
    # 【分岐ロジック】ユーザーの状態に応じて処理を変える
    if user_state == 'waiting_for_location':
        # 状態が「地点登録待ち」の場合、送られてきたメッセージを地名として登録する
        coords_data = get_location_coords(user_message)
        if coords_data:
            # 地点情報をデータベースに保存し、状態を「通常」に戻す
            database.set_user_location(user_id, coords_data["name"], coords_data["lat"], coords_data["lon"])
            reply_message = f"地点を「{coords_data['name']}」に設定しました。\n明日から毎日0時に天気予報をお届けします！"
        else:
            reply_message = f"「{user_message}」が見つかりませんでした。もう一度、市町村名などで入力してください。"
    else:
        # 通常状態の場合、送られてきたメッセージをその場の天気予報検索として扱う
        coords_data = get_location_coords(user_message)
        if coords_data:
            reply_message = get_daily_forecast(coords_data["lat"], coords_data["lon"], coords_data["name"])
        else:
            reply_message = f"「{user_message}」という地名が見つかりませんでした。"

    # 最終的な返信メッセージを送信
    line_bot_api.reply_message(
        ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply_message)])
    )

# --- サーバーを起動 ---
if __name__ == "__main__":
    app.run(port=5000, debug=True)