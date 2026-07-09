# Apple 整修品 MacBook 上架通知

每 30 分鐘檢查 [Apple 台灣整修品 Mac 頁面](https://www.apple.com/tw/shop/refurbished/mac)，
發現**新上架的 MacBook（Air / Pro）**時透過 Telegram Bot 即刻通知。

## 運作方式

- `check_refurb.py`：抓取頁面內嵌的結構化商品資料（ld+json），以 SKU 比對 `state.json`
  記錄的上次清單，有新 SKU 就發 Telegram 訊息（含型號、價格、購買連結）。
- `.github/workflows/check.yml`：GitHub Actions 每 30 分鐘執行一次，並把更新後的
  `state.json` 提交回 repo 作為下次比對基準。
- 首次執行只建立基準清單，不會發通知。

## 設定步驟

### 1. 建立 Telegram Bot

1. 在 Telegram 搜尋 **@BotFather**，傳送 `/newbot`，依指示命名。
2. 記下它給你的 **bot token**（形如 `123456789:ABC-DEF...`）。
3. 對你的新 bot 傳送任意一則訊息（例如「hi」），bot 才能傳訊息給你。
4. 取得你的 **chat ID**：瀏覽器開啟
   `https://api.telegram.org/bot<你的TOKEN>/getUpdates`，
   在回傳 JSON 裡找 `"chat":{"id":123456789}`。

### 2. 建立 GitHub Repo 並推送

1. 在 GitHub 建立一個新的 **private repo**。
2. 把這個資料夾推上去（`git push`）。

### 3. 設定 Secrets

到 repo 的 **Settings → Secrets and variables → Actions → New repository secret** 新增：

| 名稱 | 值 |
|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather 給的 token |
| `TELEGRAM_CHAT_ID` | 你的 chat ID |

### 4. 啟動

到 repo 的 **Actions** 頁籤，選 "Check Apple Refurbished MacBook"，
按 **Run workflow** 手動跑一次確認正常，之後就會自動每 30 分鐘執行。

## Bot 指令（選擇通知範圍）

直接在 Telegram 對 bot 傳送：

| 指令 | 效果 |
|---|---|
| `/air` | 只通知 MacBook Air |
| `/pro` | 只通知 MacBook Pro |
| `/all` | 通知全部 MacBook（預設） |
| `/status` | 查看目前設定與現有商品數 |

指令會在**下一次排程檢查時**處理（最多等 30 分鐘），bot 屆時會回覆確認訊息。
設定存在 `config.json`。切換範圍不影響追蹤基準——`state.json` 永遠記錄全部
MacBook，篩選只套用在發通知的當下，所以來回切換不會漏報或誤報。

## 注意事項

- GitHub Actions 的排程在尖峰時段可能延遲數分鐘，屬正常現象。
- 若 repo 連續 60 天沒有任何 commit，GitHub 會停用排程；本 workflow 會在商品
  變動時自動 commit `state.json`，一般不會觸發此限制，但若收到 GitHub 的停用
  通知信，到 Actions 頁面點一下重新啟用即可。
- 腳本只監控名稱含「MacBook」的商品；想改監控範圍，調整 `check_refurb.py`
  裡的 `KEYWORD`。
