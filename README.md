# Phil 的 AI 學院：會員通（LINE Member Kit）第一個客戶

> 程式來自範本 [philko2017/line-member-kit](https://github.com/philko2017/line-member-kit)（私人）。改程式先改範本，再複製到這裡；這個 repo 只多了 `liff/member/app.js` 的 `CONFIG`（本客戶的 LIFF ID 與 webhook）。

LINE 官方帳號「Phil 的 AI 學院」的會員申請、匯款回報與選單切換。架構沿用 [line-namecard](https://github.com/philko2017/line-namecard) 的會員模組：LINE 官方帳號＋LIFF＋Make＋Notion，只用回覆和網頁，不耗 LINE 訊息量。

```
加好友 ──► 非會員 ──申請入會＋匯款回報──► 審核中 ──管理者核准──► 一般會員 ／ 高級會員
         （訪客選單）                    （訪客選單）              （會員選單）
會員 ──停權──► 訪客選單
```

## 組成

| 部分 | 位置 | 說明 |
|---|---|---|
| 會員頁面（LIFF） | `liff/member/` | 依身分顯示：申請表（方案、匯款、基本資料）／審核中／會員資料／停權。`?v=about` 學院介紹，`?v=courses`、`?v=ai` 目前是「即將推出」 |
| 前台內容 | Notion「前台設定」（一列）、「方案」 | 學院名稱、介紹、歡迎語、各身分的說明、收款帳戶、方案與價格都在 Notion。Make 每次讀出來交給頁面，**repo 裡不放任何業務資料** |
| Make 情境 | `tools/make_blueprints.py` 產生三份藍圖 | 「AI學院｜會員 API」「AI學院｜會員：LINE 事件」「AI學院｜會員：建立圖文選單（手動執行）」 |
| Notion | Phil 工作區「Phil AI 學院」底下的「會員名冊」 | 欄位名稱要和 `make_blueprints.py` 一字不差 |

## 身分與方案

| 身分 | 選單 | 怎麼來的 |
|---|---|---|
| 非會員 | 訪客 | 加好友或第一次打開會員頁面 |
| 審核中 | 訪客 | 送出申請 |
| 一般會員 | 會員 | 管理者核准 |
| 高級會員 | 會員 | 管理者在 Notion 手動改，再點「套用身分」 |
| 已到期 | 訪客 | 到期日加 3 天寬限後，由每天的到期檢查改（尚未建立）；用同一張表續費 |
| 停權 | 訪客 | 管理者在 Notion 手動改，再點「套用身分」 |

方案與價格在 Notion「方案」表，核准時依該方案的「會籍月數」寫入到期日。到期前 7 天在會員畫面提醒（不推播）；到期後寬限 3 天才改成「已到期」，這個每天的檢查情境還沒做。

## 部署

1. 在 Make 建好 Notion、LINE 兩個連線和兩個 webhook（會員 API 用一般 webhook，LINE 事件用 LINE 的 Watch Events）。
2. 複製 `tools/config.example.json` 成 `tools/config.local.json`，填入編號和核准密鑰。
3. `python3 tools/make_blueprints.py` 產生 `make/` 裡的藍圖，到 Make 匯入（藍圖含連線編號，不用逐一重選）。
4. 把 `liff/member/app.js` 開頭 `CONFIG` 的 `liffId`、`apiUrl` 換成實際的值，推上 GitHub。
5. LIFF app 的 Endpoint URL 填 `https://philko2017.github.io/phil-ai-academy/liff/member/`。
6. 在 Notion 會員名冊加「核准按鈕」「套用身分按鈕」兩個公式欄位（連結帶密鑰，呼叫會員 API 的 `a=approve`、`a=sync`）。

Make 免費方案最多兩個啟用中的情境：會員 API、LINE 事件保持開啟；建立圖文選單平常關閉，要用時手動「執行一次」。

## 本機預覽

```bash
python3 -m http.server 5194
```

打開 <http://localhost:5194/liff/member/> 會用 `mock.js` 的模擬資料，不連 LINE 和 Make。網址加 `?state=pending`、`member`、`premium`、`expired`、`banned` 直接看各身分的畫面。
