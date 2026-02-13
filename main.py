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

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # コンテキスト設定でiPhoneを完全にシミュレート
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            viewport={'width': 375, 'height': 812},
            locale="ja-JP"
        )
        page = context.new_page()
        
        for url in urls:
            try:
                # 対策1: URLに ?pcmode=sp を付与してスマホ版を強制
                base_url = url.split('?')[0].rstrip('/')
                target_url = f"{base_url}/attend/?pcmode=sp"
                print(f"Targeting SP Mode: {target_url}")
                
                page.goto(target_url, wait_until="load", timeout=60000)
                
                # 対策2: スマホ版はスクロールでデータが読み込まれることが多いため、少しずつ下げる
                for i in range(5):
                    page.mouse.wheel(0, 800)
                    page.wait_for_timeout(1000)

                girls_data = []
                processed_ids = set()

                # 対策3: スマホ版のHTML構造（aタグのgirlid）を全スキャン
                # スマホ版はリスト形式なので、aタグを起点にするのが最も確実
                links = page.query_selector_all("a[href*='girlid-']")
                print(f"Found {len(links)} candidate links.")

                for link in links:
                    href = link.get_attribute("href")
                    match = re.search(r"girlid-(\d+)", href)
                    if not match: continue
                    
                    girl_id = match.group(1)
                    if girl_id in processed_ids: continue
                    processed_ids.add(girl_id)

                    # 近くの親要素（divやli）を取得して、その中のテキストを解析
                    parent = link.evaluate_handle("el => el.closest('div, li, section')").as_element()
                    
                    if parent:
                        parent_text = parent.inner_text().replace('\n', ' ')
                        # 名前の取得（aタグ内、または特定のクラス）
                        name = link.inner_text().strip()
                        if not name or len(name) > 15: # 変なテキストを拾った場合の予備
                            name_el = parent.query_selector("[class*='name']")
                            name = name_el.inner_text().strip() if name_el else "不明"

                        # ステータス判定
                        status = "不明"
                        if any(x in parent_text for x in ["終了", "受付不可", "本日完売"]):
                            status = "案内終了"
                        elif any(x in parent_text for x in ["予約満了", "満員", "完売"]):
                            status = "予約満了"
                        elif any(x in parent_text for x in ["×", "TEL", "接客中"]):
                            status = "接客中"
                        elif any(x in parent_text for x in ["○", "待機", "即案内", "空き"]):
                            status = "待機中"
                        else:
                            status = "出勤中"

                        girls_data.append({"id": girl_id, "name": name, "status": status})

                # 万が一0件だった場合のバックアップ（ページ全体のHTMLからIDだけ抜く）
                if not girls_data:
                    print("Backup: Regex Scan for SP content...")
                    content = page.content()
                    ids = set(re.findall(r"girlid-(\d+)", content))
                    for gid in ids:
                        girls_data.append({"id": gid, "name": "SP検知", "status": "確認中"})

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
