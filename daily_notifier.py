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
def get_jma_area_info(city_name_input):
    """
    ユーザーが入力した地名から、対応する気象庁のエリアコードなどを特定する関数。
    OpenWeatherMapで緯度経度と都道府県を特定し、その情報をもとにJMAのエリアコードを検索する。
    市区町村レベルの地名に対応できるよう、class20s (予報区) の名称も考慮する。
    """
    global JMA_AREA_DATA
    
    geo_api_url = "http://api.openweathermap.org/geo/1.0/direct"
    # city_name_input はユーザーが入力した地名（例: 大阪市、横浜市、東京都）
    geo_params = {"q": f"{city_name_input},JP", "limit": 1, "appid": OPENWEATHER_API_KEY}
    
    try:
        geo_res = requests.get(geo_api_url, params=geo_params)
        geo_res.raise_for_status()
        geo_data = geo_res.json()
        
        if not geo_data:
            print(f"OpenWeatherMapで'{city_name_input}'の地理情報が見つかりませんでした。")
            return None
        
        # OpenWeatherMapから都道府県の英語名を取得
        prefecture_en = geo_data[0].get("state", "")
        # 気象庁のエリアデータ取得前に都道府県が特定できない場合はNoneを返す
        if not prefecture_en:
            print(f"OpenWeatherMapで'{city_name_input}'の都道府県情報が見つかりませんでした。")
            return None

        # 英語都道府県名を日本語にマッピング
        prefecture_map = {
            "Hokkaido": "北海道", "Aomori": "青森県", "Iwate": "岩手県", "Miyagi": "宮城県", "Akita": "秋田県", "Yamagata": "山形県", "Fukushima": "福島県",
            "Ibaraki": "茨城県", "Tochigi": "栃木県", "Gunma": "群馬県", "Saitama": "埼玉県", "Chiba": "千葉県", "Tokyo": "東京都", "Kanagawa": "神奈川県",
            "Niigata": "新潟県", "Toyama": "富山県", "Ishikawa": "石川県", "Fukui": "福井県", "Yamanashi": "山梨県", "Nagano": "長野県", "Gifu": "岐阜県",
            "Shizuoka": "静岡県", "Aichi": "愛知県", "Mie": "三重県", "Shiga": "滋賀県", "Kyoto": "京都府", "Osaka": "大阪府", "Hyogo": "兵庫県",
            "Nara": "奈良県", "Wakayama": "和歌山県", "Tottori": "鳥取県", "Shimane": "島根県", "Okayama": "岡山県", "Hiroshima": "広島県", "Yamaguchi": "山口県",
            "Tokushima": "徳島県", "Kagawa": "香川県", "Ehime": "愛媛県", "Kochi": "高知県", "Fukuoka": "福岡県", "Saga": "佐賀県", "Nagasaki": "長崎県",
            "Kumamoto": "熊本県", "Oita": "大分県", "Miyazaki": "宮崎県", "Kagoshima": "鹿児島県", "Okinawa": "沖縄県"
        }
        prefecture_jp = prefecture_map.get(prefecture_en)
        
        if not prefecture_jp:
            print(f"警告: 英語の都道府県名 '{prefecture_en}' を日本語にマッピングできませんでした。")
            return None

        # 気象庁エリアデータをキャッシュ（初回のみ取得）
        if JMA_AREA_DATA is None:
            area_res = requests.get("https://www.jma.go.jp/bosai/common/const/area.json")
            area_res.raise_for_status()
            JMA_AREA_DATA = area_res.json()
            print("気象庁エリアデータを取得・キャッシュしました。")

        # 日本語都道府県名から、気象庁の「office」（管区気象台など）の短い名称をマッピング
        # 例: 「東京都」->「東京」、「大阪府」->「大阪」
        jma_office_short_name_map = {
            "北海道": "札幌", "青森県": "青森", "岩手県": "盛岡", "宮城県": "仙台", "秋田県": "秋田", "山形県": "山形", "福島県": "福島",
            "茨城県": "水戸", "栃木県": "宇都宮", "群馬県": "前橋", "埼玉県": "熊谷", "千葉県": "千葉", "東京都": "東京", "神奈川県": "横浜",
            "新潟県": "新潟", "富山県": "富山", "石川県": "金沢", "福井県": "福井", "山梨県": "甲府", "長野県": "長野", "岐阜県": "岐阜",
            "静岡県": "静岡", "愛知県": "名古屋", "三重県": "津", "滋賀県": "彦根", "京都府": "京都", "大阪府": "大阪", "兵庫県": "神戸",
            "奈良県": "奈良", "和歌山県": "和歌山", "鳥取県": "鳥取", "島根県": "松江", "岡山県": "岡山", "広島県": "広島", "山口県": "山口",
            "徳島県": "徳島", "香川県": "高松", "愛媛県": "松山", "高知県": "高知", "福岡県": "福岡", "佐賀県": "佐賀", "長崎県": "長崎",
            "熊本県": "熊本", "大分県": "大分", "宮崎県": "宮崎", "鹿児島県": "鹿児島", "沖縄県": "那覇"
        }
        
        target_jma_office_name = jma_office_short_name_map.get(prefecture_jp, prefecture_jp) 
        
        office_code = None
        for code, info in JMA_AREA_DATA["offices"].items():
            if info["name"] == target_jma_office_name:
                office_code = code
                break
        
        if not office_code:
            print(f"エラー: 目標のJMAオフィス名 '{target_jma_office_name}' のオフィスコードが見つかりませんでした。")
            return None
        
        # 該当オフィスが管轄するclass20s（予報区）のコードを取得
        related_class20s_codes = JMA_AREA_DATA["offices"][office_code]["children"]
        
        found_area_code = None
        found_area_name = None

        # ユーザー入力の地名に最も一致する予報区 (class20s) を探す (より具体的な市区町村レベルの対応)
        # class20s の名前やかなにユーザーの入力地名が含まれるか、完全一致するかを試みる
        
        # 正規化のため、ユーザー入力を全角/半角スペースなしの小文字に変換
        normalized_input = city_name_input.replace(' ', '').replace('　', '').lower()
        
        # 候補を格納するリスト (スコア: 3=完全一致、2=部分一致(name)、1=部分一致(kana))
        candidate_matches = []

        for c20_code in related_class20s_codes:
            c20_info = JMA_AREA_DATA["class20s"].get(c20_code, {})
            c20_name = c20_info.get("name", "")
            c20_kana = c20_info.get("kana", "")
            
            normalized_c20_name = c20_name.replace(' ', '').replace('　', '').lower()
            normalized_c20_kana = c20_kana.replace(' ', '').replace('　', '').lower()

            # 完全一致を最優先
            if normalized_c20_name == normalized_input:
                candidate_matches.append({'code': c20_code, 'name': c20_name, 'score': 3})
                break # 最良のマッチなので即座に終了
            
            # 部分一致 (予報区名が入力を含む)
            if normalized_input in normalized_c20_name:
                candidate_matches.append({'code': c20_code, 'name': c20_name, 'score': 2})
            # 部分一致 (かなが入力を含む)
            elif normalized_input in normalized_c20_kana:
                candidate_matches.append({'code': c20_code, 'name': c20_name, 'score': 1})

        # スコアに基づいて最適なマッチを選択 (スコアが高いもの、同じスコアならリストの先頭=JMAの並び順を優先)
        if candidate_matches:
            best_candidate = max(candidate_matches, key=lambda x: x['score'])
            found_area_code = best_candidate['code']
            found_area_name = best_candidate['name']
            print(f"'{city_name_input}' に対して最適なJMA予報区: '{found_area_name}' ({found_area_code}) を見つけました。")
        
        # ユーザー入力の地名に直接一致する予報区が見つからなかった場合、
        # そのオフィス配下の最初の予報区 (class20s) を使用する (都道府県レベルの対応)
        if not found_area_code and related_class20s_codes:
            # 最初の予報区コードを使用 (多くの場合、県庁所在地などその県の代表的な予報区)
            found_area_code = related_class20s_codes[0]
            found_area_name = JMA_AREA_DATA["class20s"].get(found_area_code, {}).get("name", "不明な地域")
            print(f"警告: '{city_name_input}' の具体的なclass20s予報区が見つかりませんでした。最初の予報区 '{found_area_name}' ({found_area_code}) を使用します。")

        if not found_area_code:
            print(f"エラー: '{prefecture_jp}' のオフィス '{office_code}' に適切なJMA予報区 (class20s) が見つかりませんでした。")
            return None
        
        return {"office_code": office_code, "area_code": found_area_code, "area_name": found_area_name}

    except requests.exceptions.RequestException as e:
        print(f"APIリクエストエラー: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSONデコードエラー: {e}")
        return None
    except Exception as e:
        print(f"JMAエリア情報取得エラー: {e}")
        return None

def get_jma_forecast_message_dict(office_code, area_code, area_name):
    """【気象庁データ版】指定されたコードの天気予報を取得する関数"""
    api_url = f"https://www.jma.go.jp/bosai/forecast/data/forecast/{office_code}.json"
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()
        
        time_series = data[0]["timeSeries"]
        
        # 天気
        weather_area = next(area for area in time_series[0]["areas"] if area["area"]["code"] == area_code)
        today_weather = weather_area["weathers"][0].replace("　", " ")

        # 降水確率
        pops_area = next((area for area in time_series[1]["areas"] if area["area"]["code"] == area_code), time_series[1]["areas"][0])
        pops = [p for p in pops_area["pops"] if p != "--"]
        pop_today = max(map(int, pops[:2])) if len(pops) >= 2 and all(p.isdigit() for p in pops[:2]) else (pops[0] if pops and pops[0].isdigit() else "---")

        # 最高・最低気温
        temp_area = next(area for area in time_series[2]["areas"] if area["area"]["code"] == area_code)
        temp_max = temp_area["temps"][0]
        temp_min = temp_area["temps"][1]
        
        flex_message = {
            "type": "flex", "altText": f"{area_name}の天気予報 (気象庁)",
            "contents": { "type": "bubble", "direction": 'ltr',
                "header": {"type": "box", "layout": "vertical", "contents": [
                    {"type": "text", "text": "今日の天気予報 (気象庁)", "weight": "bold", "size": "xl", "color": "#FFFFFF", "align": "center"}
                ], "backgroundColor": "#27A5F9", "paddingTop": "12px", "paddingBottom": "12px", "cornerRadius": "md"},
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
        print(f"JMA天気予報APIエラー: {e}")
        return {"type": "text", "text": "気象庁からの天気情報取得に失敗しました。"}

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
        user_id, city_name, lat, lon = user
        print(f"登録地「{city_name}」({user_id})の天気予報を送信中...")
        
        # 登録されている地名で気象庁エリア情報を取得
        area_info = get_jma_area_info(city_name)
        if area_info:
            forecast_message = get_jma_forecast_message_dict(area_info["office_code"], area_info["area_code"], area_info["area_name"])
            push_to_line(user_id, [forecast_message])
        else:
            print(f"「{city_name}」のエリア情報が見つからなかったため、送信をスキップします。")
            push_to_line(user_id, [{"type": "text", "text": f"ご登録の地点「{city_name}」の気象庁情報が見つからず、本日の通知をスキップしました。お手数ですが、メニューから地点を再登録してください。"}])
            
    print("デイリー通知の送信が完了しました。")

if __name__ == "__main__":
    # 環境変数が設定されているか確認
    if not all([CHANNEL_ACCESS_TOKEN, OPENWEATHER_API_KEY]):
        print("エラー: .envファイルに必要なキーが設定されていません。")
    else:
        send_daily_forecasts()
