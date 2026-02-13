import os
import requests
import json
import re
from playwright.sync_api import sync_playwright

GAS_URL = os.environ.get("GAS_URL")

def run():
    mode = os.environ.get("SCAN_MODE", "normal")
    
    print(f"Connecting to GAS: {GAS_URL}")
    try:
        res = requests.get(f"{GAS_URL}?action=get_urls")
        urls = res.json()
        print(f"Fetched URLs: {urls}")
    except Exception as e:
        print(f"Failed to fetch URLs: {e}")
        return

    if not urls:
        print("No URLs found. Stopping.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # 人間に見せかけるための設定
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        for url in urls:
            try:
                print(f"Scraping Store: {url}")
                # 出勤リストページへ移動
                list_url = url.rstrip('/') + "/girl_list/"
                page.goto(list_url, wait_until="networkidle")
                
                # 女の子のカードを特定（hrefにgirlidを含むリンクを持つ親要素を探す）
                girls_data = []
                # シティヘブン特有の「girl_list_box」や「cast_box」に対応
                # aタグのhrefに 'girlid-' が含まれるものをベースにループ
                girl_links = page.query_selector_all("a[href*='girlid-']")
                
                # 重複を避けるためにIDを保持
                processed_ids = set()

                for link in girl_links:
                    href = link.get_attribute("href")
                    match = re.search(r"girlid-(\d+)", href)
                    if not match: continue
                    
                    girl_id = match.group(1)
                    if girl_id in processed_ids: continue
                    processed_ids.add(girl_id)

                    # リンクの近くにある名前やステータスを探す
                    # リンクの親要素（カード全体）を取得
                    parent = link.evaluate_handle("el => el.closest('div, li')")
                    
                    if parent:
                        # 名前を取得（.nameクラス、またはリンク内のテキスト）
                        name_el = parent.as_element().query_selector("[class*='name']")
                        name = name_el.inner_text().strip() if name_el else link.inner_text().strip()
                        
                        # ステータスを取得（.statusクラス、または特定のワードを含む要素）
                        status = ""
                        status_el = parent.as_element().query_selector("[class*='status'], [class*='state']")
                        if status_el:
                            status = status_el.inner_text().strip()
                        
                        # ステータスが空の場合、予約ボタンなどのテキストから推測
                        if not status:
                            btn = parent.as_element().query_selector("[class*='btn']")
                            if btn: status = btn.inner_text().strip()

                        girls_data.append({
                            "id": girl_id,
                            "name": name,
                            "status": status.replace('\n', ' ')
                        })

                if not girls_data:
                    # 予備のセレクタ（別のデザインパターンの店舗用）
                    print("No girls found with primary selector. Trying backup...")
                    # ここで必要に応じて別のセレクタを試行
                
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
