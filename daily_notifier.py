import os
import requests
import json
from datetime import datetime
from dotenv import load_dotenv
import database

# --- 初期設定 ---
load_dotenv()
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")

# --- グローバル変数 ---
JMA_AREA_DATA = None

# --- 補助関数群（app.pyからコピー） ---

def get_jma_area_info(city_name):
    global JMA_AREA_DATA
    geo_api_url = "http://api.openweathermap.org/geo/1.0/direct"
    geo_params = {"q": f"{city_name},JP", "limit": 1, "appid": OPENWEATHER_API_KEY}
    try:
        geo_res = requests.get(geo_api_url, params=geo_params)
        geo_res.raise_for_status()
        geo_data = geo_res.json()
        if not geo_data: return None
        
        prefecture_en = geo_data[0].get("state", "")
        prefecture_map = {"Hokkaido": "北海道", "Aomori": "青森県", "Iwate": "岩手県", "Miyagi": "宮城県", "Akita": "秋田県", "Yamagata": "山形県", "Fukushima": "福島県", "Ibaraki": "茨城県", "Tochigi": "栃木県", "Gunma": "群馬県", "Saitama": "埼玉県", "Chiba": "千葉県", "Tokyo": "東京都", "Kanagawa": "神奈川県", "Niigata": "新潟県", "Toyama": "富山県", "Ishikawa": "石川県", "Fukui": "福井県", "Yamanashi": "山梨県", "Nagano": "長野県", "Gifu": "岐阜県", "Shizuoka": "静岡県", "Aichi": "愛知県", "Mie": "三重県", "Shiga": "滋賀県", "Kyoto": "京都府", "Osaka": "大阪府", "Hyogo": "兵庫県", "Nara": "奈良県", "Wakayama": "和歌山県", "Tottori": "鳥取県", "Shimane": "島根県", "Okayama": "岡山県", "Hiroshima": "広島県", "Yamaguchi": "山口県", "Tokushima": "徳島県", "Kagawa": "香川県", "Ehime": "愛媛県", "Kochi": "高知県", "Fukuoka": "福岡県", "Saga": "佐賀県", "Nagasaki": "長崎県", "Kumamoto": "熊本県", "Oita": "大分県", "Miyazaki": "宮崎県", "Kagoshima": "鹿児島県", "Okinawa": "沖縄県"}
        prefecture_jp = prefecture_map.get(prefecture_en)
        if not prefecture_jp: return None

        if JMA_AREA_DATA is None:
            area_res = requests.get("https://www.jma.go.jp/bosai/common/const/area.json")
            area_res.raise_for_status()
            JMA_AREA_DATA = area_res.json()
            print("気象庁エリアデータを取得・キャッシュしました。")

        office_code = None
        for code, info in JMA_AREA_DATA["offices"].items():
            if info["name"] == prefecture_jp:
                office_code = code
                break
        if not office_code: return None
        
        first_area_code = JMA_AREA_DATA["offices"][office_code]["children"][0]
        area_name = JMA_AREA_DATA["class20s"][first_area_code]["name"]
        
        return {"office_code": office_code, "area_code": first_area_code, "area_name": area_name}
    except Exception as e:
        print(f"JMA Area Info Error: {e}")
        return None

def get_jma_forecast_message_dict(office_code, area_code, area_name):
    api_url = f"https://www.jma.go.jp/bosai/forecast/data/forecast/{office_code}.json"
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()
        time_series = data[0]["timeSeries"]
        weather_area = next(area for area in time_series[0]["areas"] if area["area"]["code"] == area_code)
        today_weather = weather_area["weathers"][0].replace("　", " ")
        pops_area = time_series[1]["areas"][0]
        pops = [p for p in pops_area["pops"] if p != "--"]
        pop_today = max(map(int, pops[:2])) if len(pops) >= 2 else (pops[0] if pops else "---")
        temp_area = next(area for area in time_series[2]["areas"] if area["area"]["code"] == area_code)
        temp_max = temp_area["temps"][0]
        temp_min = temp_area["temps"][1]
        
        flex_message = {
            "type": "flex", "altText": f"{area_name}の天気予報 (気象庁)",
            "contents": { "type": "bubble", "direction": 'ltr',
                "header": {"type": "box", "layout": "vertical", "contents": [
                    {"type": "text", "text": "今日の天気予報 (気象庁)", "weight": "bold", "size": "xl", "color": "#FFFFFF", "align": "center"}
                ], "backgroundColor": "#27A5F9", "paddingTop": "12px", "paddingBottom": "12px"},
                "body": {"type": "box", "layout": "vertical", "spacing": "md", "contents": [
                    {"type": "box", "layout": "vertical", "contents": [
                        {"type": "text", "text": area_name, "size": "lg", "weight": "bold", "color": "#1DB446"},
                        {"type": "text", "text": datetime.now().strftime('%Y年%m月%d日'), "size": "sm", "color": "#AAAAAA"}]},
                    {"type": "separator", "margin": "md"},
                    {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm", "contents": [
                        {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                            {"type": "text", "text": "天気", "color": "#AAAAAA", "size": "sm", "flex": 2},
                            {"type": "text", "text": today_weather, "wrap": True, "color": "#666666", "size": "sm", "flex": 5}]},
                        {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                            {"type": "text", "text": "最高気温", "color": "#AAAAAA", "size": "sm", "flex": 2},
                            {"type": "text", "text": f"{temp_max}°C", "wrap": True, "color": "#666666", "size": "sm", "flex": 5}]},
                        {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                            {"type": "text", "text": "最低気温", "color": "#AAAAAA", "size": "sm", "flex": 2},
                            {"type": "text", "text": f"{temp_min}°C", "wrap": True, "color": "#666666", "size": "sm", "flex": 5}]},
                        {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                            {"type": "text", "text": "降水確率", "color": "#AAAAAA", "size": "sm", "flex": 2},
                            {"type": "text", "text": f"{pop_today}%", "wrap": True, "color": "#666666", "size": "sm", "flex": 5}]}
                    ]}
                ]}
            }
        }
        return flex_message
    except Exception as e:
        print(f"JMA Forecast API Error: {e}")
        return {"type": "text", "text": "気象庁からの天気情報取得に失敗しました。"}

def push_to_line(user_id, messages):
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
    print("デイリー通知の送信を開始します...")
    database.init_db()
    users = database.get_all_users_with_location()
    
    if not users:
        print("通知対象のユーザーが見つかりませんでした。")
    
    for user in users:
        user_id, city_name, lat, lon = user
        print(f"登録地「{city_name}」({user_id})の天気予報を送信中...")
        
        area_info = get_jma_area_info(city_name)
        if area_info:
            forecast_message = get_jma_forecast_message_dict(area_info["office_code"], area_info["area_code"], area_info["area_name"])
            push_to_line(user_id, [forecast_message])
        else:
            print(f"「{city_name}」のエリア情報が見つからなかったため、送信をスキップします。")
            push_to_line(user_id, [{"type": "text", "text": f"ご登録の地点「{city_name}」の気象庁情報が見つからず、本日の通知をスキップしました。お手数ですが、メニューから地点を再登録してください。"}])
            
    print("デイリー通知の送信が完了しました。")

if __name__ == "__main__":
    if not all([CHANNEL_ACCESS_TOKEN, OPENWEATHER_API_KEY]):
        print("エラー: .envファイルに必要なキーが設定されていません。")
    else:
        send_daily_forecasts()