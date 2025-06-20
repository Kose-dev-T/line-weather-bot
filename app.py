# app.py (デバッグ版)
import os
print("--- [DEBUG] app.py SCRIPT START ---")

try:
    import requests
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
    import database
    import re
    print("--- [DEBUG] All initial imports successful ---")
except ImportError as e:
    print(f"--- [CRITICAL ERROR] Failed during initial imports: {e} ---")
    # インポートで失敗した場合、これ以降のログは表示されない

# --- 初期設定 ---
print("--- [DEBUG] Loading .env file... ---")
load_dotenv()
print("--- [DEBUG] .env file loaded ---")

print("--- [DEBUG] Initializing database... ---")
try:
    database.init_db()
    print("--- [DEBUG] database.init_db() executed successfully ---")
except Exception as e:
    print(f"--- [CRITICAL ERROR] Failed during database.init_db(): {e} ---")

# --- 環境変数からキー情報を取得 ---
print("--- [DEBUG] Reading environment variables... ---")
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")

if CHANNEL_ACCESS_TOKEN and CHANNEL_SECRET and OPENWEATHER_API_KEY:
    print("--- [DEBUG] All API keys and tokens loaded successfully ---")
else:
    print("--- [CRITICAL ERROR] One or more API keys/tokens are missing! ---")

# --- FlaskサーバーとLINE Bot APIの準備 ---
print("--- [DEBUG] Initializing Flask app... ---")
app = Flask(__name__)
print("--- [DEBUG] Flask app initialized ---")

print("--- [DEBUG] Initializing LINE Bot API clients... ---")
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
line_bot_api = MessagingApi(api_client)
handler = WebhookHandler(CHANNEL_SECRET)
print("--- [DEBUG] LINE Bot API clients initialized successfully ---")
print("--- [DEBUG] Top-level script execution finished. Ready to define routes. ---")


# (これ以降の関数定義やルート定義は、前回の完成版から変更ありません)
# ... (get_location_coords, get_weather_sticker, get_daily_forecast の関数定義)
# ... (@app.route("/callback"), @handler.add(...) の関数定義)
# ... (if __name__ == "__main__": のブロック)

# get_location_coords, get_weather_sticker, get_daily_forecast, callback, handle_follow, handle_postback, handle_message, if __name__ ...
# 上記の関数定義と最後のif文を、前回の完成版からここにコピー＆ペーストしてください。