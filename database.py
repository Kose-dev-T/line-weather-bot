import sqlite3

DATABASE_FILE = "weather_bot.db"

def init_db():
    """データベースとテーブルを初期化（なければ作成）する関数"""
    with sqlite3.connect(DATABASE_FILE) as con:
        cur = con.cursor()
        # usersテーブル: ユーザーID、状態、登録地名、緯度、経度を保存
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                state TEXT,
                city_name TEXT,
                lat REAL,
                lon REAL
            )
        ''')
        con.commit()

def set_user_state(user_id, state):
    """ユーザーの状態（例: 'waiting_for_location'）を設定する関数"""
    with sqlite3.connect(DATABASE_FILE) as con:
        cur = con.cursor()
        cur.execute("INSERT OR REPLACE INTO users (user_id, state) VALUES (?, ?)", (user_id, state))
        con.commit()

def get_user_state(user_id):
    """ユーザーの状態を取得する関数"""
    with sqlite3.connect(DATABASE_FILE) as con:
        cur = con.cursor()
        cur.execute("SELECT state FROM users WHERE user_id = ?", (user_id,))
        result = cur.fetchone()
        return result[0] if result else None

def set_user_location(user_id, city_name, lat, lon):
    """ユーザーの登録地と、状態を'normal'にリセットする関数"""
    with sqlite3.connect(DATABASE_FILE) as con:
        cur = con.cursor()
        cur.execute('''
            INSERT OR REPLACE INTO users (user_id, state, city_name, lat, lon) 
            VALUES (?, 'normal', ?, ?, ?)
        ''', (user_id, city_name, lat, lon))
        con.commit()

def get_user_location(user_id):
    """ユーザーの登録地を取得する関数"""
    with sqlite3.connect(DATABASE_FILE) as con:
        cur = con.cursor()
        cur.execute("SELECT city_name, lat, lon FROM users WHERE user_id = ?", (user_id,))
        return cur.fetchone()
        
def get_all_users_with_location():
    """登録地がある全ユーザーの情報を取得する関数（自動通知用）"""
    with sqlite3.connect(DATABASE_FILE) as con:
        cur = con.cursor()
        cur.execute("SELECT user_id, city_name, lat, lon FROM users WHERE city_name IS NOT NULL")
        return cur.fetchall()