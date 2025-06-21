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
# OpenWeatherMapのキーは不要になるので、後で.envファイルから削除してもOKです

handler = WebhookHandler(CHANNEL_SECRET)

# --- グローバル変数（都市IDリストのキャッシュ用） ---
CITY_LIST_CACHE = None

# --- 補助関数群 ---

def get_city_id(user_input_city):
    """ユーザーが入力した地名に最も近い都市IDを探す関数"""
    global CITY_LIST_CACHE
    
    # 都市リストをまだ取得していなければ、ダウンロードしてキャッシュする
    if CITY_LIST_CACHE is None:
        try:
            # Weather Hacks互換APIが提供する都市リスト(XML形式)
            response = requests.get("https://weather.tsukumijima.net/primary_area.xml")
            response.raise_for_status()
            CITY_LIST_CACHE = ET.fromstring(response.content)
            print("都市リストをダウンロード・キャッシュしました。")
        except Exception as e:
            print(f"都市リストの取得に失敗しました: {e}")
            return None

    # 検索のために、ユーザー入力の「市」や「町」などを削除する
    search_term = user_input_city.replace('市', '').replace('町', '').replace('村', '').replace('区', '')

    # 1. 完全一致で検索
    perfect_match = CITY_LIST_CACHE.find(f".//city[@title='{search_term}']")
    if perfect_match is not None:
        return perfect_match.get('id')
    
    # 2. 部分一致で検索
    for city in CITY_LIST_CACHE.findall('.//city'):
        if search_term in city.get('title'):
            return city.get('id')

    # 見つからなければNoneを返す
    return None

def get_livedoor_forecast_message_dict(city_id):
    """指定された都市IDの天気予報を取得する関数"""
    api_url = f"https://weather.tsukumijima.net/api/forecast?city={city_id}"
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()
        
        # 今日の予報を取得
        today_forecast = data["forecasts"][0]
        
        city_name = data["location"]["city"]
        weather = today_forecast["telop"]
        temp_max_obj = today_forecast["temperature"]["max"]
        temp_min_obj = today_forecast["temperature"]["min"]
        
        # 気温データがない場合（null）の対策
        temp_max = temp_max_obj["celsius"] if temp_max_obj else "--"
        temp_min = temp_min_obj["celsius"] if temp_min_obj else "--"

        # 降水確率を取得
        chance_of_rain = " / ".join(today_forecast["chanceOfRain"].values())

        # FlexMessageを作成
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
    
    city_id = get_city_id(user_message)
    
    if user_state == 'waiting_for_location':
        if city_id:
            database.set_user_location(user_id, user_message, 0, 0) # lat,lonはもう使わない
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
    app.run(port=5000)
