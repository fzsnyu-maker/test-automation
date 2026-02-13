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
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            viewport={'width': 375, 'height': 812}
        )
        page = context.new_page()

        # 通信を監視してデータを横取りする関数
        captured_data = []

        def handle_response(response):
            # APIっぽい通信や、出勤データが含まれてそうなURLを監視
            if "get_cast" in response.url or "attend" in response.url or "api" in response.url:
                try:
                    # JSON形式のデータが流れてきたら解析
                    if "application/json" in response.headers.get("content-type", ""):
                        data = response.json()
                        print(f"Captured API Response from: {response.url}")
                        # ここでデータの形に合わせて抽出（シティヘブンのJSON構造に対応）
                        # ※構造は動的なので、後で汎用的に処理
                except:
                    pass

        page.on("response", handle_response)

        for url in urls:
            try:
                # 確実にデータが出る「スケジュールページ」をスマホモードで開く
                target_url = url.rstrip('/') + "/attend/?pcmode=sp"
                print(f"Intercepting Data at: {target_url}")
                
                page.goto(target_url, wait_until="networkidle", timeout=60000)
                
                # スクロールして「次のデータ」を読み込ませる
                for _ in range(5):
                    page.mouse.wheel(0, 1000)
                    page.wait_for_timeout(1000)

                # --- 最終手段：画面上の「全てのHTML」からIDと名前のペアを強引に抽出 ---
                # 正規表現をさらに強化
                content = page.content()
                girls_data = []
                
                # シティヘブン特有のキャストブロックを抽出するパターン
                # girlid-XXXXX と、その直後にある名前らしき文字列をペアで探す
                matches = re.findall(r'girlid-(\d+)[^>]*>([^<]+)', content)
                
                processed_ids = set()
                for gid, name in matches:
                    name = name.strip()
                    if gid not in processed_ids and len(name) > 0 and "詳細" not in name:
                        processed_ids.add(gid)
                        
                        # ステータスを周辺テキストから判定
                        # IDの周辺200文字を切り取って判定
                        pos = content.find(f"girlid-{gid}")
                        surrounding = content[pos:pos+500]
                        
                        status = "出勤中"
                        if any(x in surrounding for x in ["案内終了", "受付終了", "完売"]): status = "案内終了"
                        elif any(x in surrounding for x in ["予約満了", "満員"]): status = "予約満了"
                        elif any(x in surrounding for x in ["×", "TEL", "接客"]): status = "接客中"
                        elif any(x in surrounding for x in ["○", "即", "待機"]): status = "待機中"
                        
                        girls_data.append({"id": gid, "name": name, "status": status})

                print(f"Final Count: {len(girls_data)} girls found.")
                
                # GASへ送信
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
