import os
import requests # requestsを直接使うのでインポートを確認
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    RichMenuRequest, RichMenuArea, RichMenuBounds, PostbackAction
)
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

# 環境変数からチャネルアクセストークンを取得
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")

# LINE Bot APIの初期化（リッチメニューの骨組み作成とデフォルト設定にのみ使用）
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
line_bot_api = MessagingApi(api_client)

# リッチメニュー用の画像ファイル名
RICH_MENU_IMAGE_PATH = "rich_menu_image.png"

def create_rich_menu():
    print("リッチメニューを作成します...")
    
    # 1. リッチメニューの構造（骨組み）を定義
    rich_menu_to_create = RichMenuRequest(
        size={'width': 2500, 'height': 843},
        selected=False,
        name="final-direct-upload-menu", # 新しい名前で作成
        chat_bar_text="メニュー",
        areas=[
            RichMenuArea(
                bounds=RichMenuBounds(x=0, y=0, width=2500, height=843),
                action=PostbackAction(label="change_location", data="action=change_location")
            )
        ]
    )
    
    try:
        # 2. リッチメニューの骨組みを作成し、IDを取得
        rich_menu_id_response = line_bot_api.create_rich_menu(rich_menu_request=rich_menu_to_create)
        rich_menu_id = rich_menu_id_response.rich_menu_id
        print(f"リッチメニューの骨組みを作成しました。ID: {rich_menu_id}")

        # 3. 【最終修正】requestsライブラリを直接使って画像をアップロード
        print("画像をアップロードします... (requestsを直接使用)")
        
        # LINEの仕様書に定められた、画像アップロード用のURL
        upload_url = f"https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content"
        
        # リクエストに必要なヘッダー情報
        headers = {
            "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "image/png"
        }
        
        # 画像ファイルをバイナリモードで開く
        with open(RICH_MENU_IMAGE_PATH, 'rb') as f:
            # requests.postを使って、LINEのサーバーに直接画像データを送信する
            response = requests.post(upload_url, headers=headers, data=f)

        # 通信が成功したかチェック
        if response.status_code == 200:
            print("画像をアップロードしました。")
        else:
            # もし失敗したら、サーバーからの応答を表示して原因を特定
            print("エラー: 画像のアップロードに失敗しました。")
            print(f"ステータスコード: {response.status_code}")
            print(f"応答内容: {response.text}")
            return # エラーがあったらここで処理を中断

        # 4. 全てのユーザーにこのリッチメニューをデフォルトとして設定
        line_bot_api.set_default_rich_menu(rich_menu_id)
        print("デフォルトリッチメニューとして設定しました。")
        print("\n★★★ リッチメニューの作成と設定が、全て完了しました！ ★★★")

    except Exception as e:
        print(f"エラーが発生しました: {e}")

if __name__ == "__main__":
    if not CHANNEL_ACCESS_TOKEN:
        print("エラー: .envファイルにLINE_CHANNEL_ACCESS_TOKENが設定されていません。")
    elif not os.path.exists(RICH_MENU_IMAGE_PATH):
        print(f"エラー: 画像ファイル '{RICH_MENU_IMAGE_PATH}' が見つかりません。")
    else:
        create_rich_menu()
