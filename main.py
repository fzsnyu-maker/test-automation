import os
import requests
import json
import re
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

# --- 設定エリア ---
GAS_URL = os.environ.get("GAS_URL")

def get_target_urls():
    # GASから店舗URLリストを取得
    res = requests.get(f"{GAS_URL}?action=get_urls")
    return res.json()

def scrape_store(page, store_url, mode):
    # 出勤情報ページURLを生成
    list_url = store_url.rstrip('/') + "/girl_list/"
    page.goto(list_url)
    
    results = []
    girls = page.query_selector_all(".girl_list_box") # 店舗ページ構成に依存

    for girl in girls:
        # 基本情報取得
        name = girl.query_selector(".name").inner_text()
        girl_url = girl.query_selector("a").get_attribute("href")
        girl_id = re.search(r"girlid-(\d+)", girl_url).group(1)
        
        # 予約状況（通常巡回）
        status_text = girl.query_selector(".status").inner_text() # 「受付終了」など
        
        deep_data = {}
        if mode == "deep":
            # 深層スキャン：プロフィールへ移動
            page.goto(girl_url)
            # 動画撮影/AV判定ロジック
            body_text = page.inner_text("body")
            deep_data['av'] = "◯" if re.search(r"(AV女優|セクシー女優|AV出演)", body_text) else ""
            deep_data['video'] = "◯" if re.search(r"(動画撮影|ビデオ撮影|撮影可)", body_text) else ""
            
            # 口コミ数
            review_link = girl_url + "reviews/"
            page.goto(review_link)
            review_text = page.inner_text(".review_count") # 例: "27件"
            deep_data['reviews'] = re.sub(r"\D", "", review_text)
            
            # 1週間シフト
            shift_data = page.query_selector(".schedule_box").inner_text()
            deep_data['shift'] = shift_data

        results.append({
            "id": girl_id,
            "name": name,
            "status": status_text,
            "deep": deep_data
        })
    return results

def run():
    urls = get_target_urls()
    # モード判定（GitHub Actionsの引数などで切り替え）
    mode = os.environ.get("SCAN_MODE", "normal") 
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        
        for url in urls:
            data = scrape_store(page, url, mode)
            # GASへ送信
            requests.post(GAS_URL, data={
                "action": "sync_data",
                "mode": mode,
                "url": url,
                "data": json.dumps(data)
            })
        browser.close()

if __name__ == "__main__":
    run()
