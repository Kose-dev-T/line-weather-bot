import os
import requests
import json
from datetime import datetime
from dotenv import load_dotenv
import database
import xml.etree.ElementTree as ET

load_dotenv()

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

def get_daily_forecast(city_code, city_name):
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
        return message
    except Exception as e:
        print(f"天気取得エラー: {e}")
        return "天気情報の取得に失敗しました。"

def send_daily_notifications():
    users = database.get_all_users()
    for user in users:
        user_id = user["user_id"]
        city_name = user["city_name"]
        city_code = user["city_code"]
        message = get_daily_forecast(city_code, city_name)
        print(f"送信先: {user_id}\n{message}\n")

if __name__ == "__main__":
    send_daily_notifications()
