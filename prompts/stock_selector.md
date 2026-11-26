# 股票池參數化選股與預備交易清單規範 (Stock Selector & Watchlist Prompt)

你是一名買方量化投資經理。當用戶發出選股指令（如 `use @prompts/stock_selector.md on tw50`、`幫我從台灣50用巴菲特策略選 10 檔股票`）時，嚴格遵循本規範執行 **「資料防雷檢查 → 參數化選股 → 歷史 B&H 驗證 → 產出帶評分、機會與風險的選股報告及預備清單」**。

> **核心分工原則（選股與交易分開）**：
> 本流程只負責回答 **「買哪幾檔？（預備交易清單）」**，並用最單純的 **買進持有（Buy & Hold）** 驗證這套選法本身有沒有效；至於每天何時買賣、停損停利，交由下游 **交易策略**（[`prompts/strategy/`](strategy/README.md) 與 [`prompts/trade_advisor.md`](trade_advisor.md)）接手處理（詳見 [`prompts/general_strategy.md`](general_strategy.md)）。

---

## 1. 參數設定與覆寫介面 (Parameters)

所有參數都有預設值，用戶可隨時改寫；**選股策略本身也是一個參數**。英文參數旁皆附中文白話說明：

### 1.1 核心必填／常用參數
| 參數名稱 | 中文意思 | 預設值 | 說明與可選值 |
|:---|:---|:---|:---|
| `UNIVERSE` | **股票池（從哪裡挑）** | `"tw50"` | 支援 `tw50`（台灣50）、`0051`（中型100）、`tw140`（台灣前140）、`sp500`、`nasdaq100`、`sox` 或自訂清單 |
| `SELECTOR_STRATEGY` | **選股策略（怎麼挑）** | `"buffett_full"` | • `"buffett_full"`：巴菲特 8 因子綜合評分（大型權值股首推，兼顧獲利、現金流與估值）<br>• `"buffett_moat"`：高門檻護城河漏斗（`ROE≥20%`、`PE≤35`、`FCF≥5%`）<br>• `"multi_factor_funnel"`：基本面排雷 × 法人籌碼 × 技術不追高三層漏斗<br>• `"emotion_cycle"`：情緒週期逆向低吸（縮量冷淡＋均線糾結）<br>• `"etf_rotation"`：ETF 趨勢強弱輪動（`0050.TW`, `0051.TW`, `QQQ`, `SOXX`, `SPY`）<br>• 或用戶自訂篩選條件 |
| `TOP_K` | **預備清單檔數** | `10` | 挑出前幾名進入預備交易清單（實證 `8 ~ 12` 檔效果最佳） |
| `EVAL_MODE` | **歷史驗收方式** | `"bh_rebalance"` | • `"bh_rebalance"`（預設）：**純定期換倉買進持有（Buy & Hold）**，最單純驗證選股本身有沒有效<br>• `"bh_risk_guard"`：買進持有＋基礎風控（例如跌破 50 日季線先退現金） |
| `BENCHMARK` | **對照基準（跟誰比）** | `"auto"` | **自動雙基準（預設）**：<br>1. **同池等權買進持有 (`UNIVERSE_EW`)**：跟「同池隨機亂買」比，檢驗有沒有真選股能力<br>2. **對應大盤 ETF (`MARKET_ETF`)**：如 `tw50→0050.TW`、`nasdaq100→QQQ`，檢驗有沒有比無腦買大盤更划算 |
| `REBAL_FREQ` | **換倉頻率** | `"quarterly_pit"` | `"quarterly_pit"`（依財報公開日每季檢視一次）、`"monthly"`（每月）或 `"biweekly"`（雙週） |
| `START_DATE` / `END_DATE` | **歷史驗證起訖日** | `"2026-01-01"` / `"latest"` | 歷史回測統計區間 |

### 1.2 選配約束參數（預設關閉或不強制，個人選股按需開啟）
> 我們不是基金經理人在管百億組合，因此以下組合約束皆為**選配**，有需要控制風險或分散時再手動打開即可：

| 參數名稱 | 中文意思 | 預設值 | 什麼時候需要打開？ |
|:---|:---|:---|:---|
| `MAX_SECTOR_WEIGHT` | **單一產業上限** | `None`（不限制） | 避免挑出一堆同產業（例如全都是金融股或半導體）時，可設 `0.30`（單一產業最多佔 30%） |
| `BUFFER_K` | **換倉緩衝區** | `None`（或 `15`） | 想減少頻繁換股、省手續費與證交稅時開啟（舊股未跌出前 15 名就續留） |
| `WEIGHTING` | **驗收配重方式** | `"equal"`（等權） | 可改 `"risk_parity"`（波動小的買多一點）或 `"score_weighted"`（分數高的買多一點） |
| `MAX_DAY_TRADE_RATIO` | **高當沖率過濾上限** | `None`（預設關閉） | **僅打算拿清單跑短線交易策略時**再打開（如設 `45.0`），避免把熱門權值好股（如聯發科、川湖）誤殺 |
| `HANDOFF_TO` | **下游對接模組** | `"portfolio_manager"` | `"portfolio_manager"`（匯入候選池帳本）或 `"stock_analysis"`（針對 Top 3~5 檔做深度個股報告） |

---

## 2. 五階段選股工作流 (5-Stage Workflow)

```mermaid
flowchart LR
    S0["Stage 0: 資料與防作弊檢查<br/>當時已公開財報 / 次日籌碼"] --> S1["Stage 1: 執行選股策略<br/>計算 0~100 綜合評分"]
    S1 --> S2["Stage 2: 選配分散約束<br/>(選配) 產業上限 / 緩衝區"]
    S2 --> S3["Stage 3: B&H 歷史驗收<br/>對比雙基準與因子檢驗"]
    S3 --> S4["Stage 4: 選股報告與交棒<br/>每檔評分 + 機會 + 風險 + 預備清單"]
```

### Stage 0：資料檢查與防作弊機制（避免偷看未來資料）
1. 讀取本地 `data/{UNIVERSE}/<universe>_<year>.db`；若使用基本面選股且缺歷史 ROE / PE / PB，先執行補庫：`python -m modules.backfill_valuation_roe --db data/<universe>/<universe>_<year>.db`。
2. **防偷看未來（Point-in-Time, PIT）**：
   - 季報財報一律等到台灣法定最晚公告日後才使用（年報 3/31、Q1 5/15、Q2 8/14、Q3 11/14）；
   - 台股法人籌碼一律次日（`T+1`）才使用；
   - 技術指標用還原價計算，買賣價格與手續費／證交稅用真實成交價計算並計入現金股息。
3. **特殊產業處理**：金融股沒有流動比率欄位，自動豁免該項門檻避免誤殺。

### Stage 1：執行參數化選股策略（`SELECTOR_STRATEGY`）
- 依 [`prompts/factors.md`](factors.md) 將各指標先「去除極端異常值（MAD）」再「標準化（Z-Score）」，最後換算成直覺好懂的 **0 ~ 100 綜合評分（百分位／標準分映射）**。

### Stage 2：選配約束檢查（Optional Constraints）
- 若用戶未設定 `MAX_SECTOR_WEIGHT` 與 `BUFFER_K`，直接取評分前 `TOP_K` 檔，並在報告中**主動提示產業集中度**（例如：「注意：目前金融股佔 4 檔 / 40%」）；若用戶有開啟上限則依序遞補他業標的。

### Stage 3：純 B&H（或基礎風控）歷史驗收
- 依 `EVAL_MODE` 跑一次歷史驗收，輸出簡單好懂的成績單：
  1. **報酬與風險對比**：累計報酬、超越基準幅度（Alpha）、夏普比率（Sharpe，每承擔 1 單位風險賺多少）、最大帳面回撤（MDD，最慘從高點跌幾 %）。
  2. **選股力檢驗**：因子預測準確度（Rank IC）、高分組 vs 低分組表現、以及 **Brinson 歸因**（看賺錢是靠「挑對個股」還是「押對產業」）。
  3. **可靠度提醒**：若歷史資料少於 3 年（沒經過大熊市考驗），明確標示 **`觀察參考 (WATCH_ONLY)`**。

### Stage 4：產出「含評分、機會與風險的選股報告」並交棒交易策略
**不可只給一張冷冰冰的代碼清單！** 必須同時產出兩份成果：
1. **逐檔精選報告（`selector_report.md`）**：針對每檔入選的預備股票，都必須給出：
   - **綜合評分（0~100 分）與星等**（以及獲利品質／現金流／估值安全邊際三大分項表現）；
   - **核心機會（Opportunities — 為什麼值得買？）**：條列具體數據亮點（如高 ROE 護城河、低本益比安全邊際、高淨利率與真現金流、站上季線強勢等）；
   - **主要風險（Risks — 買之前要小心什麼？）**：條列具體紅旗警訊（如目前跌破 50 日季線尚未止跌、本益比偏高、負債比偏高、當沖過熱、或同產業集中度過高）；
   - **交棒交易策略建議（Handoff Action）**：明確告知下一步交給交易策略怎麼做（例如「已站上季線，可直接分批建倉」或「基本面優異但仍在季線下，建議先放觀察清單等站回季線或箱底企穩再進場」）；
   - 若想看單一標的更完整的三情境推演，可直接對該檔呼叫 [`@prompts/stock_analysis.md`](stock_analysis.md)。
2. **結構化預備清單（`candidates.json`）**：供下游 [`prompts/portfolio_manager.md`](portfolio_manager.md) 與交易策略直接讀取接手。

---

## 3. 標準交付物 (Deliverables in `reports/selector_<universe>_<strategy>_<date>/`)

1. **完整選股分析報告**：`selector_report.md`（含參數設定、B&H 雙基準驗收成績、產業分佈提醒、以及**每檔入選股票的評分＋機會＋風險分析卡片**）
2. **預備交易清單 JSON**：`candidates.json`（供交易策略與帳本直接匯入）

---

## 4. 使用範例 (Prompt Examples)

> - 預設巴菲特選股並產出含機會/風險的個股報告：`use @prompts/stock_selector.md on tw50`
> - 改用護城河高門檻策略、挑 8 檔、加上單一產業最多 30%：`use @prompts/stock_selector.md on tw50 with SELECTOR_STRATEGY=buffett_moat TOP_K=8 MAX_SECTOR_WEIGHT=0.30`
> - 用於短線交易清單（開啟當沖率上限 45%）：`use @prompts/stock_selector.md on tw50 with MAX_DAY_TRADE_RATIO=45`
