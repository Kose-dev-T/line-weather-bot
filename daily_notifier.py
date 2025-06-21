import os
import requests
import json
from datetime import datetime
from dotenv import load_dotenv
import database
import xml.etree.ElementTree as ET

# --- 初期設定 ---
load_dotenv()
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
# 地名から都道府県を特定するために、OpenWeatherMapのAPIキーも読み込みます
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")

# --- グローバル変数 ---
CITY_LIST_CACHE = None

# --- 補助関数群（app.pyからコピー） ---

def get_city_id(user_input_city):
    """
    ユーザーが入力した地名から、最も関連性の高い主要都市のIDを返す関数。
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
            # XMLの文字コードがEUC-JPの場合を考慮してデコードを試みる
            try:
                CITY_LIST_CACHE = ET.fromstring(response.content.decode('euc-jp'))
            except Exception:
                CITY_LIST_CACHE = ET.fromstring(response.content.decode('utf-8'))
            print("都市リストをダウンロード・キャッシュしました。")
        except Exception as e:
            print(f"都市リストの取得に失敗しました: {e}")
            return None
            
    # XML全体からcityタグを直接検索する
    search_term = user_input_city.replace('市', '').replace('町', '').replace('村', '').replace('区', '')
    perfect_match = CITY_LIST_CACHE.find(f".//city[@title='{search_term}']")
    if perfect_match is not None:
        city_id = perfect_match.get('id')
        print(f"Direct match found for '{search_term}'. City ID: {city_id}")
        return city_id

    # 直接一致がなければ、特定した都道府県の最初の都市（主要都市）のIDを返す
    pref_element = CITY_LIST_CACHE.find(f".//pref[@title='{prefecture_jp_short}']")
    
    if pref_element is not None:
        first_city = pref_element.find('city')
        if first_city is not None:
            city_id = first_city.get('id')
            print(f"Input '{user_input_city}' resolved to prefecture '{prefecture_jp_short}' and primary city ID '{city_id}'")
            return city_id
    
    print(f"Could not find any match for '{user_input_city}'.")
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

def push_to_line(user_id, messages):
    """requestsを使って、LINEにプッシュ通知を送信する関数"""
    headers = {"Content-Type": "application/json; charset=UTF-8", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
    body = {"to": user_id, "messages": messages}
    try:
        response = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, data=json.dumps(body, ensure_ascii=False).encode('utf-8'))
        response.raise_for_status()
        print(f"ユーザー({user_id})への通知が成功しました。")
    except requests.exceptions.RequestException as e:
        print(f"ユーザー({user_id})へのLINE通知エラー: {e}")
        if e.response: print(f"応答内容: {e.response.text}")

def send_daily_forecasts():
    """登録ユーザー全員に天気予報を通知するメイン関数"""
    print("デイリー通知の送信を開始します...")
    database.init_db()
    users = database.get_all_users_with_location()
    
    if not users:
        print("通知対象のユーザーが見つかりませんでした。")
    
    for user in users:
        user_id, city_name, lat, lon = user
        print(f"登録地「{city_name}」({user_id})の天気予報を送信中...")
        
        # データベースに保存された地名から都市IDを取得
        city_id = get_city_id(city_name)
        if city_id:
            forecast_message = get_livedoor_forecast_message_dict(city_id)
            push_to_line(user_id, [forecast_message])
        else:
            print(f"「{city_name}」の都市IDが見つからなかったため、送信をスキップします。")
            error_message = {"type": "text", "text": f"ご登録の地点「{city_name}」の天気情報が見つかりませんでした。お手数ですが、メニューから地点を再登録してください。"}
            push_to_line(user_id, [error_message])
            
    print("デイリー通知の送信が完了しました。")

# --- メインの実行部分 ---
if __name__ == "__main__":
    if not all([CHANNEL_ACCESS_TOKEN, OPENWEATHER_API_KEY]):
        print("エラー: .envファイルにCHANNEL_ACCESS_TOKENとOPENWEATHER_API_KEYが設定されていません。")
    else:
        send_daily_forecasts()