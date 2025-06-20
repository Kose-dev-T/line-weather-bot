import os
import requests
import json
import xml.etree.ElementTree as ET
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent, PostbackEvent
from dotenv import load_dotenv
from datetime import datetime
import database

# --- 初期設定 ---
load_dotenv()
app = Flask(__name__)
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")

with app.app_context():
    database.init_db()

# --- 地域コード取得 ---
def get_city_code_from_xml(city_name):
    try:
        xml_url = "https://weather.tsukumijima.net/primary_area.xml"
        response = requests.get(xml_url)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        for pref in root.findall(".//pref"):
            for area in pref.findall("area"):
                if area.attrib.get("name") == city_name:
                    return area.attrib.get("id")
        return None
    except Exception as e:
        print(f"XML取得エラー: {e}")
        return None

# --- 天気予報取得 ---
def get_daily_forecast_message_dict(city_code, city_name):
    api_url = f"https://weather.tsukumijima.net/api/forecast/city/{city_code}"
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()
        forecast = data["forecasts"][0]
        telop = forecast["telop"]
        temp_max = forecast["temperature"]["max"]["celsius"] or "情報なし"
        temp_min = forecast["temperature"]["min"]["celsius"] or "情報なし"
        description = data["description"]["text"]

        flex_message = {
            "type": "flex", "altText": f"{city_name}の天気予報",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": "今日の天気予報", "weight": "bold", "size": "xl", "align": "center"}
                    ],
                    "backgroundColor": "#27A5F9"
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": city_name, "size": "lg", "weight": "bold", "color": "#1DB446"},
                        {"type": "text", "text": datetime.now().strftime('%Y年%m月%d日'), "size": "sm", "color": "#AAAAAA"},
                        {"type": "separator"},
                        {"type": "text", "text": f"天気: {telop}"},
                        {"type": "text", "text": f"最高気温: {temp_max}°C"},
                        {"type": "text", "text": f"最低気温: {temp_min}°C"},
                        {"type": "text", "text": description, "wrap": True}
                    ]
                }
            }
        }
        return flex_message
    except Exception as e:
        print(f"天気取得エラー: {e}")
        return {"type": "text", "text": "天気情報の取得に失敗しました。"}

# --- LINE返信 ---
def reply_to_line(reply_token, messages):
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }
    body = {"replyToken": reply_token, "messages": messages}
    try:
        response = requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, data=json.dumps(body))
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"LINE返信エラー: {e}")

# --- Webhookエンドポイント ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- イベントハンドラ ---
@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    database.set_user_state(user_id, 'waiting_for_location')
    reply_messages = [{"type": "text", "text": "友達追加ありがとうございます！\nお住まいの地名（例: 東京）を教えてください。"}]
    reply_to_line(event.reply_token, reply_messages)

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    if event.postback.data == 'action=change_location':
        database.set_user_state(user_id, 'waiting_for_location')
        reply_messages = [{"type": "text", "text": "新しい地名を教えてください。（例: 京都）"}]
        reply_to_line(event.reply_token, reply_messages)

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text
    user_state = database.get_user_state(user_id)
    messages_to_send = []

    city_code = get_city_code_from_xml(user_message)
    if city_code:
        if user_state == 'waiting_for_location':
            database.set_user_location(user_id, user_message, city_code)
            messages_to_send.append({"type": "text", "text": f"地点を「{user_message}」に設定しました。"})
        forecast_message = get_daily_forecast_message_dict(city_code, user_message)
        messages_to_send.append(forecast_message)
    else:
        messages_to_send.append({"type": "text", "text": f"「{user_message}」という地名が見つかりませんでした。"})

    if messages_to_send:
        reply_to_line(event.reply_token, messages_to_send)
