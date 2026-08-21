"""
sales.sif.tokyo からログCSVをダウンロードし、Google Driveの
ログ種別ごとのサブフォルダへアップロード、同一年月の旧ファイルを削除する。

実行前に .env を用意すること（.env.example を参照）。
このマシンから sales.sif.tokyo と Google Drive API の両方に到達できる必要がある。

対象ログ（サイト画面の「通常ログ」セクション内、ラベル文字列で行を特定）:
  - 課金ログ
  - コイン使用ログ(ガチャ)
新しい種類を追加したい場合は TARGET_LOGS に追記するだけでよい。
"""

import os
import sys
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

load_dotenv()

# ログ種別ラベル -> Drive上のサブフォルダ名（そのまま使う）
TARGET_LOGS = [
    "課金ログ",
    "コイン使用ログ(ガチャ)",
]

DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"


def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        sys.exit(f"環境変数 {name} が未設定です。.env を確認してください。")
    return value


def month_token(d: date) -> str:
    return d.strftime("%Y%m")


def default_date_range():
    today = date.today()
    first_of_month = today.replace(day=1)
    return first_of_month.isoformat(), today.isoformat()


def download_logs(download_dir: Path, date_from: str, date_to: str) -> dict:
    """サイトにログインし、対象ログCSVをダウンロードして {label: local_path} を返す"""
    site_url = env("SIF_SITE_URL", required=True)
    login_id = env("SIF_LOGIN_ID", required=True)
    login_password = env("SIF_LOGIN_PASSWORD", required=True)
    headless = env("HEADLESS", "true").lower() != "false"

    id_selector = env("SIF_LOGIN_ID_SELECTOR", 'input[name="login_id"]')
    pw_selector = env("SIF_LOGIN_PASSWORD_SELECTOR", 'input[type="password"]')
    submit_selector = env("SIF_LOGIN_SUBMIT_SELECTOR", 'button[type="submit"]')

    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        page.goto(site_url, wait_until="networkidle")

        # ログインフォームが出ていれば入力する。既にログイン済みセッションなら
        # このブロックはタイムアウトしてスキップされる。
        try:
            page.locator(pw_selector).first.wait_for(state="visible", timeout=5000)
            page.locator(id_selector).first.fill(login_id)
            page.locator(pw_selector).first.fill(login_password)
            page.locator(submit_selector).first.click()
            page.wait_for_load_state("networkidle")
        except PlaywrightTimeoutError:
            pass

        # ログCSVダウンロード画面に戻る（未ログインだった場合はログイン後にここへ遷移させる）
        if "ログCSV" not in page.content():
            page.goto(site_url, wait_until="networkidle")

        # 期間の入力（type=date のフィールドが2つ並んでいる想定）
        date_inputs = page.locator('input[type="date"]')
        if date_inputs.count() >= 2:
            date_inputs.nth(0).fill(date_from)
            date_inputs.nth(1).fill(date_to)

        for label in TARGET_LOGS:
            row = page.locator(
                f"xpath=//*[contains(normalize-space(string(.)), '{label}')]"
                "/ancestor-or-self::*[self::tr or self::div][1]"
            ).last
            csv_button = row.locator("button, a").filter(has_text="CSV").first
            csv_button.wait_for(state="visible", timeout=15000)

            with page.expect_download() as download_info:
                csv_button.click()
            download = download_info.value

            dest = download_dir / f"{label}_{month_token(date.today())}.csv"
            download.save_as(str(dest))
            results[label] = dest
            print(f"[download] {label} -> {dest}")

        browser.close()

    return results


def drive_service():
    key_file = env("GDRIVE_SERVICE_ACCOUNT_FILE", required=True)
    creds = service_account.Credentials.from_service_account_file(
        key_file, scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)


def get_or_create_subfolder(service, parent_id: str, name: str) -> str:
    query = (
        f"'{parent_id}' in parents and name = '{name}' "
        f"and mimeType = '{DRIVE_FOLDER_MIME}' and trashed = false"
    )
    found = service.files().list(q=query, fields="files(id, name)").execute()
    files = found.get("files", [])
    if files:
        return files[0]["id"]

    metadata = {"name": name, "mimeType": DRIVE_FOLDER_MIME, "parents": [parent_id]}
    created = service.files().create(body=metadata, fields="id").execute()
    return created["id"]


def delete_same_month_files(service, folder_id: str, token: str):
    query = f"'{folder_id}' in parents and trashed = false"
    found = service.files().list(q=query, fields="files(id, name)").execute()
    for f in found.get("files", []):
        if token in f["name"]:
            service.files().delete(fileId=f["id"]).execute()
            print(f"[drive] 削除: {f['name']}")


def upload_to_drive(local_path: Path, label: str, token: str):
    service = drive_service()
    parent_id = env("GDRIVE_PARENT_FOLDER_ID", required=True)
    subfolder_id = get_or_create_subfolder(service, parent_id, label)

    delete_same_month_files(service, subfolder_id, token)

    media = MediaFileUpload(str(local_path), mimetype="text/csv", resumable=True)
    metadata = {"name": local_path.name, "parents": [subfolder_id]}
    service.files().create(body=metadata, media_body=media, fields="id").execute()
    print(f"[drive] アップロード: {label}/{local_path.name}")


def main():
    download_dir = Path(env("DOWNLOAD_DIR", "./downloads")).resolve()
    download_dir.mkdir(parents=True, exist_ok=True)

    date_from = env("SIF_DATE_FROM") or None
    date_to = env("SIF_DATE_TO") or None
    if not date_from or not date_to:
        date_from, date_to = default_date_range()

    token = month_token(date.today())

    downloaded = download_logs(download_dir, date_from, date_to)
    for label, path in downloaded.items():
        upload_to_drive(path, label, token)

    print(f"完了: {datetime.now().isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
