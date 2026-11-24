# AI Quant Trade Studio (`modules/ui/`) — 零伺服器互動工作台設計與架構說明

本目錄存放專案的**純前端、零伺服器（Zero-Server）互動式控制工作台** [`studio.html`](studio.html)，讓使用者透過瀏覽器直接導覽量化流程、自由混搭 Prompt 與策略／風控模組、線上編輯專案設定檔，並一鍵產出可執行於 **Antigravity Chat**、**Antigravity CLI (`agy`)** 與 **本機 Python 模組** 的精準指令。

---

## 1. 設計理念 (Design Philosophy)

1. **零伺服器、零依賴、雙擊即開 (`file://` Ready)**：
   - 不需要啟動 FastAPI / Flask / Node.js 伺服器、不會撞 Port、沒有額外前端編譯鏈；直接以 Chrome 或 Edge 雙擊 `modules/ui/studio.html` 即可運行。
2. **流程導引 ＋ 自由混搭並行**：
   - **給新手／例行檢核**：透過四階段視覺化流程與「情境精靈（Playbooks）」讓使用者一眼看懂系統能做什麼、該從哪一步開始。
   - **給進階操作**：提供自由模組勾選介面，任意組合策略、四層風控開關、事件庫與穩健性閘門，不受單一固定腳本限制。
3. **確定性引擎與 AI Prompt 解耦**：
   - 行情更新（`data_generator`）、事件抓取（`events_news.db`）、資料庫瀏覽（`modules/viewer.html`）採本地確定性模組，不耗費 LLM Token；
   - 複雜策略研究、多報告歸納與專案帳本閉環則透過一鍵生成的 **Antigravity Chat / CLI (`agy`)** 指令交給 AI Agent 執行。

---

## 2. 系統架構圖 (Architecture Overview)

```text
┌────────────────────────────────────────────────────────────────────────────┐
│                    modules/ui/studio.html (純靜態單檔 HTML)                 │
├──────────────────────┬──────────────────────────┬──────────────────────────┤
│  1. 流程導引與情境精靈 │  2. 自由混搭 & 指令工作台  │  3. 本機檔案讀寫與覆盤入口 │
│  (Guided Playbooks)  │  (Mix & Match Builder)   │  (FS API & Review Hub)   │
│  • 4 階段系統總覽     │  • 專案 / 市場 / 標的設定 │  • File System Access API│
│  • 6 大常用任務卡片   │  • 策略模組多選 (8 引擎)  │    直讀直存 .md / .json  │
│    一鍵帶入預設參數   │  • 四層風控與倉位開關     │  • 直開 review_viewer    │
│                      │  • 即時組裝三種執行指令   │  • 直開 sql.js DB 檢視器 │
└──────────┬───────────┴────────────┬─────────────┴────────────┬─────────────┘
           │                        │                          │
           ▼                        ▼                          ▼
   【Antigravity Chat】     【Antigravity CLI / PS1】   【本機專案檔案系統】
   一鍵複製貼入對話框        • `agy -p "..."`           • prompts/**/*.md
   執行完整 Workflow         • `.venv\Scripts\python`   • workflow/*.md
                             • 下載 `.ps1` 執行腳本     • projects/<name>/
                                                        • data/*/events_news.db
```

---

## 3. 四大分頁模組說明

| 分頁 | 職責 | 核心能力 |
|:---|:---|:---|
| **🧭 1. 流程導引與情境精靈** | 降低使用門檻，建立整體操作感 | 呈現 Stage 1~4 量化閉環，內建 6 張常用情境卡片（建新專案、每日更新與買賣訊號、全變體＋四層風控對照、Router V2 盲測、事件庫更新、券商成交回報），點擊自動帶入工作台。 |
| **🧩 2. 自由混搭 & 指令工作台** | 核心指令產生器 | 左側設定專案、市場 (`US/TW`)、標的、起訖日、策略多選（Bollinger / KDJ / MACD / RSI / Router V2 / State-Score / 台股籌碼 / Trinity）及 `risk_module.md` 可調風控參數；右側即時同步輸出 **Antigravity Chat**、**`agy` CLI** 與 **Python / `.ps1`** 三種執行格式。 |
| **📝 3. Prompt / Project 編輯器** | 零伺服器本機檔案管理 | 透過 Chrome / Edge 原生 **File System Access API** 連結 `ai_quant_trade/` 根目錄後，自動遞迴掃描 `prompts/`、`workflow/`、`projects/` 下的 `.md` 與 `.json`，支援關鍵字篩選、線上編輯與直接存回硬碟。 |
| **📊 4. 報告索引與覆盤檢視器入口** | 結果檢視與多版本追溯 | 一鍵跳轉開啟 `projects/<name>/review_viewer.html`、`modules/viewer.html`（瀏覽器端 `sql.js` 免 Server 開啟 `.db`）、`price_vol_viewer.html` 與歷次時間戳報告。 |

---

## 4. 瀏覽器安全邊界與實務使用方式

- **為何不會從網頁直接執行 Shell 指令？**
  - 純靜態網頁受瀏覽器安全沙箱限制，無法直接呼叫本機進程（`agy` / `python`）。本架構刻意保留此安全邊界，改以 **「一鍵複製指令」＋「一鍵下載 `.ps1` 腳本」** 作為最安全、零維護的執行橋接。
- **File System Access API 需求**：
  - 本機檔案直讀直存功能需使用 **Chrome** 或 **Edge**（首次點擊右上角 `📂 連結本機工作區` 並授權 `ai_quant_trade` 目錄即可）；若未連結資料夾，仍可正常使用內建目錄與所有指令產生功能。

---

## 5. 擴充與維護指南 (How to Extend)

所有設定均集中於 [`studio.html`](studio.html) 頂部常數區，擴充只需修改 JSON 陣列即可：
- **新增策略模組**：於 `STRATEGIES` 陣列新增 `{ id, name, desc, checked }`。
- **新增情境精靈卡片**：於 `PLAYBOOKS` 陣列新增一張預設任務卡片。
- **新增專案報告／檢視器捷徑**：於 Tab 4（`#tab-review`）新增相對路徑連結卡片（例如 `../../projects/<new_project>/review_viewer.html`）。
