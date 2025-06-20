# add_text_to_image.py

from PIL import Image, ImageDraw, ImageFont
import os

# --- 設定項目 ---

# 元になる画像ファイル名（文字なしの画像）
BASE_IMAGE_PATH = "rich_menu_image.png" 
# プロジェクトフォルダにコピーしたフォントファイル名
FONT_PATH = "NotoSansJP-Regular.ttf"
# 追加したいテキスト
TEXT_TO_ADD = "登録地点を変更する"
# 文字のサイズ
FONT_SIZE = 120
# 文字の色 (R, G, B)
TEXT_COLOR = (80, 80, 80)
# 新しく保存する画像ファイル名
OUTPUT_IMAGE_PATH = "rich_menu_with_text.png"

# --- ここから処理 ---

def add_text_to_image():
    # 1. ベース画像を開く
    try:
        img = Image.open(BASE_IMAGE_PATH)
        print(f"画像 '{BASE_IMAGE_PATH}' を開きました。")
    except FileNotFoundError:
        print(f"エラー: ベース画像 '{BASE_IMAGE_PATH}' が見つかりません。")
        print("文字なしの背景画像を、この名前でプロジェクトフォルダに保存してください。")
        return

    # 2. 描画オブジェクトとフォントオブジェクトを作成
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
        print(f"フォント '{FONT_PATH}' を読み込みました。")
    except IOError:
        print(f"エラー: フォントファイル '{FONT_PATH}' が見つかりません。")
        print("ステップ2を参考に、正しいフォントファイルをプロジェクトフォルダに置いてください。")
        return

    # 画像の中央下に配置する
    img_width, img_height = img.size
    # テキスト自体の幅と高さを取得
    text_bbox = draw.textbbox((0, 0), TEXT_TO_ADD, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    
    # 中央に配置するためのx, y座標を計算
    position_x = (img_width - text_width) / 2
    # y座標は、画像の中央より少し下あたりに設定
    position_y = (img_height / 2) + 150 
    
    position = (position_x, position_y)

    # 4. 画像にテキストを描画
    draw.text(position, TEXT_TO_ADD, font=font, fill=TEXT_COLOR)
    print(f"テキスト '{TEXT_TO_ADD}' を描画しました。")

    # 5. 新しい画像として保存
    img.save(OUTPUT_IMAGE_PATH)
    print(f"完成した画像を '{OUTPUT_IMAGE_PATH}'として保存しました。")

if __name__ == "__main__":
    add_text_to_image()