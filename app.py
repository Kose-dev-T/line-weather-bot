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
import xml.etree.ElementTree as ET # XMLを解析するためにインポート

# --- 初期設定 ---
load_dotenv()
app = Flask(__name__)

with app.app_context():
    database.init_db()

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
# 【修正】地名から都道府県を特定するために、OpenWeatherMapのAPIキーも読み込みます
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")

handler = WebhookHandler(CHANNEL_SECRET)

# --- グローバル変数 ---
CITY_LIST_CACHE = None

# --- 補助関数群 ---

def get_city_id(user_input_city):
    """
    ユーザーが入力した地名から、最も関連性の高い主要都市のIDを返す関数。
    (daily_notifier.pyと全く同じ関数です)
    """
    global CITY_LIST_CACHE
    
    try:
        geo_api_url = "http://api.openweathermap.org/geo/1.0/direct"
        geo_params = {"q": f"{user_input_city},JP", "limit": 1, "appid": OPENWEATHER_API_KEY}
        geo_res = requests.get(geo_api_url, params=geo_params)
        geo_res.raise_for_status()
        geo_data = geo_res.json()
        if not geo_data or "state" not in geo_data[0]:
            print(f"OWM Geocoding API did not find a prefecture for '{user_input_city}'")
            return None
        prefecture_en = geo_data[0]["state"]
    except Exception as e:
        print(f"Error getting prefecture from OWM: {e}")
        return None

    prefecture_map = {
        "Hokkaido": "北海道", "Aomori": "青森", "Iwate": "岩手", "Miyagi": "宮城", 
        "Akita": "秋田", "Yamagata": "山形", "Fukushima": "福島", "Ibaraki": "茨城", 
        "Tochigi": "栃木", "Gunma": "群馬", "Saitama": "埼玉", "Chiba": "千葉", 
        "Tokyo": "東京", "Kanagawa": "神奈川", "Niigata": "新潟", "Toyama": "富山", 
        "Ishikawa": "石川", "Fukui": "福井", "Yamanashi": "山梨", "Nagano": "長野", 
        "Gifu": "岐阜", "Shizuoka": "静岡", "Aichi": "愛知", "Mie": "三重", 
        "Shiga": "滋賀", "Kyoto": "京都", "Osaka": "大阪", "Hyogo": "兵庫", 
        "Nara": "奈良", "Wakayama": "和歌山", "Tottori": "鳥取", "Shimane": "島根", 
        "Okayama": "岡山", "Hiroshima": "広島", "Yamaguchi": "山口", 
        "Tokushima": "徳島", "Kagawa": "香川", "Ehime": "愛媛", "Kochi": "高知", 
        "Fukuoka": "福岡", "Saga": "佐賀", "Nagasaki": "長崎", "Kumamoto": "熊本", 
        "Oita": "大分", "Miyazaki": "宮崎", "Kagoshima": "鹿児島", "Okinawa": "沖縄"
    }
    prefecture_jp_short = prefecture_map.get(prefecture_en)
    
    if not prefecture_jp_short:
        print(f"Could not map English prefecture '{prefecture_en}' to Japanese.")
        return None

    if CITY_LIST_CACHE is None:
        try:
            response = requests.get("https://weather.tsukumijima.net/primary_area.xml")
            response.raise_for_status()
            CITY_LIST_CACHE = ET.fromstring(response.content.decode('utf-8'))
            print("都市リストをダウンロード・キャッシュしました。")
        except Exception as e:
            print(f"都市リストの取得に失敗しました: {e}")
            return None
            
    pref_element = CITY_LIST_CACHE.find(f".//pref[@title='{prefecture_jp_short}']")
    
    if pref_element is not None:
        first_city = pref_element.find('city')
        if first_city is not None:
            city_id = first_city.get('id')
            print(f"Input '{user_input_city}' resolved to prefecture '{prefecture_jp_short}' and primary city ID '{city_id}'")
            return city_id
    
    print(f"Could not find a primary city for prefecture '{prefecture_jp_short}' in the XML list.")
    return None

def get_livedoor_forecast_message_dict(city_id):
    """指定された都市IDの天気予報を取得する関数 (daily_notifier.pyと全く同じ)"""
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
    user_state = database.get_user_state(user_id)
    messages_to_send = []
    
    # 【修正】賢くなったget_city_idを呼び出す
    city_id = get_city_id(user_message)
    
    if user_state == 'waiting_for_location':
        if city_id:
            # データベースには元のユーザー入力を保存する
            database.set_user_location(user_id, user_message, 0, 0)
            messages_to_send.append({"type": "text", "text": f"地点を「{user_message}」に設定しました。\n明日から登録地点の天気予報をお届けします！"})
        else:
            messages_to_send.append({"type": "text", "text": f"「{user_message}」が見つかりませんでした。日本の市町村名などで入力してください。"})
    else:
        if city_id:
            forecast_message = get_livedoor_forecast_message_dict(city_id)
            messages_to_send.append(forecast_message)
        else:
            messages_to_send.append({"type": "text", "text": f"「{user_message}」の天気情報が見つかりませんでした。"})
            
    if messages_to_send:
        reply_to_line(event.reply_token, messages_to_send)

if __name__ == "__main__":
    if not all([CHANNEL_ACCESS_TOKEN, CHANNEL_SECRET, OPENWEATHER_API_KEY]):
        print("エラー: .envファイルに必要なキーが設定されていません。")
    else:
        app.run(port=5000)
