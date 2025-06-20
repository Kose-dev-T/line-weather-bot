import os
import requests
import json
from datetime import datetime
from dotenv import load_dotenv
import database
import sys
import re

# --- 初期設定 ---
load_dotenv()
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")

# 環境変数がすべて設定されているか確認
if not all([CHANNEL_ACCESS_TOKEN, OPENWEATHER_API_KEY]):
    missing_vars = []
    if not CHANNEL_ACCESS_TOKEN:
        missing_vars.append("LINE_CHANNEL_ACCESS_TOKEN")
    if not OPENWEATHER_API_KEY:
        missing_vars.append("OPENWEATHER_API_KEY")
    
    error_message = f"エラー: .envファイルまたは環境変数に以下のキーが設定されていません: {', '.join(missing_vars)}"
    print(error_message, file=sys.stderr)
    sys.exit(1)

# --- グローバル変数 ---
JMA_AREA_DATA = None

# 特定の市区町村から都道府県を推測するためのマップ (OpenWeatherMapのstateが空の場合の補完用)
PREFECTURE_GUESS_MAP = {
    "札幌": "北海道", "旭川": "北海道", "函館": "北海道",
    "青森": "青森県", "盛岡": "岩手県", "仙台": "宮城県", "秋田": "秋田県", "山形": "山形県", "福島県": "福島県",
    "水戸": "茨城県", "宇都宮": "栃木県", "前橋": "群馬県", "さいたま": "埼玉県", "千葉": "千葉県", "東京": "東京都", 
    "新宿": "東京都", "千代田": "東京都", "中央": "東京都", "港": "東京都", "渋谷": "東京都", "大田": "東京都", 
    "横浜": "神奈川県", "川崎": "神奈川県", "相模原": "神奈川県",
    "新潟": "新潟県", "富山": "富山県", "金沢": "石川県", "福井": "福井県", "山梨県": "山梨県", "長野県": "長野県", "岐阜県": "岐阜県",
    "静岡": "静岡県", "浜松": "静岡県", "名古屋": "愛知県", "津": "三重県",
    "大津": "滋賀県", "近江八幡": "滋賀県", "彦根": "滋賀県", "草津": "滋賀県",
    "京都": "京都府", "大阪": "大阪府", "堺": "大阪府", "東大阪": "大阪府",
    "神戸": "兵庫県", "姫路": "兵庫県", "西宮": "兵庫県",
    "奈良": "奈良県", "和歌山県": "和歌山県",
    "鳥取": "鳥取県", "松江": "島根県", "岡山県": "岡山県", "広島県": "広島県", "福山": "広島県", "山口県": "山口県",
    "徳島": "徳島県", "高松": "香川県", "松山": "愛媛県", "高知": "高知県",
    "福岡": "福岡県", "北九州": "福岡県", "久留米": "福岡県",
    "佐賀": "佐賀県", "長崎": "長崎県", "熊本県": "熊本県", "大分県": "大分県", "宮崎県": "宮崎県", "鹿児島県": "鹿児島県",
    "那覇": "沖縄県", "沖縄": "沖縄県",
}


# --- 補助関数群 ---

def normalize_place_name(name):
    """
    地名から一般的な接尾辞を除去し、全角/半角スペースを削除して小文字に変換する。
    例: "大阪市" -> "大阪", "東京都" -> "東京", "札幌" -> "札幌"
    """
    if not isinstance(name, str):
        return ""
    
    normalized = name.replace(' ', '').replace('　', '')
    
    # より多くの接尾辞を考慮し、順序も調整
    suffixes = ['市', '区', '町', '村', '郡', '都', '道', '府', '県', '地方', '部']
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]
            return normalize_place_name(normalized) # 再帰的に呼び出し
    
    return normalized.lower()

def get_jma_area_info(city_name_input):
    """
    ユーザーが入力した地名から、対応する気象庁のエリアコードなどを特定する関数。
    OpenWeatherMapで緯度経度と都道府県を特定し、その情報をもとにJMAのエリアコードを検索する。
    市区町村レベルの地名に対応できるよう、class20s (予報区) の名称も考慮する。
    OpenWeatherMapが都道府県情報を返さない場合の補完ロジックを強化。
    """
    global JMA_AREA_DATA
    
    print(f"DEBUG: get_jma_area_info('{city_name_input}')を開始します。")

    geo_api_url = "http://api.openweathermap.org/geo/1.0/direct"
    geo_params = {"q": f"{city_name_input},JP", "limit": 1, "appid": OPENWEATHER_API_KEY}
    
    prefecture_jp = None
    try:
        geo_res = requests.get(geo_api_url, params=geo_params)
        geo_res.raise_for_status()
        geo_data = geo_res.json()
        
        if not geo_data:
            print(f"DEBUG: OpenWeatherMapで'{city_name_input}'の地理情報が見つかりませんでした。")
            # OpenWeatherMapで見つからない場合、都道府県マッピングで直接探す
            prefecture_jp = PREFECTURE_GUESS_MAP.get(normalize_place_name(city_name_input), None)
            if prefecture_jp:
                print(f"DEBUG: 地名直接マッピングで都道府県 '{prefecture_jp}' を推測しました。")
            else:
                print(f"DEBUG: 地名直接マッピングでも都道府県を特定できませんでした。")
                return None # OpenWeatherMapでも直接マッピングでも見つからなければ終了
        else:
            prefecture_en = geo_data[0].get("state", "")
            geo_city_name = geo_data[0].get("name", "")
            print(f"DEBUG: OpenWeatherMap結果: state='{prefecture_en}', name='{geo_city_name}'")

            # OpenWeatherMapが都道府県を返した場合
            if prefecture_en:
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
                    print(f"警告: OpenWeatherMapが返した英語都道府県名 '{prefecture_en}' を日本語にマッピングできませんでした。")
                    # マッピングできない場合、地名直接マッピングで試す
                    prefecture_jp = PREFECTURE_GUESS_MAP.get(normalize_place_name(city_name_input), None)
                    if prefecture_jp:
                        print(f"DEBUG: 地名直接マッピングで都道府県 '{prefecture_jp}' を推測しました。")
            else:
                # OpenWeatherMapが都道府県を返さなかった場合、OpenWeatherMapの都市名とユーザー入力の地名で都道府県を推測
                print(f"DEBUG: OpenWeatherMapが都道府県を返しませんでした。地名から推測を試みます。")
                
                # ユーザー入力地名から推測
                prefecture_jp = PREFECTURE_GUESS_MAP.get(normalize_place_name(city_name_input), None)
                if prefecture_jp:
                    print(f"DEBUG: ユーザー入力地名直接マッピングで都道府県 '{prefecture_jp}' を推測しました。")
                else:
                    # OpenWeatherMapが返した都市名から推測
                    prefecture_jp = PREFECTURE_GUESS_MAP.get(normalize_place_name(geo_city_name), None)
                    if prefecture_jp:
                        print(f"DEBUG: OpenWeatherMap都市名直接マッピングで都道府県 '{prefecture_jp}' を推測しました。")
                    else:
                        print(f"DEBUG: 地名から都道府県を推測できませんでした。")
                        return None # どちらもダメなら終了
        
        if not prefecture_jp:
            print(f"最終的に都道府県を特定できませんでした。")
            return None

        print(f"DEBUG: 特定された都道府県 (日本語): {prefecture_jp}")

        # 気象庁エリアデータをキャッシュ（初回のみ取得）
        if JMA_AREA_DATA is None:
            area_res = requests.get("https://www.jma.go.jp/bosai/common/const/area.json")
            area_res.raise_for_status()
            JMA_AREA_DATA = area_res.json()
            print("DEBUG: 気象庁エリアデータを取得・キャッシュしました。")

        jma_office_short_name_map = {
            "北海道": "札幌", "青森県": "青森", "岩手県": "盛岡", "宮城県": "仙台", "秋田県": "秋田", "山形県": "山形", "福島県": "福島",
            "茨城県": "水戸", "栃木県": "宇都宮", "群馬県": "前橋", "埼玉県": "熊谷", "千葉県": "千葉", "東京都": "東京", "神奈川県": "横浜",
            "新潟県": "新潟", "富山県": "富山", "石川県": "金沢", "福井県": "福井", "山梨県": "甲府", "長野県": "長野", "岐阜県": "岐阜",
            "静岡県": "静岡", "愛知県": "名古屋", "三重県": "津", "滋賀県": "彦根", "京都府": "京都", "大阪府": "大阪", "兵庫県": "神戸",
            "奈良県": "奈良", "和歌山県": "和歌山", "鳥取県": "鳥取", "島根県": "松江", "岡山県": "岡山", "広島県": "広島", "山口県": "山口",
            "徳島県": "徳島", "香川県": "高松", "愛媛県": "松山", "高知県": "高知", "福岡県": "福岡", "佐賀県": "佐賀", "長崎県": "長崎",
            "熊本県": "熊本", "大分県": "大分", "宮崎県": "宮崎県", "鹿児島県": "鹿児島県", "沖縄県": "沖縄県"
        }
        
        target_jma_office_name = jma_office_short_name_map.get(prefecture_jp, prefecture_jp.replace('県', '').replace('府', '').replace('都', '').replace('道', '')) 
        if prefecture_jp == "和歌山県": # 和歌山県は例外的に「和歌山」
            target_jma_office_name = "和歌山"
        
        office_code = None
        for code, info in JMA_AREA_DATA["offices"].items():
            if info["name"] == target_jma_office_name:
                office_code = code
                break
        
        if not office_code:
            print(f"エラー: 目標のJMAオフィス名 '{target_jma_office_name}' のオフィスコードが見つかりませんでした。")
            return None
        
        print(f"DEBUG: JMAオフィスコード: {office_code}")
        
        related_class20s_codes = JMA_AREA_DATA["offices"][office_code]["children"]
        
        found_area_code = None
        found_area_name = None

        normalized_input = normalize_place_name(city_name_input)
        
        best_match_score = -1
        best_match_area = None

        for c20_code in related_class20s_codes:
            c20_info = JMA_AREA_DATA["class20s"].get(c20_code, {})
            c20_name = c20_info.get("name", "")
            c20_kana = c20_info.get("kana", "")
            
            normalized_c20_name = normalize_place_name(c20_name)
            normalized_c20_kana = normalize_place_name(c20_kana)
            
            current_score = -1
            
            # 1. 完全一致
            if normalized_c20_name == normalized_input or normalized_c20_kana == normalized_input:
                current_score = 100 
                best_match_area = {'code': c20_code, 'name': c20_name}
                break 

            # 2. 部分一致 (ユーザー入力が予報区名・かなに含まれる)
            if normalized_input in normalized_c20_name:
                match_len = len(normalized_input)
                current_score = max(current_score, 50 + match_len)
            elif normalized_input in normalized_c20_kana:
                match_len = len(normalized_input)
                current_score = max(current_score, 30 + match_len)
            
            # 3. 部分一致 (予報区名・かながユーザー入力に含まれる)
            if normalized_c20_name in normalized_input:
                match_len = len(normalized_c20_name)
                current_score = max(current_score, 40 + match_len)
            elif normalized_c20_kana in normalized_input:
                match_len = len(normalized_c20_kana)
                current_score = max(current_score, 20 + match_len)
            
            if current_score > best_match_score:
                best_match_score = current_score
                best_match_area = {'code': c20_code, 'name': c20_name}

        if best_match_area:
            found_area_code = best_match_area['code']
            found_area_name = best_match_area['name']
            print(f"DEBUG: '{city_name_input}' に対して最適なJMA予報区: '{found_area_name}' ({found_area_code}, スコア: {best_match_score}) を見つけました。")
        
        if not found_area_code and related_class20s_codes:
            found_area_code = related_class20s_codes[0]
            found_area_name = JMA_AREA_DATA["class20s"].get(found_area_code, {}).get("name", "不明な地域")
            print(f"DEBUG: '{city_name_input}' の具体的なclass20s予報区が見つかりませんでした。最初の予報区 '{found_area_name}' ({found_area_code}) を使用します。")

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
        print(f"DEBUG: JMA天気予報API '{api_url}' からデータを取得中...")
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()
        print(f"DEBUG: JMA天気予報APIからデータ取得成功。データ構造の確認中...")
        
        # timeSeries データの存在確認
        if not data or len(data) == 0 or "timeSeries" not in data[0]:
            print("ERROR: JMAデータにtimeSeriesが存在しないか、データが空です。")
            return {"type": "text", "text": "気象庁からの天気情報取得に失敗しました。(データ構造エラー)"}
        
        time_series = data[0]["timeSeries"]
        
        weather_area = next((area for area in time_series[0]["areas"] if area["area"]["code"] == area_code), None)
        today_weather = "情報なし"
        if weather_area and "weathers" in weather_area and len(weather_area["weathers"]) > 0:
            today_weather = weather_area["weathers"][0].replace("　", " ").strip()
        print(f"DEBUG: 抽出された天気: {today_weather}")

        pops_area = next((area for area in time_series[1]["areas"] if area["area"]["code"] == area_code), time_series[1]["areas"][0] if len(time_series[1]["areas"]) > 0 else None)
        
        pop_today = "---"
        if pops_area and "pops" in pops_area:
            pops = [p.strip() for p in pops_area["pops"] if p != "--" and p.strip().isdigit()]
            if len(pops) >= 2:
                pop_today = str(max(map(int, pops[:2])))
            elif len(pops) == 1:
                pop_today = pops[0]
        print(f"DEBUG: 抽出された降水確率: {pop_today}%")

        temp_area = next((area for area in time_series[2]["areas"] if area["area"]["code"] == area_code), None)
        temp_max = "---"
        temp_min = "---"
        if temp_area and "temps" in temp_area:
            if len(temp_area["temps"]) > 0 and str(temp_area["temps"][0]).strip().replace('.', '').isdigit():
                temp_max = str(int(float(temp_area["temps"][0])))
            if len(temp_area["temps"]) > 1 and str(temp_area["temps"][1]).strip().replace('.', '').isdigit():
                temp_min = str(int(float(temp_area["temps"][1])))
        print(f"DEBUG: 抽出された最高気温: {temp_max}°C, 最低気温: {temp_min}°C")

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
        print("DEBUG: Flex MessageのJSONが正常に構築されました。")
        return flex_message
    except requests.exceptions.RequestException as e:
        print(f"ERROR: JMA天気予報APIへのリクエストエラー: {e}")
        return {"type": "text", "text": "気象庁からの天気情報取得に失敗しました。(APIリクエストエラー)"}
    except json.JSONDecodeError as e:
        print(f"ERROR: JMA天気予報APIの応答JSONデコードエラー: {e}")
        return {"type": "text", "text": "気象庁からの天気情報取得に失敗しました。(JSON形式エラー)"}
    except Exception as e:
        print(f"ERROR: JMA天気予報取得処理中の予期せぬエラー: {e}")
        return {"type": "text", "text": "気象庁からの天気情報取得に失敗しました。(処理エラー)"}

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
    database.init_db()
    users = database.get_all_users_with_location()
    
    if not users:
        print("通知対象のユーザーが見つかりませんでした。")
        return
    
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
        print("エラー: .envファイルに必要なキーが設定されていません。デイリー通知は実行されません。", file=sys.stderr)
    else:
        send_daily_forecasts()
