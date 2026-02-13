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
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1", # スマホ版に偽装
            locale="ja-JP"
        )
        page = context.new_page()
        
        for url in urls:
            try:
                # 対策：店舗トップではなく、必ず存在する「出勤スケジュールページ」を狙う
                # ここはPC版よりも構造が単純で、データが抜きやすい
                base_url = url.rstrip('/')
                target_url = f"{base_url}/attend/"
                print(f"Targeting Attendance Page: {target_url}")
                
                page.goto(target_url, wait_until="load", timeout=60000)
                page.wait_for_timeout(7000) # 読み込みをしっかり待つ

                girls_data = []
                
                # 手法：HTML全体から girlid を含む全てのブロック（trやdiv）を抽出
                # シティヘブンの attend ページは table 構造が多いため、それを中心に解析
                rows = page.query_selector_all("tr, .cast_box, .girl_list_box")
                print(f"Found {len(rows)} potential rows.")

                for row in rows:
                    link = row.query_selector("a[href*='girlid-']")
                    if not link:
                        continue
                    
                    href = link.get_attribute("href")
                    girl_id = re.search(r"girlid-(\d+)", href).group(1)
                    
                    # すでに同じIDを取得済みならスキップ
                    if any(g['id'] == girl_id for g in girls_data):
                        continue

                    name = link.inner_text().strip()
                    # 名前が空の場合や「詳細」などの場合は、隣の要素を探す
                    if not name or len(name) < 2:
                        name_el = row.query_selector(".name, b, strong")
                        name = name_el.inner_text().strip() if name_el else "不明"

                    # ステータス判定（行全体のテキストから判断）
                    row_text = row.inner_text().replace('\n', '')
                    status = "不明"
                    if "終了" in row_text or "受付不可" in row_text:
                        status = "案内終了"
                    elif "満了" in row_text or "満員" in row_text:
                        status = "予約満了"
                    elif "×" in row_text or "TEL" in row_text or "接客" in row_text:
                        status = "接客中"
                    elif "○" in row_text or "待機" in row_text or "即" in row_text or "空き" in row_text:
                        status = "待機中"
                    else:
                        status = "出勤中"

                    girls_data.append({
                        "id": girl_id,
                        "name": name,
                        "status": status
                    })

                # --- 最終手段：もし0件なら、スマホ版URLへ切り替えて再トライ ---
                if not girls_data:
                    print("No girls found. Trying Mobile URL...")
                    sp_url = base_url.replace("www.", "m.") + "/attend/"
                    page.goto(sp_url, wait_until="networkidle")
                    page.wait_for_timeout(5000)
                    # 同様のロジックで再スキャン（省略するが、page.content()からの正規表現抜き出し等）
                    content = page.content()
                    sp_ids = re.findall(r"girlid-(\d+)", content)
                    for sid in set(sp_ids):
                        girls_data.append({"id": sid, "name": "SP検知", "status": "確認中"})

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
