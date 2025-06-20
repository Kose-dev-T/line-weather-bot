# LINE Weather Assistant (対話型・天気予報LINEボット)
![Status](https://img.shields.io/badge/status-complete-brightgreen)

## 概要

自身の「プログラミング学習中に、集中を妨げずに英単語を調べたい」という課題を解決するために開発した、LINE上で動作するパーソナルアシスタントです。

当初はシンプルな翻訳ツールとして構想しましたが、技術学習を深める中で、より実用的で多くの人が日常的に使える「天気予報」をテーマに発展させました。ユーザーとの対話機能、パーソナライズされた自動通知機能、そしてクラウドへのデプロイまで、Webアプリケーション開発の一連のプロセスを一人で完遂したプロジェクトです。

## 主な機能

-   ✅ **オンデマンド天気予報**: トーク画面で地名を送信すると、その場所の当日予報（天気・最高/最低気温・降水確率）を、見やすいカード形式（Flex Message）で即座に返信します。
-   ✅ **パーソナライズされたプッシュ通知**: ユーザーは通知を受け取りたい「マイ地点」を一つ登録できます。登録すると、毎日深夜0時にその地点の天気予報が自動でLINEに届きます。
-   ✅ **優れたUI/UX**: トーク画面下部に「地点変更」ボタンを常設（リッチメニュー）。ユーザーが直感的に操作でき、いつでも簡単かつ確実に通知先を変更できます。
-   ✅ **状態管理**: ユーザーが地点登録中か、通常の問い合わせ中かをボットが判断し、文脈に合わせた自然な対話を実現しています。

## システム構成図

```
[ ユーザー on LINE ] <--(対話)--> [ LINE Platform ] <--(Webhook)--> [ Render Web Service (app.py) ]
       ^                                                                           |
       | (プッシュ通知)                                                            | (DB Read/Write)
       |                                                                           V
[ Render Cron Job (daily_notifier.py) ] --(DB Read)--> [ Render PostgreSQL DB ] <--+
       |
       | (天気予報を問い合わせ)
       V
[ OpenWeatherMap API ]
```

## 使用技術

* **バックエンド**: Python, Flask, Gunicorn
* **データベース**: PostgreSQL (SQLAlchemy, psycopg2-binary)
* **フロントエンド**: LINE Messaging API (Flex Message, Rich Menu)
* **外部API**: OpenWeatherMap API
* **インフラ・DevOps**: Render (Web Service, Cron Job), Git/GitHub, ngrok

## ローカルでの動作方法

```bash
# 1. リポジトリをクローン
git clone [https://github.com/Kose-dev-T/line-weather-bot.git](https://github.com/Kose-dev-T/line-weather-bot.git)
cd line-weather-bot

# 2. 仮想環境の作成と有効化
python -m venv venv
source venv/bin/activate  # Macの場合。Windowsは venv\Scripts\activate

# 3. 必要なライブラリをインストール
pip install -r requirements.txt

# 4. .envファイルを作成し、各種キーを記述
# OPENWEATHER_API_KEY="..."
# LINE_CHANNEL_ACCESS_TOKEN="..."
# LINE_CHANNEL_SECRET="..."
# DATABASE_URL="postgres://..."

# 5. リッチメニューをLINEに登録（一度だけ実行）
python create_rich_menu.py

# 6. Webサーバーを起動
python app.py
```

## このプロジェクトから得られた学びと経験

このプロジェクトを通じて、単にコードを書くだけでなく、サービスをゼロから構築し、安定稼働させるまでの一連のプロセスを深く経験しました。

1.  **フルスタック開発の経験**
    ユーザーインターフェース（LINEの対話やリッチメニュー）から、Webサーバー（Flask）、データベース（PostgreSQL）、外部API連携、インフラ（Render）まで、アプリケーションを構成する全てのレイヤーを一人で設計・実装しました。これにより、サービス全体の構造を俯瞰して考える力が身につきました。

2.  **粘り強いデバッグと問題解決能力**
    開発中に、ローカル環境（Windows）とクラウド環境（Linux）の差異に起因する、非常に複雑なライブラリの依存関係・バージョン問題に直面しました。その際、エラーログを精読し、原因を体系的に切り分けることで根本原因を特定。代替案を自ら調査・実装し、最終的に問題を解決に導きました。この経験から、計画通りに進まない状況でも、目的を達成するための最適な解決策を見つけ出す、実践的な問題解決能力を養いました。

3.  **クラウドネイティブな開発スキル**
    `requirements.txt`による依存関係の管理、`gunicorn`による本番サーバーの運用、環境変数による機密情報の管理など、ローカルで動かすだけでなく、クラウド上で安定稼働させるためのモダンな開発手法を実践しました。