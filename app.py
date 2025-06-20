import os
import requests
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage,
    FlexSendMessage, BubbleContainer, BoxComponent, TextComponent, SeparatorComponent
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent, PostbackEvent
from datetime import datetime
from dotenv import load_dotenv
import database
import re

# --- 初期設定 ---
load_dotenv()
database.init_db()

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")

app = Flask(__name__)
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
line_bot_api = MessagingApi(api_client)
handler = WebhookHandler(CHANNEL_SECRET)

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
        pop_percent = pop * 100
        description = " / ".join(weather_descriptions) if weather_descriptions else "情報なし"
        
        bubble = BubbleContainer(
            direction='ltr', header=BoxComponent(layout='vertical', contents=[TextComponent(text='今日の天気予報', weight='bold', size='xl')]),
            body=BoxComponent(layout='vertical', spacing='md', contents=[
                BoxComponent(layout='vertical', contents=[
                    TextComponent(text=city_name, size='lg', weight='bold', color='#1DB446'),
                    TextComponent(text=datetime.now().strftime('%Y年%m月%d日'), size='sm', color='#AAAAAA')
                ]),
                SeparatorComponent(margin='md'),
                BoxComponent(layout='vertical', margin='lg', spacing='sm', contents=[
                    BoxComponent(layout='baseline', spacing='sm', contents=[
                        TextComponent(text='天気', color='#AAAAAA', size='sm', flex=2), TextComponent(text=description, wrap=True, color='#666666', size='sm', flex=5)
                    ]),
                    BoxComponent(layout='baseline', spacing='sm', contents=[
                        TextComponent(text='最高気温', color='#AAAAAA', size='sm', flex=2), TextComponent(text=f"{temp_max:.1f}°C", wrap=True, color='#666666', size='sm', flex=5)
                    ]),
                    BoxComponent(layout='baseline', spacing='sm', contents=[
                        TextComponent(text='最低気温', color='#AAAAAA', size='sm', flex=2), TextComponent(text=f"{temp_min:.1f}°C", wrap=True, color='#666666', size='sm', flex=5)
                    ]),
                    BoxComponent(layout='baseline', spacing='sm', contents=[
                        TextComponent(text='降水確率', color='#AAAAAA', size='sm', flex=2), TextComponent(text=f"{pop_percent:.0f}%", wrap=True, color='#666666', size='sm', flex=5)
                    ])
                ])
            ])
        )
        return FlexSendMessage(alt_text=f"{city_name}の天気予報", contents=bubble)
    except Exception as e:
        print(f"Forecast API Error or Flex Message creation error: {e}")
        return TextMessage(text="天気情報の取得に失敗しました。")

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    database.set_user_state(user_id, 'waiting_for_location')
    reply_message = TextMessage(text="友達追加ありがとうございます！\n毎日の天気予報を通知するために、まずはお住まいの地名（例: 大阪市）を教えてください。")
    line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply_message]))

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    if event.postback.data == 'action=change_location':
        database.set_user_state(user_id, 'waiting_for_location')
        reply_message = TextMessage(text="新しい通知先の地名を教えてください。（例: 横浜市）")
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply_message]))

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text
    user_state = database.get_user_state(user_id)
    reply_message = None
    if user_state == 'waiting_for_location':
        coords_data = get_location_coords(user_message)
        if coords_data:
            database.set_user_location(user_id, coords_data["name"], coords_data["lat"], coords_data["lon"])
            reply_message = TextMessage(text=f"地点を「{coords_data['name']}」に設定しました。\n明日から毎日0時に天気予報をお届けします！")
        else:
            reply_message = TextMessage(text=f"「{user_message}」が見つかりませんでした。もう一度、市町村名などで入力してください。")
    else:
        coords_data = get_location_coords(user_message)
        if coords_data:
            reply_message = get_daily_forecast(coords_data["lat"], coords_data["lon"], coords_data["name"])
        else:
            reply_message = TextMessage(text=f"「{user_message}」という地名が見つかりませんでした。")
    if reply_message:
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply_message]))

if __name__ == "__main__":
    app.run(port=5000)