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
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        for url in urls:
            try:
                # 店舗トップページから情報を探す（ヘブンはトップに出勤状況が埋め込まれていることが多い）
                print(f"Scraping Store: {url}")
                page.goto(url, wait_until="networkidle")
                page.wait_for_timeout(5000) # JSの読み込みを待つ

                girls_data = []
                processed_ids = set()

                # ロジック1: href属性に girlid- が含まれる全てのリンクを起点にする
                links = page.query_selector_all("a[href*='girlid-']")
                
                for link in links:
                    href = link.get_attribute("href")
                    match = re.search(r"girlid-(\d+)", href)
                    if not match: continue
                    
                    girl_id = match.group(1)
                    if girl_id in processed_ids: continue
                    processed_ids.add(girl_id)

                    # リンクの親要素をたどって、その周りのテキストを全部拾う
                    # これにより、名前やステータスをクラス名に関わらず取得する
                    parent = link.evaluate_handle("el => { \
                        let p = el.closest('div[class*=\"box\"], li, tr, div[class*=\"cast\"]'); \
                        return p ? p : el.parentElement; \
                    }").as_element()

                    if parent:
                        parent_text = parent.inner_text().replace('\n', ' ')
                        # 名前の抽出（リンクのテキストそのもの、または特定の強いワードを避ける）
                        name = link.inner_text().strip()
                        if not name:
                             name_el = parent.query_selector("span, b, p")
                             name = name_el.inner_text().strip() if name_el else "不明"
                        
                        # ステータス判定（親要素内のテキストから判断）
                        status = "不明"
                        if any(x in parent_text for x in ["案内終了", "受付終了", "本日終了"]):
                            status = "案内終了"
                        elif any(x in parent_text for x in ["予約満了", "満員", "完売"]):
                            status = "予約満了"
                        elif any(x in parent_text for x in ["接客中", "予約中", "×", "TEL"]):
                            status = "接客中/予約済"
                        elif any(x in parent_text for x in ["待機中", "即案内", "○", "空き"]):
                            status = "待機中"
                        else:
                            # アイコン画像があるかチェック
                            img = parent.query_selector("img")
                            status = img.get_attribute("alt") if img and img.get_attribute("alt") else "出勤中"

                        girls_data.append({
                            "id": girl_id,
                            "name": name,
                            "status": status
                        })

                # デバッグ用：取得できなかった場合にページ全体から girlid- を探す（最終手段）
                if not girls_data:
                    print("Secondary search by Regex on page content...")
                    content = page.content()
                    matches = re.findall(r"girlid-(\d+)", content)
                    for gid in set(matches):
                        girls_data.append({"id": gid, "name": "検知のみ", "status": "不明"})

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
