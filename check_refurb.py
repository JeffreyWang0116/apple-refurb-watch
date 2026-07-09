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
_HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(_HERE, "state.json")
CONFIG_FILE = os.path.join(_HERE, "config.json")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
KEYWORD = "MacBook"  # 只追蹤名稱含此關鍵字的商品
TELEGRAM_MSG_LIMIT = 4096

# 通知範圍設定：state.json 永遠追蹤全部 MacBook，篩選只在「發通知時」套用，
# 這樣切換範圍不會造成漏報或誤報
FILTER_LABELS = {
    "all": "全部 MacBook（Air + Pro）",
    "air": "只有 MacBook Air",
    "pro": "只有 MacBook Pro",
}


def matches_filter(name, mode):
    if mode == "air":
        return "MacBook Air" in name
    if mode == "pro":
        return "MacBook Pro" in name
    return True


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"filter": "all", "telegram_offset": 0}


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=1, sort_keys=True)


def get_updates(offset):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    api = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}"
    with urllib.request.urlopen(api, timeout=30) as resp:
        result = json.loads(resp.read())
    return result.get("result", []) if result.get("ok") else []


def status_text(config, current):
    air = sum(1 for p in current.values() if "MacBook Air" in p["name"])
    pro = sum(1 for p in current.values() if "MacBook Pro" in p["name"])
    return (
        f"📋 目前通知範圍：{FILTER_LABELS[config['filter']]}\n"
        f"頁面上現有 MacBook Air {air} 台、MacBook Pro {pro} 台\n\n"
        "指令：\n"
        "/air - 只通知 MacBook Air\n"
        "/pro - 只通知 MacBook Pro\n"
        "/all - 通知全部 MacBook\n"
        "/status - 查看目前設定\n\n"
        "（指令會在下一次檢查時處理，最多等 30 分鐘）"
    )


def process_commands(config, current):
    """讀取你在 Telegram 發給 bot 的指令，更新通知範圍設定並回覆確認。"""
    my_chat_id = os.environ["TELEGRAM_CHAT_ID"]
    for upd in get_updates(config["telegram_offset"]):
        config["telegram_offset"] = upd["update_id"] + 1
        msg = upd.get("message") or {}
        if str((msg.get("chat") or {}).get("id")) != str(my_chat_id):
            continue  # 忽略其他人傳給 bot 的訊息
        cmd = (msg.get("text") or "").strip().lower().split("@")[0]
        if cmd in ("/air", "/pro", "/all"):
            config["filter"] = cmd[1:]
            print(f"通知範圍切換為: {config['filter']}")
            send_telegram(f"✅ 已切換通知範圍：{FILTER_LABELS[config['filter']]}")
        elif cmd in ("/status", "/start", "/help"):
            send_telegram(status_text(config, current))


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
    config = load_config()
    process_commands(config, current)

    if not os.path.exists(STATE_FILE):
        # 第一次執行：建立基準清單，不發通知
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=1, sort_keys=True)
        print(f"首次執行，已記錄 {len(current)} 台 MacBook 作為基準，不發送通知")
        save_config(config)
        return

    with open(STATE_FILE, encoding="utf-8") as f:
        previous = json.load(f)

    new_skus = sorted(set(current) - set(previous))
    gone_skus = sorted(set(previous) - set(current))

    if new_skus:
        new_items = [current[sku] for sku in new_skus]
        for item in new_items:
            wanted = matches_filter(item["name"], config["filter"])
            print(f"新上架{'' if wanted else '（不在通知範圍，略過）'}: "
                  f"{item['name']} NT${item['price']:,}")
        notify_items = [i for i in new_items
                        if matches_filter(i["name"], config["filter"])]
        if notify_items:
            notify(notify_items)
    if gone_skus:
        for sku in gone_skus:
            print(f"已下架: {previous[sku]['name']}")
    if not new_skus and not gone_skus:
        print(f"無變化（目前 {len(current)} 台 MacBook，"
              f"通知範圍: {FILTER_LABELS[config['filter']]}）")

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=1, sort_keys=True)
    save_config(config)


if __name__ == "__main__":
    sys.exit(main())
