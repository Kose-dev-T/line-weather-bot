# app.py (最終完成版)
import os
import requests
import json
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage, StickerSendMessage,
    FlexSendMessage, BubbleContainer, BoxComponent, TextComponent, SeparatorComponent
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent, PostbackEvent
from datetime import datetime
from dotenv import load_dotenv
import database # 作成したdatabase.pyをインポート

# --- 初期設定 ---
load_dotenv()

# --- FlaskサーバーとLINE Bot APIの準備 ---
app = Flask(__name__) # まずFlaskアプリ本体を作成する

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")

# キーが設定されているかチェック
if not all([CHANNEL_ACCESS_TOKEN, CHANNEL_SECRET, OPENWEATHER_API_KEY]):
    print("エラー: 必要な環境変数が設定されていません。")
    # exit() # ここでは終了させずに続行させる

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
line_bot_api = MessagingApi(api_client)
handler = WebhookHandler(CHANNEL_SECRET)

# --- データベースの初期化 ---
# アプリケーションのコンテキスト内で安全に実行
with app.app_context():
    database.init_db()

# (これ以降の関数定義は、以前の完成版から変更ありません)
# ... (get_location_coords, get_daily_forecast, ... handle_message の関数定義)
# ...

# 最後の if __name__ == "__main__": ブロックは、ローカルテスト用なので
# Renderでは使われませんが、念のため残しておきます。
if __name__ == "__main__":
    app.run(port=5000)