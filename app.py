import os
import requests
import json
import xml.etree.ElementTree as ET
from flask import Flask, request, abort
from datetime import datetime
from dotenv import load_dotenv
import database

# --- 初期設定 ---
load_dotenv()
app = Flask(__name__)

with app.app_context():
    database.init_db()

# --- 地域コード取得 ---
def fetch_city_code_map():
    url = "https://weather.tsukumijima.net/primary_area.xml"
    try:
        response = requests.get(url)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        city_map = {}
        for pref in root.findall(".//pref"):
            for area in pref.findall("area"):
                for info in area.findall("info"):
                    city_name = info.find("city").text
                    city_code = info.get("id")
                    city_map[city_name] = city_code
        return city_map
    except Exception as e:
        print(f"XML取得エラー: {e}")
        return {}

CITY_CODE_MAP = fetch_city_code_map()

def get_city_code(city_name):
    return CITY_CODE_MAP.get(city_name)

# --- 天気取得関数 ---
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

        message = f"{city_name}の天気予報（{datetime.now().strftime('%Y年%m月%d日')}）\n"
        message += f"天気: {telop}\n"
        message += f"最高気温: {temp_max}°C\n"
        message += f"最低気温: {temp_min}°C\n"
        message += f"{description}"
        return {"type": "text", "text": message}
    except Exception as e:
        print(f"天気取得エラー: {e}")
        return {"type": "text", "text": "天気情報の取得に失敗しました。"}

# --- ユーザー入力処理（仮） ---
def handle_user_input(user_id, user_message):
    user_state = database.get_user_state(user_id)
    messages_to_send = []

    city_code = get_city_code(user_message)
    if user_state == 'waiting_for_location':
        if city_code:
            database.set_user_location(user_id, user_message, city_code, 0)
            messages_to_send.append({"type": "text", "text": f"地点を「{user_message}」に設定しました。\n明日から毎日0時に天気予報をお届けします！"})
        else:
            messages_to_send.append({"type": "text", "text": f"「{user_message}」が見つかりませんでした。もう一度、市町村名などで入力してください。"})
    else:
        if city_code:
            forecast_message = get_daily_forecast_message_dict(city_code, user_message)
            messages_to_send.append(forecast_message)
        else:
            messages_to_send.append({"type": "text", "text": f"「{user_message}」という地名が見つかりませんでした。"})

    if __name__ == "__main__":
         port = int(os.environ.get("PORT", 5000))
         app.run(host="0.0.0.0", port=port)


    return messages_to_send
