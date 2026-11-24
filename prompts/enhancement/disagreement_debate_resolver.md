# Enhancement Module: 多策略多空分歧偵測與結構化辯論裁決 (Disagreement & Evidence Debate Resolver)

> **定位**：當專案同時混搭多個策略（如 `MACD` + `KDJ` + `Bollinger` + `RSI` + `Router V2`）且出現**訊號互相打架**（例如 `MACD` 剛發 `BUY`，同日 `KDJ` 卻發 `SELL`）時，調用 `@prompts/enhancement/disagreement_debate_resolver.md` 自動偵測衝突並強制進行一輪結構化證據辯論與風險裁決。

---

## 1. Parameters (可調參數)

| 參數 | 預設值 | 說明 |
|:---|:---|:---|
| `MAX_DEBATE_ROUNDS` | `1` | 多空證據辯論輪數（建議 `1~2` 輪，避免冗長耗費上下文） |
| `CONFLICT_SIZE_PENALTY` | `0.5` | 偵測到直接多空衝突時，即使多方勝出之建議倉位乘數上限（預設砍半） |
| `REQUIRE_PASS_WEIGHT` | `true` | 辯論權重優先採信通過穩健性閘門（`PASS` / `ALL_WEATHER`）之策略，降權 `BULL_ONLY` / `UNSTABLE` |

---

## 2. 分歧自動分類器 (Conflict Classifier)

將各策略／分析維度對單一標的的最新訊號歸類為 `BULLISH`（買進／持倉看多）、`BEARISH`（賣出／空頭破位）、`NEUTRAL`（觀望／空倉），並判定衝突類型：

1. **`CONSENSUS`（高度共識）**：全為同向或僅同向＋中性 → 直接通過，無需辯論。
2. **`DIRECT_BULL_BEAR_CONFLICT`（直接多空衝突）**：同時存在 `BULLISH` 與 `BEARISH` 訊號（例如 `INTC 2026-11-18` 出現 `macd:bb_water BUY` vs `kdj:baseline SELL`）→ **強制觸發證據辯論**！
3. **`RISK_OVERRIDE_CONFLICT`（風控覆蓋衝突）**：策略看多但風控／體制（如 `Type 5 恐慌瀑布`）亮紅燈 → **風控優先，直接壓降操作等級**。
4. **`DEGRADED_CONSENSUS`（降級共識）**：部分資料或模組缺失 → 下調信心度並註明盲區。

---

## 3. 結構化證據辯論協議 (Evidence Debate Brief)

當觸發 `DIRECT_BULL_BEAR_CONFLICT` 時，必須在報告中輸出以下三段式精簡裁決（**嚴禁空泛猜測，每一句必須引用具體數據**）：

1. **🟢 多方核心證據 (Bull Case)**：
   - 哪幾個策略看多？它們的歷史穩健評級（如 `PASS 6/6`、`Sharpe`、`PF`）為何？支撐位與反轉訊號是什麼？
2. **🔴 空方核心證據 (Bear Case)**：
   - 哪幾個策略看空？當前量波體制（如 `Type 5 恐慌瀑布`、`ADX > 40`）、均線壓制與近期 8-K／財報利空是什麼？
3. **⚖️ 風控官最終裁決 (Risk-Weighted Verdict)**：
   - 依 `REQUIRE_PASS_WEIGHT` 權衡兩側歷史勝率與當前體制風險，給出明確中文決議（如「多空分歧且處恐慌瀑布 → 空倉者觀望等確認，已進場者嚴守硬停損並套用 `0.5x` 減半倉位」）。
