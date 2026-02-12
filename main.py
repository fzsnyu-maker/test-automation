import asyncio
import os
import requests
from playwright.async_api import async_playwright

async def run_scraper():
    gas_url = os.environ.get("GAS_URL")
    if not gas_url: return

    # 1. GASから巡回対象のURLリストを取得
    try:
        res = requests.get(gas_url, params={"action": "get_urls"})
        target_urls = res.json()
    except Exception as e:
        print(f"URL取得失敗: {e}")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0...")
        
        for url in target_urls:
            # 予約ページURLを生成
            res_url = url if "A6ShopReservation" in url else url.rstrip('/') + "/A6ShopReservation/"
            print(f"調査中: {res_url}")
            
            page = await context.new_page()
            try:
                await page.goto(res_url, wait_until="networkidle", timeout=60000)
                # .girl_name クラスが出るまで待機
                await page.wait_for_selector(".girl_name", timeout=15000)
                names = await page.eval_on_selector_all(".girl_name", "els => els.map(el => el.innerText)")
                
                if names:
                    # GASに送信
                    requests.get(gas_url, params={"names": ",".join(names), "url": url})
                    print(f"送信完了: {len(names)}名")
            except Exception as e:
                print(f"スキップ({url}): {e}")
            await page.close()
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_scraper())
