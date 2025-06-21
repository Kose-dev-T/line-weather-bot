import os
import requests
import json
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent, PostbackEvent
from datetime import datetime
from dotenv import load_dotenv
import database
import xml.etree.ElementTree as ET
import math

# --- 初期設定 ---
load_dotenv()
app = Flask(__name__)

with app.app_context():
    database.init_db()

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")

handler = WebhookHandler(CHANNEL_SECRET)

# --- グローバル変数 ---
LIVEDOOR_CITY_LIST = None

# --- 補助関数群 ---

def get_livedoor_cities():
    """livedoor互換APIの都市リストとID、緯度経度を取得・キャッシュする関数"""
    global LIVEDOOR_CITY_LIST
    if LIVEDOOR_CITY_LIST is not None:
        return LIVEDOOR_CITY_LIST

    # このリストは、一般的に公開されているLivedoor Weatherの主要な都市コードと緯度経度の対応表です。
    # ここに都市を追加すれば、検索精度が向上します。
    LIVEDOOR_CITY_LIST = [
        {"id": "016010", "name": "札幌", "lat": 43.064, "lon": 141.347},
        {"id": "040010", "name": "仙台", "lat": 38.268, "lon": 140.872},
        {"id": "130010", "name": "東京", "lat": 35.689, "lon": 139.692},
        {"id": "140010", "name": "横浜", "lat": 35.448, "lon": 139.642},
        {"id": "230010", "name": "名古屋", "lat": 35.181, "lon": 136.906},
        {"id": "250010", "name": "大津", "lat": 35.004, "lon": 135.869},
        {"id": "250020", "name": "彦根", "lat": 35.274, "lon": 136.259},
        {"id": "260010", "name": "京都", "lat": 35.021, "lon": 135.754},
        {"id": "270000", "name": "大阪", "lat": 34.686, "lon": 135.520},
        {"id": "280010", "name": "神戸", "lat": 34.694, "lon": 135.195},
        {"id": "340010", "name": "広島", "lat": 34.396, "lon": 132.459},
        {"id": "400010", "name": "福岡", "lat": 33.591, "lon": 130.401},
        {"id": "471010", "name": "那覇", "lat": 26.212, "lon": 127.681}
    ]
    print("主要都市リストをキャッシュしました。")
    return LIVEDOOR_CITY_LIST

def haversine(lat1, lon1, lat2, lon2):
    """2点間の距離を計算する関数（ハーバーサイン公式）"""
    R = 6371 # 地球の半径 (km)
    dLat, dLon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dLat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def get_closest_city_id(user_input_city):
    """ユーザー入力の地名に最も近い、予報可能な都市のIDを返す"""
    try:
        # 1. ユーザー入力の地名の緯度・経度を取得 (OWM API)
        geo_api_url = f"http://api.openweathermap.org/geo/1.0/direct?q={user_input_city},JP&limit=1&appid={OPENWEATHER_API_KEY}"
        geo_res = requests.get(geo_api_url)
        geo_res.raise_for_status()
        geo_data = geo_res.json()
        if not geo_data: return None
        
        user_lat, user_lon = geo_data[0]['lat'], geo_data[0]['lon']
        
        # 2. 予報可能な全都市のリストを取得
        all_cities = get_livedoor_cities()
        if not all_cities: return None
        
        # 3. 最も近い都市を探す
        closest_city = None
        min_distance = float('inf')

        for city in all_cities:
            distance = haversine(user_lat, user_lon, city["lat"], city["lon"])
            if distance < min_distance:
                min_distance = distance
                closest_city = city
        
        if closest_city:
            print(f"'{user_input_city}'に最も近い都市として'{closest_city['name']}' (ID: {closest_city['id']}) を選択しました。")
            return closest_city['id']
        return None

    except Exception as e:
        print(f"Error in get_closest_city_id: {e}")
        return None

def get_livedoor_forecast_message_dict(city_id):
    """指定された都市IDの天気予報を取得する関数"""
    api_url = f"https://weather.tsukumijima.net/api/forecast?city={city_id}"
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()
        
        today_forecast = data["forecasts"][0]
        city_name = data["location"]["city"]
        weather = today_forecast["telop"]
        temp_max_obj = today_forecast["temperature"]["max"]
        temp_min_obj = today_forecast["temperature"]["min"]
        
        temp_max = temp_max_obj["celsius"] if temp_max_obj else "--"
        temp_min = temp_min_obj["celsius"] if temp_min_obj else "--"

        chance_of_rain = " / ".join(today_forecast["chanceOfRain"].values())

        flex_message = {
            "type": "flex", "altText": f"{city_name}の天気予報",
            "contents": {
                "type": "bubble", "direction": 'ltr',
                "header": {"type": "box", "layout": "vertical", "contents": [
                    {"type": "text", "text": "今日の天気予報", "weight": "bold", "size": "xl", "color": "#FFFFFF", "align": "center"}
                ], "backgroundColor": "#00B900", "paddingTop": "12px", "paddingBottom": "12px"},
                "body": {"type": "box", "layout": "vertical", "spacing": "md", "contents": [
                    {"type": "box", "layout": "vertical", "contents": [
                        {"type": "text", "text": city_name, "size": "lg", "weight": "bold", "color": "#00B900"},
                        {"type": "text", "text": today_forecast["date"], "size": "sm", "color": "#AAAAAA"}]},
                    {"type": "separator", "margin": "md"},
                    {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm", "contents": [
                        {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                            {"type": "text", "text": "天気", "color": "#AAAAAA", "size": "sm", "flex": 2},
                            {"type": "text", "text": weather, "wrap": True, "color": "#666666", "size": "sm", "flex": 5}]},
                        {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                            {"type": "text", "text": "最高気温", "color": "#AAAAAA", "size": "sm", "flex": 2},
                            {"type": "text", "text": f"{temp_max}°C", "wrap": True, "color": "#666666", "size": "sm", "flex": 5}]},
                        {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                            {"type": "text", "text": "最低気温", "color": "#AAAAAA", "size": "sm", "flex": 2},
                            {"type": "text", "text": f"{temp_min}°C", "wrap": True, "color": "#666666", "size": "sm", "flex": 5}]},
                        {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                            {"type": "text", "text": "降水確率", "color": "#AAAAAA", "size": "sm", "flex": 2},
                            {"type": "text", "text": chance_of_rain, "wrap": True, "color": "#666666", "size": "sm", "flex": 5}]}
                    ]}
                ]}
            }
        }
        return flex_message
    except Exception as e:
        print(f"Livedoor Forecast API Error: {e}")
        return {"type": "text", "text": "天気情報の取得に失敗しました。"}

def reply_to_line(reply_token, messages):
    headers = {"Content-Type": "application/json; charset=UTF-8", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
    body = {"replyToken": reply_token, "messages": messages}
    try:
        response = requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, data=json.dumps(body, ensure_ascii=False).encode('utf-8'))
        response.raise_for_status()
        print("LINEへの返信が成功しました。")
    except requests.exceptions.RequestException as e:
        print(f"LINE返信エラー: {e}\n応答内容: {e.response.text if e.response else 'N/A'}")

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
    reply_messages = [{"type": "text", "text": "友達追加ありがとうございます！\n毎日の天気予報を通知するために、まずはお住まいの地名（例: 大阪市）を教えてください。"}]
    reply_to_line(event.reply_token, reply_messages)

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    if event.postback.data == 'action=change_location':
        database.set_user_state(user_id, 'waiting_for_location')
        reply_messages = [{"type": "text", "text": "新しい通知先の地名を教えてください。（例: 横浜市）"}]
        reply_to_line(event.reply_token, reply_messages)

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text
    messages_to_send = []
    
    try:
        user_state = database.get_user_state(user_id)
        
        if user_state == 'waiting_for_location':
            city_id = get_closest_city_id(user_message)
            if city_id:
                database.set_user_location(user_id, user_message, city_id)
                messages_to_send.append({"type": "text", "text": f"地点を「{user_message}」に設定しました。\n明日から登録地点の天気予報をお届けします！"})
            else:
                messages_to_send.append({"type": "text", "text": f"「{user_message}」が見つかりませんでした。日本の市町村名などで入力してください。"})
        else:
            city_id = get_closest_city_id(user_message)
            if city_id:
                forecast_message = get_livedoor_forecast_message_dict(city_id)
                messages_to_send.append(forecast_message)
            else:
                messages_to_send.append({"type": "text", "text": f"「{user_message}」の天気情報が見つかりませんでした。"})
    
    except Exception as e:
        print(f"Error in handle_message: {e}")
        messages_to_send.append({"type": "text", "text": "現在、データベースが準備中です。しばらくしてからもう一度お試しください。"})

    if messages_to_send:
        reply_to_line(event.reply_token, messages_to_send)

if __name__ == "__main__":
    if not all([CHANNEL_ACCESS_TOKEN, CHANNEL_SECRET, OPENWEATHER_API_KEY]):
        print("エラー: .envファイルに必要なキーが設定されていません。")
    else:
        app.run(port=5000)
