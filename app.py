import os
import requests
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage,
    StickerSendMessage,
    FlexSendMessage, BubbleContainer, BoxComponent, TextComponent, SeparatorComponent
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent, PostbackEvent
from datetime import datetime
from dotenv import load_dotenv
import database
import re

# --- 初期設定 ---
load_dotenv()
database.init_db() # データベースを初期化

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

# --- 天気予報・スタンプを取得するための関数 ---

def get_location_coords(city_name):
    """地名から緯度と経度を取得する関数"""
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

# 天気の説明文から、送信するLINEスタンプのIDを返す関数
def get_weather_sticker(weather_description):
    if "晴" in weather_description:
        return {"package_id": "11537", "sticker_id": "52002734"}
    elif "曇" in weather_description:
        return {"package_id": "11537", "sticker_id": "52002748"}
    elif "雨" in weather_description:
        return {"package_id": "11538", "sticker_id": "51626501"}
    elif "雪" in weather_description:
        return {"package_id": "11538", "sticker_id": "51626522"}
    else:
        return {"package_id": "11537", "sticker_id": "52002735"}

# 天気予報をFlex Message形式で生成
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
            direction='ltr',
            header=BoxComponent(
                layout='vertical',
                contents=[
                    TextComponent(text='今日の天気予報', weight='bold', size='xl')
                ]
            ),
            body=BoxComponent(
                layout='vertical',
                spacing='md',
                contents=[
                    BoxComponent(layout='vertical', contents=[
                        TextComponent(text=city_name, size='lg', weight='bold', color='#1DB446'),
                        TextComponent(text=datetime.now().strftime('%Y年%m月%d日'), size='sm', color='#AAAAAA')
                    ]),
                    SeparatorComponent(margin='md'),
                    BoxComponent(layout='vertical', margin='lg', spacing='sm', contents=[
                        BoxComponent(layout='baseline', spacing='sm', contents=[
                            TextComponent(text='天気', color='#AAAAAA', size='sm', flex=2),
                            TextComponent(text=description, wrap=True, color='#666666', size='sm', flex=5)
                        ]),
                        BoxComponent(layout='baseline', spacing='sm', contents=[
                            TextComponent(text='最高気温', color='#AAAAAA', size='sm', flex=2),
                            TextComponent(text=f"{temp_max:.1f}°C", wrap=True, color='#666666', size='sm', flex=5)
                        ]),
                        BoxComponent(layout='baseline', spacing='sm', contents=[
                            TextComponent(text='最低気温', color='#AAAAAA', size='sm', flex=2),
                            TextComponent(text=f"{temp_min:.1f}°C", wrap=True, color='#666666', size='sm', flex=5)
                        ]),
                        BoxComponent(layout='baseline', spacing='sm', contents=[
                            TextComponent(text='降水確率', color='#AAAAAA', size='sm', flex=2),
                            TextComponent(text=f"{pop_percent:.0f}%", wrap=True, color='#666666', size='sm', flex=5)
                        ])
                    ])
                ]
            )
        )
        return FlexSendMessage(alt_text=f"{city_name}の天気予報", contents=bubble)
    except Exception as e:
        print(f"Forecast API Error or Flex Message creation error: {e}")
        return TextMessage(text="天気情報の取得に失敗しました。")

# --- LINEからのアクセスを処理 ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- ここからボットの対話ロジック ---

# 1. 友達追加されたときの処理
@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    database.set_user_state(user_id, 'waiting_for_location')
    reply_message = TextMessage(text="友達追加ありがとうございます！\n毎日の天気予報を通知するために、まずはお住まいの地名（例: 大阪市）を教えてください。")
    line_bot_api.reply_message(
        ReplyMessageRequest(reply_token=event.reply_token, messages=[reply_message])
    )

# 2. リッチメニューのボタンが押されたときの処理
@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    if event.postback.data == 'action=change_location':
        database.set_user_state(user_id, 'waiting_for_location')
        reply_message = TextMessage(text="新しい通知先の地名を教えてください。（例: 横浜市）")
        line_bot_api.reply_message(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[reply_message])
        )

# 3. テキストメッセージが送られてきたときの処理
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text
    user_state = database.get_user_state(user_id)
    
    reply_object = None # 返信するメッセージオブジェクトを格納する変数
    
    if user_state == 'waiting_for_location':
        coords_data = get_location_coords(user_message)
        if coords_data:
            database.set_user_location(user_id, coords_data["name"], coords_data["lat"], coords_data["lon"])
            reply_object = TextMessage(text=f"地点を「{coords_data['name']}」に設定しました。\n明日から毎日0時に天気予報をお届けします！")
        else:
            reply_object = TextMessage(text=f"「{user_message}」が見つかりませんでした。もう一度、市町村名などで入力してください。")
    else:
        coords_data = get_location_coords(user_message)
        if coords_data:
            reply_object = get_daily_forecast(coords_data["lat"], coords_data["lon"], coords_data["name"])
        else:
            reply_object = TextMessage(text=f"「{user_message}」という地名が見つかりませんでした。")

    # スタンプと天気予報を一緒に送るロジック
    messages_to_send = []
    # reply_objectがFlexSendMessageの場合のみ、スタンプを追加する
    if isinstance(reply_object, FlexSendMessage):
        # FlexMessageから天気の説明文を抽出
        weather_description = reply_object.contents.body.contents[2].contents[0].contents[1].text
        # 説明文に合ったスタンプを取得
        sticker_info = get_weather_sticker(weather_description)
        sticker_message = StickerSendMessage(
            package_id=sticker_info["package_id"],
            sticker_id=sticker_info["sticker_id"]
        )
        # 送信リストにスタンプを先に追加
        messages_to_send.append(sticker_message)
    
    # 最後に、メインのメッセージを追加
    if reply_object:
        messages_to_send.append(reply_object)

    # 最終的なメッセージリストを送信
    if messages_to_send:
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=messages_to_send
            )
        )

# --- サーバーを起動 ---
if __name__ == "__main__":
    app.run(port=5000, debug=True)
