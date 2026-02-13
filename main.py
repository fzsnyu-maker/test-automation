import os
import requests
import json
import re
import time
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
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        for url in urls:
            try:
                # E+錦糸町は /girllist/ または /attend/ が有効
                # より情報が確実な /attend/ を優先的にチェック
                base_url = url.rstrip('/')
                target_url = f"{base_url}/attend/"
                print(f"Scraping Target: {target_url}")
                
                page.goto(target_url, wait_until="networkidle")
                
                # 動的コンテンツの読み込み待ち（超重要）
                page.wait_for_timeout(5000) 

                girls_data = []
                # シティヘブンの「出勤表」から女の子の情報を抜き出す
                # aタグのhrefに girlid- が含まれるものをすべて探す
                cast_links = page.query_selector_all("a[href*='girlid-']")
                
                processed_ids = set()

                for link in cast_links:
                    href = link.get_attribute("href")
                    match = re.search(r"girlid-(\d+)", href)
                    if not match: continue
                    
                    girl_id = match.group(1)
                    if girl_id in processed_ids: continue
                    processed_ids.add(girl_id)

                    # 名前とステータスを、リンクの周囲（親要素）から探す
                    # シティヘブンの出勤表は tr や li の中に情報が固まっている
                    parent = link.evaluate_handle("el => el.closest('tr, li, div.cast_box, div.girl_list_box')")
                    
                    if parent:
                        parent_el = parent.as_element()
                        # 名前の取得
                        name = link.inner_text().strip()
                        
                        # ステータスの取得（◯, ✕, 案内終了, TEL等）
                        # シティヘブンの予約表内のテキストや画像altをスキャン
                        status = ""
                        # 予約表のセルのテキストを取得
                        status_text = parent_el.inner_text()
                        
                        # ステータス判定ロジック
                        if "案内終了" in status_text or "受付終了" in status_text:
                            status = "案内終了"
                        elif "予約満了" in status_text or "満員" in status_text:
                            status = "予約満了"
                        elif "✕" in status_text or "TEL" in status_text:
                            status = "接客中/予約済"
                        elif "◯" in status_text or "即案内" in status_text or "空き" in status_text:
                            status = "待機中"
                        else:
                            # 記号が取れない場合、画像(alt)をチェック
                            img = parent_el.query_selector("img")
                            if img and img.get_attribute("alt"):
                                status = img.get_attribute("alt")

                        girls_data.append({
                            "id": girl_id,
                            "name": name,
                            "status": status if status else "出勤中"
                        })

                if not girls_data:
                    # attendでダメなら girllist を試す
                    print("No girls found in /attend/. Trying /girllist/...")
                    page.goto(f"{base_url}/girllist/", wait_until="networkidle")
                    page.wait_for_timeout(3000)
                    # (ここにも同様の抽出ロジックが入りますが、まずはattendでテスト)

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
