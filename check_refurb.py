#!/usr/bin/env python3
"""監控 Apple 台灣整修品頁面，MacBook 新上架時發送 Telegram 通知。

只用 Python 標準函式庫，無需安裝任何套件。
狀態存在 state.json（sku -> 商品資訊），由 GitHub Actions 提交回 repo。
"""
import json
import os
import re
import sys
import urllib.request
import urllib.parse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PAGE_URL = "https://www.apple.com/tw/shop/refurbished/mac"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
KEYWORD = "MacBook"  # 只通知名稱含此關鍵字的商品
TELEGRAM_MSG_LIMIT = 4096


def fetch_products():
    """抓取頁面並解析 ld+json 結構化資料，回傳 {sku: {name, price, url}}。"""
    req = urllib.request.Request(PAGE_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        html = resp.read().decode("utf-8")

    blocks = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S
    )
    products = {}
    for block in blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if data.get("@type") != "Product" or KEYWORD not in data.get("name", ""):
            continue
        offer = (data.get("offers") or [{}])[0]
        sku = offer.get("sku")
        if not sku:
            continue
        products[sku] = {
            "name": data["name"],
            "price": int(offer.get("price") or 0),
            "url": data.get("url", PAGE_URL),
        }

    if not products:
        # 頁面改版或被擋都會走到這裡：寧可失敗也不要誤判成「全部下架」
        raise RuntimeError("頁面上找不到任何 MacBook 商品，可能是頁面結構改變或請求被擋")
    return products


def send_telegram(text):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    api = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
    ).encode()
    with urllib.request.urlopen(api, data=payload, timeout=30) as resp:
        result = json.loads(resp.read())
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API 回傳錯誤: {result}")


def notify(new_items):
    header = f"🆕 Apple 整修品有 {len(new_items)} 台 MacBook 新上架！\n"
    entries = [
        f"\n{item['name']}\n💰 NT${item['price']:,}\n🔗 {item['url']}\n"
        for item in new_items
    ]
    # Telegram 單則訊息上限 4096 字，超過就拆成多則
    chunk = header
    for entry in entries:
        if len(chunk) + len(entry) > TELEGRAM_MSG_LIMIT:
            send_telegram(chunk)
            chunk = ""
        chunk += entry
    if chunk:
        send_telegram(chunk)


def main():
    current = fetch_products()

    if not os.path.exists(STATE_FILE):
        # 第一次執行：建立基準清單，不發通知
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=1, sort_keys=True)
        print(f"首次執行，已記錄 {len(current)} 台 MacBook 作為基準，不發送通知")
        return

    with open(STATE_FILE, encoding="utf-8") as f:
        previous = json.load(f)

    new_skus = sorted(set(current) - set(previous))
    gone_skus = sorted(set(previous) - set(current))

    if new_skus:
        new_items = [current[sku] for sku in new_skus]
        for item in new_items:
            print(f"新上架: {item['name']} NT${item['price']:,}")
        notify(new_items)
    if gone_skus:
        for sku in gone_skus:
            print(f"已下架: {previous[sku]['name']}")
    if not new_skus and not gone_skus:
        print(f"無變化（目前 {len(current)} 台 MacBook）")

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=1, sort_keys=True)


if __name__ == "__main__":
    sys.exit(main())
