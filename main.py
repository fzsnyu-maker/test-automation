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
        print(f"Target URLs: {urls}")
    except Exception as e:
        print(f"Failed to fetch URLs: {e}")
        return

    with sync_playwright() as p:
        # ブラウザの起動オプションを強化
        browser = p.chromium.launch(headless=True)
        
        # 徹底的な「人間（日本人）」の偽装
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            viewport={'width': 1920, 'height': 1080}
        )
        
        page = context.new_page()
        
        for url in urls:
            try:
                print(f"Accessing: {url}")
                # タイムアウトを極限まで伸ばし、ネットワークが静かになるまで待つ
                page.goto(url, wait_until="load", timeout=90000)
                
                # シティヘブンの動的ロードを待つために、数回スクロール
                for _ in range(3):
                    page.mouse.wheel(0, 500)
                    page.wait_for_timeout(1000)
                
                # 少し長めに待機（重要）
                page.wait_for_timeout(5000)

                girls_data = []
                processed_ids = set()

                # 手法1: href属性の全スキャン（正規表現）
                # ページ全体のHTMLを取得して直接IDをぶっこ抜く
                content = page.content()
                all_girl_ids = re.findall(r"girlid-(\d+)", content)
                
                if all_girl_ids:
                    print(f"Found {len(set(all_girl_ids))} IDs by Regex Scan.")
                    
                    for gid in set(all_girl_ids):
                        # 各IDに対して、名前とステータスを特定しにいく
                        # ページ内のそのIDを持つaタグを探す
                        el = page.query_selector(f"a[href*='girlid-{gid}']")
                        if el:
                            # 親要素を取得
                            parent = el.evaluate_handle("el => el.closest('div, li, tr')").as_element()
                            name = "調査中"
                            status = "出勤中"
                            
                            if parent:
                                p_text = parent.inner_text().replace('\n', ' ')
                                # 名前の推測
                                name = el.inner_text().strip()
                                # ステータスの推測
                                if "終了" in p_text or "受付不可" in p_text: status = "案内終了"
                                elif "満了" in p_text or "満員" in p_text: status = "予約満了"
                                elif "×" in p_text or "TEL" in p_text: status = "接客中"
                                elif "○" in p_text or "即" in p_text: status = "待機中"
                            
                            girls_data.append({"id": gid, "name": name, "status": status})

                # 手法2: それでもダメなら「隠し要素」を全検索
                if not girls_data:
                    print("Attempting to find hidden data-attributes...")
                    elements = page.query_selector_all("[data-girl_id]")
                    for el in elements:
                        gid = el.get_attribute("data-girl_id")
                        if gid and gid not in processed_ids:
                            processed_ids.add(gid)
                            girls_data.append({"id": gid, "name": "データ検知", "status": "不明"})

                print(f"Sending {len(girls_data)} girls to GAS...")
                requests.post(GAS_URL, data={
                    "action": "sync_data",
                    "mode": mode,
                    "store_url": url,
                    "json_data": json.dumps(girls_data, ensure_ascii=False)
                })

            except Exception as e:
                print(f"Error during scraping: {e}")
                
        browser.close()

if __name__ == "__main__":
    run()
