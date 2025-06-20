import sqlite3

DB_NAME = "weather_bot.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            city_name TEXT,
            city_code TEXT,
            lat REAL,
            lon REAL
        )
    """)
    conn.commit()
    conn.close()

def set_user_location(user_id, city_name, city_code, lat=None, lon=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        INSERT INTO users (user_id, city_name, city_code, lat, lon)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            city_name=excluded.city_name,
            city_code=excluded.city_code,
            lat=excluded.lat,
            lon=excluded.lon
    """, (user_id, city_name, city_code, lat, lon))
    conn.commit()
    conn.close()

def get_user_location(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT city_name, city_code, lat, lon FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    if result:
        return {
            "city_name": result[0],
            "city_code": result[1],
            "lat": result[2],
            "lon": result[3]
        }
    return None

def set_user_state(user_id, state):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_states (
            user_id TEXT PRIMARY KEY,
            state TEXT
        )
    """)
    c.execute("""
        INSERT INTO user_states (user_id, state)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            state=excluded.state
    """, (user_id, state))
    conn.commit()
    conn.close()

def get_user_state(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT state FROM user_states WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None
