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
import sys
import re

# --- 初期設定 ---
load_dotenv()
app = Flask(__name__)
with app.app_context():
    database.init_db()

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET") or os.environ.get("LINE_SECRET")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")

# 環境変数がすべて設定されているか確認
if not all([CHANNEL_ACCESS_TOKEN, CHANNEL_SECRET, OPENWEATHER_API_KEY]):
    missing_vars = []
    if not CHANNEL_ACCESS_TOKEN:
        missing_vars.append("LINE_CHANNEL_ACCESS_TOKEN")
    if not CHANNEL_SECRET:
        missing_vars.append("LINE_CHANNEL_SECRET (または LINE_SECRET)")
    if not OPENWEATHER_API_KEY:
        missing_vars.append("OPENWEATHER_API_KEY")
    
    error_message = f"エラー: 以下の環境変数が設定されていません。Renderの環境変数設定を確認してください: {', '.join(missing_vars)}"
    print(error_message, file=sys.stderr)
    sys.exit(1)

handler = WebhookHandler(CHANNEL_SECRET)

# --- グローバル変数（気象庁エリアコードのキャッシュ用） ---
JMA_AREA_DATA = None

# 特定の市区町村から都道府県を推測するためのマップ (OpenWeatherMapのstateが空の場合の補完用)
# キーはnormalize_place_name()で処理された後の形に合わせる（接尾辞除去・小文字の日本語）
PREFECTURE_GUESS_MAP = {
    # 北海道
    "札幌": "北海道", "旭川": "北海道", "函館": "北海道",
    # 東北
    "青森": "青森県", "盛岡": "岩手県", "仙台": "宮城県", "秋田": "秋田県", "山形": "山形県", "福島": "福島県",
    # 関東
    "水戸": "茨城県", "宇都宮": "栃木県", "前橋": "群馬県", "さいたま": "埼玉県", "千葉": "千葉県", "東京": "東京都", 
    "新宿": "東京都", "千代田": "東京都", "中央": "東京都", "港": "東京都", "渋谷": "東京都", "大田": "東京都", 
    "横浜": "神奈川県", "川崎": "神奈川県", "相模原": "神奈川県",
    # 中部
    "新潟": "新潟県", "富山": "富山県", "金沢": "石川県", "福井": "福井県", "甲府": "山梨県", "長野": "長野県", "岐阜": "岐阜県",
    "静岡": "静岡県", "浜松": "静岡県", "名古屋": "愛知県", "津": "三重県",
    # 関西
    "大津": "滋賀県", "近江八幡": "滋賀県", "彦根": "滋賀県", "草津": "滋賀県", 
    "京都": "京都府", "大阪": "大阪府", "堺": "大阪府", "東大阪": "大阪府",
    "神戸": "兵庫県", "姫路": "兵庫県", "西宮": "兵庫県",
    "奈良": "奈良県", "和歌山": "和歌山県",
    # 中国
    "鳥取": "鳥取県", "松江": "島根県", "岡山": "岡山県", "広島": "広島県", "福山": "広島県", "山口": "山口県",
    # 四国
    "徳島": "徳島県", "高松": "香川県", "松山": "愛媛県", "高知": "高知県",
    # 九州・沖縄
    "福岡": "福岡県", "北九州": "福岡県", "久留米": "福岡県",
    "佐賀": "佐賀県", "長崎": "長崎県", "熊本": "熊本県", "大分": "大分県", "宮崎": "宮崎県", "鹿児島": "鹿児島県",
    "那覇": "沖縄県", "沖縄": "沖縄県", 
}

# --- 補助関数群 ---

def normalize_place_name(name):
    """
    地名から一般的な接尾辞を除去し、全角/半角スペースを削除して小文字に変換する。
    例: "大阪市" -> "大阪", "東京都" -> "東京", "札幌" -> "札幌"
    漢字、ひらがな、カタカナの地名に対応し、ローマ字への変換は行わない。
    """
    if not isinstance(name, str):
        return ""
    
    normalized = name.replace(' ', '').replace('　', '')
    
    suffixes = ['市', '区', '町', '村', '郡', '都', '道', '府', '県', '地方', '部']
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]
            return normalize_place_name(normalized) # 再帰的に呼び出し
    
    return normalized.lower() # 日本語のまま小文字化

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
            prefecture_jp = PREFECTURE_GUESS_MAP.get(normalize_place_name(city_name_input), None)
            if prefecture_jp:
                print(f"DEBUG: 地名直接マッピングで都道府県 '{prefecture_jp}' を推測しました。")
            else:
                print(f"DEBUG: 地名直接マッピングでも都道府県を特定できませんでした。")
                return None 
        else:
            prefecture_en = geo_data[0].get("state", "")
            geo_city_name = geo_data[0].get("name", "")
            print(f"DEBUG: OpenWeatherMap結果: state='{prefecture_en}', name='{geo_city_name}'")

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
                    prefecture_jp = PREFECTURE_GUESS_MAP.get(normalize_place_name(city_name_input), None)
                    if prefecture_jp:
                        print(f"DEBUG: 地名直接マッピングで都道府県 '{prefecture_jp}' を推測しました。")
            else:
                print(f"DEBUG: OpenWeatherMapが都道府県を返しませんでした。地名から推測を試みます。")
                prefecture_jp = PREFECTURE_GUESS_MAP.get(normalize_place_name(city_name_input), None)
                if prefecture_jp:
                    print(f"DEBUG: ユーザー入力地名直接マッピングで都道府県 '{prefecture_jp}' を推測しました。")
                else:
                    prefecture_jp = PREFECTURE_GUESS_MAP.get(normalize_place_name(geo_city_name), None)
                    if prefecture_jp:
                        print(f"DEBUG: OpenWeatherMap都市名直接マッピングで都道府県 '{prefecture_jp}' を推測しました。")
                    else:
                        print(f"DEBUG: 地名から都道府県を推測できませんでした。")
                        return None 
        
        if not prefecture_jp:
            print(f"最終的に都道府県を特定できませんでした。")
            return None

        print(f"DEBUG: 特定された都道府県 (日本語): {prefecture_jp}")

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
            "熊本県": "熊本", "大分県": "大分", "宮崎県": "宮崎県", "鹿児島県": "鹿児島県", "沖縄県": "那覇"
        }
        
        # 目標となるJMAオフィス名（彦根など）
        target_jma_office_name = jma_office_short_name_map.get(prefecture_jp, normalize_place_name(prefecture_jp)) 
        if prefecture_jp == "和歌山県": 
            target_jma_office_name = "和歌山"
        
        office_code = None
        # オフィスコードを検索する際の正規化されたターゲット名
        normalized_target_jma_office_name = normalize_place_name(target_jma_office_name)
        # 都道府県名も正規化しておく（例えば「滋賀県」->「滋賀」）
        normalized_prefecture_jp = normalize_place_name(prefecture_jp)

        # DEBUG: JMA_AREA_DATA["offices"]の最初の数件を出力して内容を確認
        print("DEBUG: JMA Offices Data Sample:")
        for i, (code, info) in enumerate(JMA_AREA_DATA["offices"].items()):
            if i >= 5: break # 最初の5件だけ表示
            print(f"  Code: {code}, Name: '{info.get('name', 'N/A')}'")


        for code, info in JMA_AREA_DATA["offices"].items():
            office_actual_name = info.get("name", "")
            normalized_office_actual_name = normalize_place_name(office_actual_name)
            
            print(f"DEBUG: Comparing JMA office name '{office_actual_name}' (Normalized: '{normalized_office_actual_name}') with target '{target_jma_office_name}' (Normalized: '{normalized_target_jma_office_name}') and normalized prefecture '{normalized_prefecture_jp}'")
            
            # 優先度1: 短縮名（彦根）での完全一致
            if normalized_office_actual_name == normalized_target_jma_office_name:
                office_code = code
                print(f"DEBUG: Found office code '{office_code}' by direct office name match: '{office_actual_name}'")
                break
            # 優先度2: 都道府県名（滋賀）での完全一致 (JMAのオフィス名が都道府県名の場合)
            elif normalized_office_actual_name == normalized_prefecture_jp:
                office_code = code
                print(f"DEBUG: Found office code '{office_code}' by prefecture name match: '{office_actual_name}'")
                break
            
        if not office_code:
            print(f"エラー: 目標のJMAオフィス名 '{target_jma_office_name}'（正規化後: '{normalized_target_jma_office_name}'）または都道府県名 '{prefecture_jp}'（正規化後: '{normalized_prefecture_jp}'）に対応するオフィスコードが見つかりませんでした。")
            return None
        
        print(f"DEBUG: JMAオフィスコード: {office_code}")
        
        related_class20s_codes = JMA_AREA_DATA["offices"][office_code]["children"]
        
        found_area_code = None
        found_area_name = None

        normalized_input = normalize_place_name(city_name_input)
        print(f"DEBUG: 正規化されたユーザー入力: '{normalized_input}'")
        
        best_match_score = -1
        best_match_area = None

        for c20_code in related_class20s_codes:
            c20_info = JMA_AREA_DATA["class20s"].get(c20_code, {})
            c20_name = c20_info.get("name", "")
            c20_kana = c20_info.get("kana", "")
            
            normalized_c20_name = normalize_place_name(c20_name)
            normalized_c20_kana = normalize_place_name(c20_kana)
            print(f"DEBUG:   予報区 '{c20_name}' (正規化: '{normalized_c20_name}', かな正規化: '{normalized_c20_kana}')")
            
            current_score = -1
            
            # 1. 完全一致
            if normalized_c20_name == normalized_input or normalized_c20_kana == normalized_input:
                current_score = 100 
                best_match_area = {'code': c20_code, 'name': c20_name}
                print(f"DEBUG:     完全一致！スコア: {current_score}")
                break 

            # 2. 部分一致 (ユーザー入力が予報区名・かなに含まれる)
            if normalized_input in normalized_c20_name:
                match_len = len(normalized_input)
                current_score = max(current_score, 50 + match_len)
                print(f"DEBUG:     予報区名に部分一致。現在のスコア: {current_score}")
            elif normalized_input in normalized_c20_kana:
                match_len = len(normalized_input)
                current_score = max(current_score, 30 + match_len)
                print(f"DEBUG:     かなに部分一致。現在のスコア: {current_score}")
            
            # 3. 部分一致 (予報区名・かながユーザー入力に含まれる)
            if normalized_c20_name in normalized_input:
                match_len = len(normalized_c20_name)
                current_score = max(current_score, 40 + match_len)
                print(f"DEBUG:     入力に予報区名が部分一致。現在のスコア: {current_score}")
            elif normalized_c20_kana in normalized_input:
                match_len = len(normalized_c20_kana)
                current_score = max(current_score, 20 + match_len)
                print(f"DEBUG:     入力にかなが部分一致。現在のスコア: {current_score}")
            
            if current_score > best_match_score:
                best_match_score = current_score
                best_match_area = {'code': c20_code, 'name': c20_name}
                print(f"DEBUG:     新しい最良候補を発見。スコア: {best_match_score}")

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

def reply_to_line(reply_token, messages):
    """LINE Messaging APIを通じてユーザーに返信する関数"""
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
    """LINEからのWebhookを受け取るエンドポイント"""
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("署名検証に失敗しました。")
        abort(400)
    return 'OK'

@handler.add(FollowEvent)
def handle_follow(event):
    """友達追加イベントのハンドラー"""
    user_id = event.source.user_id
    database.set_user_state(user_id, 'waiting_for_location')
    reply_messages = [{"type": "text", "text": "友達追加ありがとうございます！\n毎日の天気予報を通知するために、まずはお住まいの地名（例: 大阪市、横浜市、千代田区）を教えてください。"}]
    reply_to_line(event.reply_token, reply_messages)

@handler.add(PostbackEvent)
def handle_postback(event):
    """ポストバックイベントのハンドラー（例：地点変更ボタン）"""
    user_id = event.source.user_id
    if event.postback.data == 'action=change_location':
        database.set_user_state(user_id, 'waiting_for_location')
        reply_messages = [{"type": "text", "text": "新しい通知先の地名を教えてください。（例: 横浜市、千代田区）"}]
        reply_to_line(event.reply_token, reply_messages)

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    """メッセージイベントのハンドラー"""
    user_id = event.source.user_id
    user_message = event.message.text
    user_state = database.get_user_state(user_id)
    messages_to_send = []
    
    if user_state == 'waiting_for_location':
        area_info = get_jma_area_info(user_message)
        if area_info:
            database.set_user_location(user_id, user_message, 0, 0) 
            messages_to_send.append({"type": "text", "text": f"地点を「{area_info['area_name']}」に設定しました。\n明日から登録地点の天気予報をお届けします！\n（入力された地名に最も近い予報区です）"})
            database.set_user_state(user_id, 'normal') 
        else:
            messages_to_send.append({"type": "text", "text": f"「{user_message}」のエリア情報が見つかりませんでした。日本の市町村名などで入力してください。\n例：東京都、大阪市、横浜市、名古屋市、福岡市、札幌市、那覇市、または千代田区"})
    else:
        area_info = get_jma_area_info(user_message)
        if area_info:
            forecast_message = get_jma_forecast_message_dict(area_info["office_code"], area_info["area_code"], area_info["area_name"])
            messages_to_send.append(forecast_message)
        else:
            messages_to_send.append({"type": "text", "text": f"「{user_message}」の気象庁エリア情報が見つかりませんでした。日本の市町村名などで入力してください。\n例：東京都、大阪市、横浜市、名古屋市、福岡市、札幌市、那覇市、または千代田区"})
            
    if messages_to_send:
        reply_to_line(event.reply_token, messages_to_send)

if __name__ == "__main__":
    app.run(port=5000)
