# LINE Weather Assistant: A Cloud-Native Forecast Bot
![Status](https://img.shields.io/badge/status-live_on_render-blue)

## 1. 概要 (Overview)

毎朝の外出前に天気を確認し忘れることが多く、「個人に最適化された情報が、意識せずとも能動的に届けられる仕組みがあれば」という自身の日常的な課題意識から、このプロジェクトはスタートしました。

単なるリマインダーではなく、LINEという対話型インターフェースを介したオンデマンドな情報取得機能と、スケジュール実行されるプロアクティブなプッシュ通知機能を組み合わせた、パーソナライズド情報提供システムとして設計・実装。

最終的に、複数の外部API連携、PostgreSQLによるデータ永続化、そしてRender上でのCI/CDパイプラインを通じた本番環境へのデプロイまで、Webアプリケーション開発における一連のプロセスを完遂しました。

## 2. 主な機能 (Key Features)

* **オンデマンドな情報取得 (On-Demand Data Retrieval)**
    * LINEのWebhookをトリガーに、ユーザーからのテキストメッセージ（地名）をリアルタイムで処理。OpenWeatherMap APIを介して気象データを取得し、整形されたFlex Messageとして非同期に応答します。

* **プロアクティブな情報配信 (Proactive Information Delivery)**
    * RenderのCron Job機能を利用し、毎日定時（0:00 UTC）にバッチ処理を実行。PostgreSQLデータベースに永続化された全ユーザーの登録地点情報を参照し、個別のユーザーに対してパーソナライズされた天気予報をプッシュ通知します。

* **永続的なUI/UX (Persistent UI/UX)**
    * LINEのリッチメニュー機能を活用し、ユーザーがいつでも設定変更を行えるUIを常設。Postbackイベントを通じてユーザーの状態を「地点登録待機中」に遷移させ、対話の文脈に応じた応答を可能にしています。

## 3. システム構成 (System Architecture)

```
[ ユーザー on LINE ] <--(対話)--> [ LINE Platform ] <--(Webhook)--> [ Render Web Service (app.py) ]
       ^                                                                            |
       | (プッシュ通知)                                                            | (DB Read/Write via SQLAlchemy)
       |                                                                            V
[ Render Cron Job (daily_notifier.py) ] ---(DB Read)----> [ Render PostgreSQL DB ] <----+
       |
       | (天気予報を問い合わせ)
       V
[ OpenWeatherMap API ]
```

## 4. 技術スタック (Technology Stack)

* **バックエンド**: Python 3.11, Flask, Gunicorn
* **データベース**: PostgreSQL
* **主要ライブラリ**: `line-bot-sdk-python`, `requests`, `SQLAlchemy`, `psycopg2-binary`, `python-dotenv`
* **インフラストラクチャ**: Render.com (Web Service & Cron Job), Git/GitHub
* **外部API**: LINE Messaging API, OpenWeatherMap API

## 5. 技術的ハイライトと実装から得た知見

### フルスタックなサービス構築経験
ユーザーインターフェース（LINEの対話、Flex Message, Rich Menu）から、Webサーバー（Flask）、データベース（PostgreSQL）、外部API連携、そして本番環境のインフラ（Render）まで、アプリケーションを構成する全ての技術レイヤーを一人で設計・実装しました。これにより、サービス全体のデータフローとコンポーネント間の連携を俯瞰的に設計・管理する能力を習得しました。

### クラウド環境における依存関係の解決能力
ローカル環境（Windows）とクラウド環境（Linux）の差異に起因する、非常に複雑なライブラリの依存関係・ビルドエラーに直面。その際、エラーログを精読し、原因を体系的に切り分けることで根本原因を特定。代替案を自ら調査・実装し、最終的に問題を解決に導きました。これにより、計画通りに進まない状況でも、目的を達成するための最適な解決策を見つけ出す、実践的な問題解決能力を養いました。

### ステートフルなアプリケーションの設計
各ユーザーの状態（通常問い合わせ時、地点登録待機時など）をデータベースで管理することにより、単なるリクエスト/レスポンスモデルを超えた、文脈に応じた対話を実現しました。これにより、ユーザーIDに紐づく状態（ステート）を永続化し、より高度なインタラクションを提供するステートフルなアプリケーションの設計・実装経験を得ました。