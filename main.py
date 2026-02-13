import os
import requests
import json
import re
from playwright.sync_api import sync_playwright

GAS_URL = os.environ.get("GAS_URL")

def run():
    mode = os.environ.get("SCAN_MODE", "normal")
    
    # 1. GASからURLを取得
    print(f"Connecting to GAS: {GAS_URL}")
    try:
        res = requests.get(f"{GAS_URL}?action=get_urls")
        urls = res.json()
        print(f"Fetched URLs: {urls}") # ここで取得したURLがログに出ます
    except Exception as e:
        print(f"Failed to fetch URLs from GAS: {e}")
        return

    if not urls:
        print("No URLs found in the '設定' sheet (Column Q). Stopping.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")
        page = context.new_page()
        
        for url in urls:
            try:
                print(f"Scraping Store: {url}")
                # 巡回処理
                list_url = url.rstrip('/') + "/girl_list/"
                page.goto(list_url, wait_until="domcontentloaded")
                
                girls_data = []
                # シティヘブンの女の子リストの要素を特定（クラス名は調整が必要な場合があります）
                # 今回はより汎用的なセレクタに変更
                girl_elements = page.query_selector_all("[class*='girl_list_box']")
                
                for el in girl_elements:
                    name = el.query_selector("[class*='name']").inner_text() if el.query_selector("[class*='name']") else "Unknown"
                    status = el.query_selector("[class*='status']").inner_text() if el.query_selector("[class*='status']") else ""
                    girl_link = el.query_selector("a").get_attribute("href") if el.query_selector("a") else ""
                    girl_id = re.search(r"girlid-(\d+)", girl_link).group(1) if girl_link else "0"
                    
                    girls_data.append({
                        "id": girl_id,
                        "name": name,
                        "status": status.replace('\n', ' ')
                    })
                
                # GASへ送信
                print(f"Sending {len(girls_data)} girls to GAS...")
                post_res = requests.post(GAS_URL, data={
                    "action": "sync_data",
                    "mode": mode,
                    "store_url": url,
                    "json_data": json.dumps(girls_data, ensure_ascii=False)
                })
                print(f"GAS Response: {post_res.text}")

            except Exception as e:
                print(f"Error scraping {url}: {e}")
                
        browser.close()

if __name__ == "__main__":
    run()
