import os
import requests
import json
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent, PostbackEvent
from datetime import datetime
from dotenv import load_dotenv
import re
from sqlalchemy import create_engine, text

# --- 初期設定 ---
load_dotenv()
app = Flask(__name__)

# --- データベース設定と関数を、このファイル内に直接定義 ---
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
engine = create_engine(DATABASE_URL) if DATABASE_URL else None

def init_db():
    if not engine: return
    with engine.connect() as connection:
        connection.execute(text('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY, state TEXT, city_name TEXT, city_id TEXT
            )
        '''))
        connection.commit()

def set_user_state(user_id, state):
    if not engine: return
    with engine.connect() as connection:
        connection.execute(text("""
            INSERT INTO users (user_id, state) VALUES (:user_id, :state)
            ON CONFLICT(user_id) DO UPDATE SET state = :state
        """), {"user_id": user_id, "state": state})
        connection.commit()

def get_user_state(user_id):
    if not engine: return None
    with engine.connect() as connection:
        result = connection.execute(text("SELECT state FROM users WHERE user_id = :user_id"), {"user_id": user_id}).fetchone()
        return result[0] if result else None

def set_user_location(user_id, city_name, city_id):
    if not engine: return
    with engine.connect() as connection:
        connection.execute(text("""
            INSERT INTO users (user_id, state, city_name, city_id) VALUES (:user_id, 'normal', :city_name, :city_id)
            ON CONFLICT(user_id) DO UPDATE SET 
                state = 'normal', city_name = :city_name, city_id = :city_id
        """), {"user_id": user_id, "city_name": city_name, "city_id": city_id})
        connection.commit()

# --- アプリケーション起動時にDBを初期化 ---
with app.app_context():
    init_db()

# 環境変数からキー情報を取得
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")

handler = WebhookHandler(CHANNEL_SECRET)

# (これ以降のコードは、database.xxx() の呼び出しを、単なる xxx() に変更する以外は同じです)
# ...(get_location_coords, get_daily_forecast_message_dict, reply_to_line など)...
# ...(callback, handle_follow, handle_postback, handle_message など)...

if __name__ == "__main__":
    app.run(port=5000)
