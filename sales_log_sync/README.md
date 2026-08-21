# sales.sif.tokyo ログ自動同期

`sales.sif.tokyo`（Android日本 / site_code=sao_android_jp_release）から
「課金ログ」「コイン使用ログ(ガチャ)」CSVをダウンロードし、Google Driveの
ログ種別ごとのサブフォルダにアップロードした上で、同一年月の旧ファイルを
削除するスクリプトです。**ローカルPC（sales.sif.tokyo に到達できる環境）で
実行してください。**このリポジトリの認証情報（`.env` / サービスアカウントJSON）は
絶対にコミットしないでください（`.gitignore` 済み）。

## セットアップ

1. Python 3.10 以上をインストール
2. 依存関係をインストール
   ```
   cd sales_log_sync
   pip install -r requirements.txt
   playwright install chromium
   ```
3. Google Cloud で Drive API を有効にしたサービスアカウントを作成し、JSON鍵を
   ダウンロード（例: `service_account.json` としてこのフォルダに配置。**コミット禁止**）
4. アップロード先の Google Drive フォルダ（親フォルダ）を、サービスアカウントの
   メールアドレスに「編集者」権限で共有する
5. `.env.example` を `.env` にコピーし、以下を埋める
   - `SIF_LOGIN_ID` / `SIF_LOGIN_PASSWORD`: 配布されたログイン情報
   - `GDRIVE_PARENT_FOLDER_ID`: 共有した親フォルダのID（URLの `folders/` の後ろの部分）
   - `GDRIVE_SERVICE_ACCOUNT_FILE`: JSON鍵ファイルへのパス

## 実行

```
python download_and_sync.py
```

デフォルトでは「当月1日〜今日」の期間でダウンロードします。期間を固定したい
場合は `.env` の `SIF_DATE_FROM` / `SIF_DATE_TO` に `YYYY-MM-DD` で指定してください。

Drive上の構成:
```
<GDRIVE_PARENT_FOLDER_ID>/
  課金ログ/
    課金ログ_202608.csv
  コイン使用ログ(ガチャ)/
    コイン使用ログ(ガチャ)_202608.csv
```
同じ年月（ファイル名に年月が含まれるもの）は実行のたびに削除→再アップロードされ、
常に最新1件だけが残ります。過去の年月のファイルは残ります。

## 定期実行したい場合

- Linux/Mac (cron 例、毎朝9時):
  ```
  0 9 * * * cd /path/to/sales_log_sync && /usr/bin/python3 download_and_sync.py >> sync.log 2>&1
  ```
- Windows: タスクスケジューラで `python download_and_sync.py` を登録

## 動作しない場合（セレクタ調整）

このスクリプトはスクリーンショットのみを元に作成しており、実際のサイトの
HTML構造（ログインフォームの input 名など）を確認できていません。うまく
動かない場合は次を試してください。

- `.env` の `HEADLESS=false` にしてブラウザ画面を目視しながら実行し、
  ログインフォームやCSVボタンで止まっている箇所を確認
- ログインフォームの入力欄名が異なる場合は `.env` の
  `SIF_LOGIN_ID_SELECTOR` / `SIF_LOGIN_PASSWORD_SELECTOR` /
  `SIF_LOGIN_SUBMIT_SELECTOR` を実際のCSSセレクタに合わせて調整
- ログ行の特定がうまくいかない場合は `download_and_sync.py` の
  `TARGET_LOGS` 周辺のXPathを実際のDOM構造に合わせて調整

## セキュリティ上の注意

ダウンロードされるCSVにはユーザーの個人ID・課金情報が含まれます。
`downloads/` ディレクトリ、`.env`、サービスアカウントJSONはすべて
`.gitignore` 済みですが、扱いには十分注意してください。
