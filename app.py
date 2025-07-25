import os
import requests
import json
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent, PostbackEvent
# QuickReply機能に必要な部品をインポート
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage,
    QuickReply, QuickReplyButton, MessageAction
)
from datetime import datetime
from dotenv import load_dotenv
import database
import xml.etree.ElementTree as ET

# --- 初期設定 ---
load_dotenv()
app = Flask(__name__)

with app.app_context():
    database.init_db()

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")

handler = WebhookHandler(CHANNEL_SECRET)

# --- グローバル変数 ---
AREA_DATA_CACHE = None

# --- 補助関数群 ---
def get_area_data():
    """livedoor互換APIの都市リストXMLを取得・キャッシュする関数"""
    global AREA_DATA_CACHE
    if AREA_DATA_CACHE is not None:
        return AREA_DATA_CACHE
    try:
        response = requests.get("https://weather.tsukumijima.net/primary_area.xml")
        response.raise_for_status()
        try:
            AREA_DATA_CACHE = ET.fromstring(response.content.decode('euc-jp'))
        except Exception:
            AREA_DATA_CACHE = ET.fromstring(response.content.decode('utf-8'))
        print("地域・都市リストをダウンロード・キャッシュしました。")
        return AREA_DATA_CACHE
    except Exception as e:
        print(f"地域・都市リストの取得に失敗しました: {e}")
        return None

def create_quick_reply(options):
    """選択肢のリストからQuickReplyボタンを作成する関数"""
    if len(options) > 13:
        options = options[:13] # LINEのQuickReplyは最大13個
    items = [QuickReplyButton(action=MessageAction(label=opt, text=opt)) for opt in options]
    return QuickReply(items=items)

def reply_to_line(reply_token, text, quick_reply=None):
    """LINEにメッセージを返信する関数"""
    headers = {"Content-Type": "application/json; charset=UTF-8", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
    message_payload = {"type": "text", "text": text}
    if quick_reply:
        message_payload["quickReply"] = quick_reply.to_dict()
    body = {"replyToken": reply_token, "messages": [message_payload]}
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

def start_location_setting(event):
    """地点登録/変更のフローを開始する関数"""
    user_id = event.source.user_id
    database.set_user_state(user_id, 'waiting_for_area')
    area_data = get_area_data()
    if not area_data:
        reply_to_line(event.reply_token, "地域情報の取得に失敗しました。しばらくしてからお試しください。")
        return
    area_names = [area.get('title') for area in area_data.findall('.//area')]
    quick_reply = create_quick_reply(area_names)
    reply_to_line(event.reply_token, "お住まいのエリアを選択してください。", quick_reply)

# --- イベントごとの処理 ---
@handler.add(FollowEvent)
def handle_follow(event):
    start_location_setting(event)

@handler.add(PostbackEvent)
def handle_postback(event):
    if event.postback.data == 'action=change_location':
        start_location_setting(event)

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text
    user_state = database.get_user_state(user_id)
    
    area_data = get_area_data()
    if not area_data:
        reply_to_line(event.reply_token, "地域情報の取得に失敗しました。")
        return

    if user_state == 'waiting_for_area':
        selected_area = area_data.find(f".//area[@title='{user_message}']")
        if selected_area:
            pref_names = [pref.get('title') for pref in selected_area.findall('pref')]
            quick_reply = create_quick_reply(pref_names)
            database.set_user_state(user_id, f'waiting_for_pref:{user_message}')
            reply_to_line(event.reply_token, "次に都道府県を選択してください。", quick_reply)
        else:
            reply_to_line(event.reply_token, "ボタンから正しいエリア名を選択してください。")
    elif user_state and user_state.startswith('waiting_for_pref:'):
        area_name = user_state.split(':')[1]
        selected_area = area_data.find(f".//area[@title='{area_name}']")
        selected_pref = selected_area.find(f".//pref[@title='{user_message}']") if selected_area else None
        if selected_pref:
            city_names = [city.get('title') for city in selected_pref.findall('city')]
            quick_reply = create_quick_reply(city_names)
            database.set_user_state(user_id, f'waiting_for_city:{user_message}')
            reply_to_line(event.reply_token, "最後に都市名を選択してください。", quick_reply)
        else:
            reply_to_line(event.reply_token, "ボタンから正しい都道府県名を選択してください。")
    elif user_state and user_state.startswith('waiting_for_city:'):
        pref_name = user_state.split(':')[1]
        selected_city_element = area_data.find(f".//pref[@title='{pref_name}']/city[@title='{user_message}']")
        if selected_city_element is not None:
            city_id = selected_city_element.get('id')
            city_name = selected_city_element.get('title')
            database.set_user_location(user_id, city_name, city_id)
            reply_to_line(event.reply_token, f"地点を「{city_name}」に設定しました！\n明日から毎朝、天気予報をお届けします。")
        else:
            reply_to_line(event.reply_token, "ボタンから正しい都市名を選択してください。")
    else:
        reply_to_line(event.reply_token, "メニューの「地点を変更する」から、通知先を設定してください。")

if __name__ == "__main__":
    app.run(port=5000)
