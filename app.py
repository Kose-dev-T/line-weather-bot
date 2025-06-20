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

# --- 初期設定 ---
load_dotenv()
app = Flask(__name__)
with app.app_context():
    database.init_db()

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.environ.get("LINE_SECRET") # 環境変数のキーがLINE_SECRETである可能性も考慮
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")

handler = WebhookHandler(CHANNEL_SECRET)

# --- グローバル変数（気象庁エリアコードのキャッシュ用） ---
JMA_AREA_DATA = None

# --- 補助関数群 ---
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
        
        # 予報データから本日分の天気、降水確率、最高/最低気温を抽出
        time_series = data[0]["timeSeries"]
        
        # 天気
        weather_area = next(area for area in time_series[0]["areas"] if area["area"]["code"] == area_code)
        today_weather = weather_area["weathers"][0].replace("　", " ") # 全角スペースを半角に置換

        # 降水確率
        # 降水確率は通常、予報区全体のデータが使われるが、念のためarea_codeでフィルター
        pops_area = next((area for area in time_series[1]["areas"] if area["area"]["code"] == area_code), time_series[1]["areas"][0])
        pops = [p for p in pops_area["pops"] if p != "--"] # "--"はデータがない場合
        # 本日午前の降水確率と午後の降水確率のうち、高い方を採用
        pop_today = max(map(int, pops[:2])) if len(pops) >= 2 and all(p.isdigit() for p in pops[:2]) else (pops[0] if pops and pops[0].isdigit() else "---")

        # 最高・最低気温
        temp_area = next(area for area in time_series[2]["areas"] if area["area"]["code"] == area_code)
        temp_max = temp_area["temps"][0]
        temp_min = temp_area["temps"][1]
        
        # Flex Messageの構造を定義
        flex_message = {
            "type": "flex", "altText": f"{area_name}の天気予報 (気象庁)",
            "contents": { "type": "bubble", "direction": 'ltr',
                "header": {"type": "box", "layout": "vertical", "contents": [
                    {"type": "text", "text": "今日の天気予報 (気象庁)", "weight": "bold", "size": "xl", "color": "#FFFFFF", "align": "center"}
                ], "backgroundColor": "#27A5F9", "paddingTop": "12px", "paddingBottom": "12px", "cornerRadius": "md"}, # 角を丸く
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

def reply_to_line(reply_token, messages):
    """LINE Messaging APIを通じてユーザーに返信する関数"""
    headers = {"Content-Type": "application/json; charset=UTF-8", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
    body = {"replyToken": reply_token, "messages": messages}
    try:
        response = requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, data=json.dumps(body, ensure_ascii=False).encode('utf-8'))
        response.raise_for_status() # HTTPエラーがあれば例外を発生させる
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
        abort(400) # 不正なリクエストとして400エラーを返す
    return 'OK'

@handler.add(FollowEvent)
def handle_follow(event):
    """友達追加イベントのハンドラー"""
    user_id = event.source.user_id
    database.set_user_state(user_id, 'waiting_for_location')
    reply_messages = [{"type": "text", "text": "友達追加ありがとうございます！\n毎日の天気予報を通知するために、まずはお住まいの地名（例: 大阪市、横浜市）を教えてください。"}]
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
        area_info = get_jma_area_info(user_message) # ユーザー入力の地名を渡す
        if area_info:
            # 緯度経度情報はOpenWeatherMapから取得するが、今回はJMAのエリア情報が取れれば十分なので0,0を仮置き
            database.set_user_location(user_id, user_message, 0, 0) 
            messages_to_send.append({"type": "text", "text": f"地点を「{area_info['area_name']}」に設定しました。\n明日から登録地点の天気予報をお届けします！\n（入力された地名に最も近い予報区です）"})
            # 地点設定後、状態をクリアまたはデフォルト状態に戻す
            database.set_user_state(user_id, 'normal') 
        else:
            messages_to_send.append({"type": "text", "text": f"「{user_message}」のエリア情報が見つかりませんでした。日本の市町村名などで入力してください。\n例：東京都、大阪市、横浜市、名古屋市、福岡市、札幌市、那覇市"})
    else:
        # 通常メッセージとして受け取り、即座に天気予報を返す
        area_info = get_jma_area_info(user_message) # ユーザー入力の地名を渡す
        if area_info:
            forecast_message = get_jma_forecast_message_dict(area_info["office_code"], area_info["area_code"], area_info["area_name"])
            messages_to_send.append(forecast_message)
        else:
            messages_to_send.append({"type": "text", "text": f"「{user_message}」の気象庁エリア情報が見つかりませんでした。日本の市町村名などで入力してください。\n例：東京都、大阪市、横浜市、名古屋市、福岡市、札幌市、那覇市"})
            
    if messages_to_send:
        reply_to_line(event.reply_token, messages_to_send)

if __name__ == "__main__":
    app.run(port=5000)
