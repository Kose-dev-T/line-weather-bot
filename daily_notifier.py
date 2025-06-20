import os
import requests
import json
from datetime import datetime
from dotenv import load_dotenv
import database
import sys

load_dotenv()
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")

def get_daily_forecast_message_dict(lat, lon, city_name):
    """OpenWeatherMap APIから天気予報を取得し、Flex Messageを生成する関数"""
    api_url = "https://api.openweathermap.org/data/2.5/forecast"
    # OpenWeatherMap APIのパラメータを設定
    params = {
        "lat": lat,
        "lon": lon,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",  # 摂氏で取得
        "lang": "ja"      # 日本語で取得
    }
    try:
        response = requests.get(api_url, params=params)
        response.raise_for_status()  # HTTPエラーがあれば例外を発生
        data = response.json()
        
        today_str = datetime.now().strftime('%Y-%m-%d')
        temp_max, temp_min, pop = -1000.0, 1000.0, 0.0 # float型で初期化
        weather_descriptions = []
        
        # 今日の日付の天気予報データを抽出
        for forecast in data["list"]:
            if today_str in forecast["dt_txt"]:
                temp_max = max(temp_max, forecast["main"]["temp_max"])
                temp_min = min(temp_min, forecast["main"]["temp_min"])
                pop = max(pop, forecast["pop"]) # popは降水確率 (0-1の範囲)
                
                # 天気の説明が重複しないようにリストに追加
                if forecast["weather"][0]["description"] not in weather_descriptions:
                    weather_descriptions.append(forecast["weather"][0]["description"])
        
        pop_percent = pop * 100 # 降水確率をパーセント表示に
        description = " / ".join(weather_descriptions) if weather_descriptions else "情報なし"
        
        # Flex MessageのJSON構造を定義
        flex_message = {
            "type": "flex", 
            "altText": f"{city_name}の天気予報", 
            "contents": { 
                "type": "bubble", 
                "direction": 'ltr',
                "header": {
                    "type": "box", 
                    "layout": "vertical", 
                    "contents": [
                        {"type": "text", "text": "今日の天気予報", "weight": "bold", "size": "xl", "color": "#FFFFFF", "align": "center"}
                    ], 
                    "backgroundColor": "#27A5F9", 
                    "paddingTop": "12px", 
                    "paddingBottom": "12px",
                    "cornerRadius": "md" # 角を丸くする
                },
                "body": {
                    "type": "box", 
                    "layout": "vertical", 
                    "spacing": "md", 
                    "contents": [
                        {"type": "box", "layout": "vertical", "contents": [
                            {"type": "text", "text": city_name, "size": "lg", "weight": "bold", "color": "#1DB446"},
                            {"type": "text", "text": datetime.now().strftime('%Y年%m月%d日'), "size": "sm", "color": "#AAAAAA"}
                        ]},
                        {"type": "separator", "margin": "md"},
                        {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm", "contents": [
                            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                                {"type": "text", "text": "天気", "color": "#AAAAAA", "size": "sm", "flex": 2},
                                {"type": "text", "text": description, "wrap": True, "color": "#666666", "size": "sm", "flex": 5}
                            ]},
                            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                                {"type": "text", "text": "最高気温", "color": "#AAAAAA", "size": "sm", "flex": 2},
                                {"type": "text", "text": f"{temp_max:.1f}°C", "wrap": True, "color": "#666666", "size": "sm", "flex": 5}
                            ]},
                            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                                {"type": "text", "text": "最低気温", "color": "#AAAAAA", "size": "sm", "flex": 2},
                                {"type": "text", "text": f"{temp_min:.1f}°C", "wrap": True, "color": "#666666", "size": "sm", "flex": 5}
                            ]},
                            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                                {"type": "text", "text": "降水確率", "color": "#AAAAAA", "size": "sm", "flex": 2},
                                {"type": "text", "text": f"{pop_percent:.0f}%", "wrap": True, "color": "#666666", "size": "sm", "flex": 5}
                            ]}
                        ]}
                    ]
                }
            }
        }
        return flex_message
    except Exception as e:
        print(f"天気予報APIエラーまたはFlex Message作成エラー: {e}")
        return {"type": "text", "text": "天気情報の取得に失敗しました。"}

def push_to_line(user_id, messages):
    """LINE Messaging APIを通じてユーザーにプッシュ通知を送信する関数"""
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
    """登録ユーザー全員にデイリー天気予報を送信する関数"""
    print("デイリー通知の送信を開始します...")
    database.init_db() # データベースの初期化
    users = database.get_all_users_with_location() # 登録されている全ユーザーと地点情報を取得
    
    if not users:
        print("通知対象のユーザーが見つかりませんでした。")
        return # ユーザーがいなければ処理を終了
    
    for user in users:
        # データベースから取得したuserデータの形式をチェック
        # OpenWeatherMap API を使用する場合、city_name, lat, lon が必要
        if isinstance(user, (list, tuple)) and len(user) >= 4:
            user_id, city_name, lat, lon = user[0], user[1], user[2], user[3]
            print(f"ユーザーID: {user_id}, 登録地: {city_name} (Lat: {lat}, Lon: {lon}) の天気予報を送信中...")
        else:
            print(f"エラー: データベースからのユーザーデータ形式が不正です: {user}。このユーザーはスキップします。")
            continue # 不正なデータ形式のユーザーはスキップ

        # OpenWeatherMap API を使用して天気予報を取得
        forecast_message = get_daily_forecast_message_dict(lat, lon, city_name)
        
        # LINEにプッシュ通知を送信
        if forecast_message: # メッセージが正常に生成された場合のみ送信
            push_to_line(user_id, [forecast_message])
        else:
            print(f"エラー: {city_name} の天気予報メッセージが生成できなかったため、通知をスキップしました。")
            push_to_line(user_id, [{"type": "text", "text": f"ご登録の地点「{city_name}」の天気情報が取得できず、本日の通知をスキップしました。お手数ですが、メニューから地点を再登録してください。"}])
            
    print("デイリー通知の送信が完了しました。")

if __name__ == "__main__":
    # 環境変数が設定されているか確認
    if not all([CHANNEL_ACCESS_TOKEN, OPENWEATHER_API_KEY]):
        print("エラー: .envファイルに必要なキーが設定されていないか、環境変数から読み込めていません。デイリー通知は実行されません。", file=sys.stderr)
    else:
        send_daily_forecasts()

