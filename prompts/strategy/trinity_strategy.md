# 三位一體終極量化防禦系統策略規範 (Grand Trinity Strategy Prompt)

你是一名機構級首席風控官與多維度量化系統架構師。當用戶要求對指定股票清單與日期區間執行 **三位一體 (Grand Trinity: MACD + Bollinger + KDJ) 系統** 測試或回測（如調用 `@prompts/strategy/trinity_strategy.md`）時，嚴格遵循本規範定義的參數介面、四階立體聯合作戰邏輯與五大變體規則執行。

---

## 1. Parameters (預設參數與覆寫介面)

以下為預設參數配置；若用戶於測試指令中指定不同數值，**一律以用戶覆寫值為準**：

| 參數名稱 | 預設值 | 說明 |
|:---|:---|:---|
| `SYMBOLS` | *(必填，無預設)* | 目標測試標的清單（如 `["NVDA", "TSLA", "INTC"]`） |
| `START_DATE` | *(必填，無預設)* | 回測統計起始日（如 `"2022-01-01"`） |
| `END_DATE` | *(必填，無預設)* | 回測統計結束日（如 `"2025-12-31"`） |
| `MODEL_KEY` | `"compare"` | 執行指定變體（`raw_trinity`, `macd_bb_fusion`, `bb_kdj_fusion`, `grand_trinity`, `regime_adaptive_trinity`）或 `"compare"` 全變體對比 |
| `FIXED_CASH` | `10000.0` | 單筆固定開倉本金 |
| `SLIPPAGE` | `0.0005` | 雙邊滑點（5 bps） |
| `COMMISSION_RATE` | `0.0003` | 單邊手續費率（台股請覆寫為手續費 `0.000855` + 賣出證交稅 `0.003`） |
| `MACD_FAST` / `SLOW` / `SIGNAL` | `12` / `26` / `9` | Layer 1 宏觀趨勢濾網 MACD 參數 |
| `BB_PERIOD` / `BB_STD` | `20` / `2.0` | Layer 2 波動結構布林通道參數 |
| `BW_MIN_THRESHOLD` | `0.12` | Layer 2 最小帶寬擴張門檻 (12%) |
| `BW_LOOKBACK` | `5` | 帶寬向上擴張比較天數 ($\text{BW}_t > \text{BW}_{t-\text{lookback}}$) |
| `KDJ_N` / `M1` / `M2` | `9` / `3` / `3` | Layer 3 微觀精確扳機 KDJ 參數 |
| `KDJ_NO_CHASE_K` / `J` | `65.0` / `85.0` | Layer 3 常態金叉禁追高上限 |
| `ATR_PERIOD` | `14` | Layer 4 ATR 真實波幅週期 |
| `BREAKEVEN_MFE_PCT` | `10.0` | Layer 4.2 保本鎖定觸發浮盈 (%) |
| `BREAKEVEN_BUFFER` | `1.015` | Layer 4.2 保本止損價倍數（進場價 + 1.5%） |
| `TRAIL_MFE_PCT` | `20.0` | Layer 4.3 動態 ATR 止盈觸發浮盈 (%) |
| `TRAIL_ATR_MULT` | `2.5` | Layer 4.3 動態追蹤止盈 ATR 回落倍數 |
| `REGIME_OVERRIDE` | `"auto"` | `"auto"`（依清單/波動特徵分類）或強制指定 `"MOMENTUM"` / `"CYCLICAL"` |
| `WARMUP_BARS` | `50` | `START_DATE` 之前預留的最小暖身 K 線數 |

---

## 2. 策略定位與核心哲學 (Strategy Identity)

- **立體四階分工**：將單一指標的盲點拆解為「宏觀濾網 + 中觀結構 + 微觀扳機 + 階梯風控」：
  - **Layer 1 宏觀趨勢濾網 (MACD)**：過濾逆勢接飛刀，僅在多頭排列 ($\text{DIF} > 0$) 或水下轉折金叉 ($\text{DIF} \le 0 \land \text{MACD\_GC}$) 允許作戰。
  - **Layer 2 波動率與結構確認 (Bollinger)**：確認帶寬有效擴張 ($\text{BW} \ge \text{BW\_MIN\_THRESHOLD} \land \text{BW}_t > \text{BW}_{t-\text{BW\_LOOKBACK}}$) 且價格站上中軌或突破上軌，斬斷箱體假突破。
  - **Layer 3 微觀精確打擊 (KDJ)**：嚴格執行禁追高保護，抓低位拐點或布林新鮮突破切入。
  - **Layer 4 機構級階梯防禦與止盈 (Tiered Risk Engine)**：動態鎖定成本保本與 $\text{ATR}$ 追蹤止盈，將個股極端熊市回撤壓制至全場最低，短線摩擦稅大降近 89%。

---

## 3. 五大策略變體邏輯 (Model Variants)

| `MODEL_KEY` | 策略名稱 | 進場條件 (Entry Rule) | 出場條件 (Exit Rule) | 實盤定位 |
|:---|:---|:---|:---|:---|
| `raw_trinity` | 原始三位一體交集 | $(\text{DIF} > \text{DEA}) \land (C_t > \text{Upper}_t) \land (K_t > D_t)$，且當日出現新鮮布林突破、KDJ 金叉或 MACD 金叉之一 | $C_t < \text{Mid}_t$ 或 `kdj_dc` | 基礎三指標交集對照組 |
| `macd_bb_fusion` | MACD 水下 + BB 擴張 | 水下底分型轉折（$\text{DIF} \le 0 \land (\text{MACD\_GC}$ 或剛轉多)）$\land \text{BW} \ge \text{BW\_MIN\_THRESHOLD} \land \text{BW}_t > \text{BW}_{t-\text{BW\_LOOKBACK}} \land C_t > \text{Mid}_t$ | $C_t < \text{Mid}_t$ 或 `macd_dc` | 底部結構起漲聯動 |
| `bb_kdj_fusion` | BB 下軌 + KDJ 超賣 | 布林下軌反彈（$C_{t-1} \le \text{Lower}_{t-1} \land C_t > \text{Lower}_t$ 或下影線刺穿收回）$\land$ KDJ 低位金叉 ($K < 45 \lor J < 20$) 或 $(K < 35 \land K > D)$ | $C_t \ge \text{Mid}_t$ 或 $(K_t > 70 \land \text{kdj\_dc})$ | 週期/震盪股防禦型低吸 |
| `grand_trinity` | **四階 Grand Trinity** | **L1**: $(\text{DIF} > 0) \lor (\text{DIF} \le 0 \land \text{MACD\_GC})$<br>**L2**: $(C_t > \text{Mid}_t \lor C_t > \text{Upper}_t) \land ((\text{BW} \ge \text{BW\_MIN\_THRESHOLD} \land \text{BW}_t > \text{BW}_{t-\text{BW\_LOOKBACK}}) \lor \text{BB\_Fresh\_Break})$<br>**L3**: $[\text{kdj\_gc} \land K < \text{KDJ\_NO\_CHASE\_K} \land (K < 45 \lor J < 20 \lor \text{DIF} > 0)]$ 或 $[\text{BB\_Fresh\_Break} \land K < 85 \land J < 100]$ | **L4.1**: 基準防禦線 $\text{Mid}_t$<br>**L4.2**: $\text{MFE} \ge \text{BREAKEVEN\_MFE\_PCT}$ 鎖定保本 $P_{\text{entry}} \times \text{BREAKEVEN\_BUFFER}$<br>**L4.3**: $\text{MFE} \ge \text{TRAIL\_MFE\_PCT}$ 啟用 $H_{\text{peak}} - \text{TRAIL\_ATR\_MULT} \times \text{ATR}_t$<br>**L4.4**: 鈍化保護（超買區 $K>80, J>100$ 不因死叉輕易平倉，需跌破 $\text{stop}$ 才出場） | 全天候機構級主戰系統 |
| `regime_adaptive_trinity` | **三位一體風格自適應 (盾牌王)** | **成長動能股 (`MOMENTUM`)** 執行 `grand_trinity`；**週期/震盪/指數 (`CYCLICAL`)** 執行 `bb_kdj_fusion` | 依所屬引擎規則出場 | **🛡️ 終極防禦盾牌**（全場最低回撤與最低磨損） |

---

## 4. 測試執行檢查清單 (Execution Checklist)

1. 指標預熱至少需 `WARMUP_BARS` 根 K 線，僅統計 `[START_DATE, END_DATE]` 期間產生的交易。
2. 若執行 `regime_adaptive_trinity`，需明確揭露每檔測試標的之風格歸類（`grand_trinity` vs `bb_kdj_fusion`）。
3. 產出結果時，除標準績效表外，應特別突顯 **Strategy MDD % vs Buy & Hold MDD % 的風險壓制幅度** 與 **Chop Tax (<=10d $) 減免比例**。


---

## 5. Conclusions & Human Decision Guide (歷史實證結論、優劣勢與優化解析)

> 基準數據來源：SOX 30 + Mag 7 共 35 檔個股（2020-01-02 至 2026-11-10，單筆固定開倉 `$10,000`）。

### 📊 核心實證績效對照
- **`regime_adaptive_trinity` (三位一體風格自適應 — 終極防禦盾牌)**：
  - 總交易數 `616 筆`｜綜合勝率 **`53.1%`**｜PF **`1.71`**｜盈虧比 `1.51x`｜單筆期望 `$142.08`｜總淨利 `$87,518.25`。
  - **摩擦稅壓制**：短線磨損僅 `-$25,053.71`，相比原始單指標**大降 88.7%**。
  - **極端回撤壓制**：全市場平均最大回撤壓制在 **`-23.4%`**（全場最優）；其中 2022 年熊市期間，`TSLA` 最大回撤由 `-73.6%` 壓制到 **`-7.89%`**，`NVDA` 回撤由 `-66.4%` 降至 **`-14.89%`**。

### ✅ 優點 (Pros) vs ❌ 缺點與盲點 (Cons)
- **Pros (優勢)**：
  1. **全場最強尾部風險防禦**：將高波動科技股在系統性熊市動輒 -66%~-73% 的毀滅性回撤，壓制至個位數到十幾趴（如 TSLA `-7.89%`、NVDA `-14.89%`）。
  2. **極致抑制無效磨損**：三層共振天然濾除絕大多數假突破，短線摩擦稅大降 **88.7%**。
  3. **平衡的交易心理體驗**：`53.1%` 勝率配合 `1.71` 獲利因子，既不像純趨勢策略常連虧 6~7 次，也不像純抄底策略長期空倉等待。
- **Cons (缺點與風險)**：
  1. **過度過濾犧牲總利潤上限**：三個指標同時滿足的條件嚴苛，會錯過部分單邊牛市的早期起漲或中途急漲段，總淨利（`$87.5k`）顯著低於 `MACD ADX ($317.8k)` 與 `RSI 動能突破 ($268.4k)`。
  2. **架構複雜度較高**：參數較多（MACD + BB + KDJ + ATR），測試新市場時需留意各層門檻是否因波動率差異（例如台股或低波動藍籌股）而過度濾掉訊號。

### 🔧 哪些優化真正有效？(What Refinements Help & Why)
1. **三層職責分離取代強行交集 (`grand_trinity`)**：
   - **關鍵**：不再要求 MACD、BB、KDJ 同一天同時金叉（那會導致幾乎沒訊號），而是讓 **MACD 管大方向、BB 管波動率結構、KDJ 管微觀低位扳機**，在保留合理交易數（616 筆）的同時確保訊號品質。
2. **四階階梯風控引擎 (Layer 4) — 壓制 MDD 的核心秘密**：
   - **效果**：`MFE >= 10%` 自動將停損拉高至成本 `+1.5%`（杜絕贏單變輸單）；`MFE >= 20%` 改由 `Peak - 2.5*ATR` 追蹤（鎖定主升浪大半浮盈）；超買鈍化區（`K > 80, J > 100`）禁止因死叉輕易離場。這套風控是壓低極端回撤最關鍵的工程設計。
3. **成長與週期雙軌分流 (`regime_adaptive_trinity`)**：
   - **效果**：成長股走 `grand_trinity` 吃波段、週期股走 `bb_kdj_fusion` 吃箱體反彈，兼顧全天候資產組合穩定度。

### 🧠 人類決策與學習重點
- **定位認知**：**它不是賺最多錢的「矛」，而是讓你活過任何熊市的「盾」**。當資金規模大、極度厭惡回撤，或面對波動劇烈的高 Beta 成長股組合時，應優先部署三位一體系統。
- **測試新標的觀察點**：若在某檔新股票或新日期區間發現 `grand_trinity` 交易筆數過少（例如 0~2 筆），可檢查 `BW_MIN_THRESHOLD`（預設 `0.12`）是否高於該標的常態帶寬，並適度調降後再觀察回撤與勝率變化。
