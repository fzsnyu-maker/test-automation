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
    except Exception as e:
        print(f"Failed to fetch URLs: {e}")
        return

    if not urls:
        print("No URLs found. Stopping.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # より人間に近いブラウザ偽装
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        page = context.new_page()
        
        for url in urls:
            try:
                # 対策1: 直接「出勤情報」のページを狙う（トップページだとiframe等で隠されるため）
                target_url = url.rstrip('/') + "/attend/"
                print(f"Scraping Target: {target_url}")
                
                # 対策2: タイムアウトを長めに設定
                page.goto(target_url, wait_until="networkidle", timeout=60000)
                
                # 対策3: ページを一番下までスクロールして「後読み込み」を強制起動させる
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(5000) 

                girls_data = []
                processed_ids = set()

                # 対策4: シティヘブンの「予約表（table）」や「キャストBOX」を広範囲にスキャン
                # aタグのhref属性を全て取得
                elements = page.query_selector_all("a[href*='girlid-']")
                
                for el in elements:
                    href = el.get_attribute("href")
                    match = re.search(r"girlid-(\d+)", href)
                    if not match: continue
                    
                    girl_id = match.group(1)
                    if girl_id in processed_ids: continue
                    processed_ids.add(girl_id)

                    # 近くにある名前とステータスを探す
                    # aタグ自体のテキストか、その親のテキストを判定
                    parent = el.evaluate_handle("el => { \
                        let p = el.closest('tr, li, div[class*=\"cast\"], div[class*=\"girl\"]'); \
                        return p ? p : el.parentElement; \
                    }").as_element()

                    if parent:
                        full_text = parent.inner_text().replace('\n', ' ')
                        name = el.inner_text().strip()
                        if not name or len(name) > 10: # 名前が長すぎる場合は別の場所を探す
                             name_el = parent.query_selector(".name, dt, b")
                             name = name_el.inner_text().strip() if name_el else name

                        status = "不明"
                        if any(x in full_text for x in ["案内終了", "受付終了", "本日終了"]):
                            status = "案内終了"
                        elif any(x in full_text for x in ["予約満了", "満員", "完売"]):
                            status = "予約満了"
                        elif any(x in full_text for x in ["×", "TEL", "接客中"]):
                            status = "接客中"
                        elif any(x in full_text for x in ["○", "待機", "即案内"]):
                            status = "待機中"
                        else:
                            status = "出勤中"

                        girls_data.append({"id": girl_id, "name": name, "status": status})

                # 最終手段：それでも0件ならiframeの中を覗く
                if not girls_data:
                    print("Checking iframes...")
                    for frame in page.frames:
                        f_elements = frame.query_selector_all("a[href*='girlid-']")
                        for fel in f_elements:
                            f_href = fel.get_attribute("href")
                            f_match = re.search(r"girlid-(\d+)", f_href)
                            if f_match:
                                girls_data.append({"id": f_match.group(1), "name": fel.inner_text().strip(), "status": "iframe検知"})

                print(f"Sending {len(girls_data)} girls to GAS...")
                requests.post(GAS_URL, data={
                    "action": "sync_data",
                    "mode": mode,
                    "store_url": url,
                    "json_data": json.dumps(girls_data, ensure_ascii=False)
                })

            except Exception as e:
                print(f"Error: {e}")
                
        browser.close()

if __name__ == "__main__":
    run()
