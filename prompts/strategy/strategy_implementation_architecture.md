# 量化交易策略實裝架構設計手冊 (Modular Strategy Implementation Architecture)

本手冊定義了一個生產級量化交易策略（Production-Grade Quantitative Strategy）在程式碼工程實現上的**「五位一體核心模組架構」**。超越傳統粗糙的「Entry / Exit」二元寫法，實現高內聚、低耦合的機構級可插拔交易引擎。

---

## 🏛️ 策略實裝架構全景 (Architecture Overview)

一個成熟的量化交易策略，由以下 **五大功能模組 (The 5 Core Modules)** 協同運作：

```
                              ┌────────────────────────────────────────────────────────┐
                              │            量化策略實裝五大核心模組架構                  │
                              └───────────────────────────┬────────────────────────────┘
                                                          │
         ┌───────────────────┬────────────────────┼────────────────────┬───────────────────┐
         ▼                   ▼                    ▼                    ▼                   ▼
  【模組一：過濾防護網】 【模組二：進場訊號引擎】 【模組三：動態部位定階】 【模組四：出場與風控防護】 【模組五：盤後狀態機】
   (Universe Filter)    (Entry Engine)       (Position Sizing)     (Exit & Trailing)     (State Machine)
   - 剔除當沖率>35%      - 主力投信連買>=2    - 固定全額 vs 波動定價- 硬止損 (-6%)        - 紀錄持倉成本均價
   - 剔除大宗原物料      - 外投同買共識       - 凱利公式/波動平價  - 主力巨額倒貨破月線  - 記錄波段最高收盤價
   - 均線多頭順勢門檻    - 散戶融資沉澱未追   - ATR 風險單位計算   - 投信護盤免死判定    - 管理階梯分批狀態(30%/70%)
                                                                   - 階梯分批平倉 (Tier 1/2)
```

---

## 模組一：標的適應性過濾器 (Universe & Regime Filter Module)

在執行任何進場邏輯前，作為前置守門員（Gatekeeper）。防止策略在不適合的「基因標的」上頻繁試錯。

### 1. 程式實裝規則 (Rule Implementation)
```python
def check_universe_filter(row, avg_day_trading_ratio, sector_type):
    """
    前置過濾：
    1. 剔除大宗原物料景氣循環股 (Commodity Cyclical)
    2. 剔除近 20 日平均當沖率 > 35% 的高噪聲隔日沖標的
    3. 趨勢生命線：股價必須處於 20 MA 或 50 MA 之上
    """
    if sector_type in ["Commodity_Cyclical", "Shipping_Steel"]:
        return False, "排除景氣循環原物料股"
    if avg_day_trading_ratio > 35.0:
        return False, "排除高當沖噪音投機股"
    if row["收盤價"] < row["SMA_20"]:
        return False, "股價跌破月線，不符合大趨勢多頭"
    return True, "通過前置濾網"
```

---

## 模組二：進場訊號引擎 (Entry Signal Engine)

負責捕捉「主力默默吸籌、散戶退場、外資投信共振」的波段發起點。

### 1. 程式實裝規則 (Rule Implementation)
滿足以下 **全部維度** 觸發開倉訊號：
```python
def check_entry_signal(df, idx):
    row = df.loc[idx]
    
    # 1. 主力連續性或共識訊號 (滿足其一)
    # 條件 A: 投信連買 >= 2 天
    sitc_consec_buy = (idx >= 1 and df.loc[idx, "投信買賣超張數"] > 0 and df.loc[idx-1, "投信買賣超張數"] > 0)
    
    # 條件 B: 外資投信同買 (外資>0, 投信>門檻, 合計>共識門檻)
    fgn = row["外資買賣超張數"]
    sitc = row["投信買賣超張數"]
    # 根據標的規模自動調整門檻 (大型股 500/2000, 中小型 100/500)
    inst_consensus = (fgn > 0 and sitc > 200 and (fgn + sitc) > 1000)
    
    has_inst_inflow = (sitc_consec_buy or inst_consensus)
    
    # 2. 散戶槓桿沉澱 (散戶未跟風攪局)
    margin_clean = (row["融資日增減"] <= 300)
    
    # 3. 技術順勢確認
    tech_bull = (row["收盤價"] >= row["SMA_20"])
    
    if has_inst_inflow and margin_clean and tech_bull:
        return True, "觸發主力波段吸籌進場訊號"
    return False, ""
```

---

## 模組三：動態部位管理與資金定階 (Position Sizing & Capital Allocation)

**「決定賺多少的不是訊號，而是部位（Position Sizing）！」**
拒絕無腦 100% 滿倉，依據市場波動率調整下單張數。

### 1. 程式實裝規則 (Rule Implementation)
```python
def calculate_position_size(account_cash, current_price, current_atr, risk_tolerance=0.01):
    """
    基於波動率 (ATR) 的風險平價部位計算：
    限制單筆交易的最大止損虧損金額，不超過總帳戶權益的 1%
    """
    risk_amount = account_cash * risk_tolerance  # 本筆交易願意承擔的最大虧損 (例如 10,000 元)
    stop_distance = max(current_price * 0.06, 2.0 * current_atr) # 停損距離 (至少 6% 或 2 倍 ATR)
    
    # 允許買進的總股數
    target_shares = int(risk_amount / stop_distance)
    
    # 最大資本上限約束 (單檔標的不超過可用現金的 95%)
    max_affordable_shares = int((account_cash * 0.95) / (current_price * 1.000855))
    final_shares = min(target_shares, max_affordable_shares)
    
    return max(final_shares, 0)
```

---

## 模組四：動態出場、停利與風控防護網 (Exit & Risk Shield Engine)

本模組是策略的核心靈魂，涵蓋 **四層動態階梯防禦機制**：

```
持倉價格走勢
     ▲
     │                             最高峰值 P_max
     │                                ╭───╮
     │                               │     ╰──► 跌幅達 8%: 觸發【層級 3 階梯分批】
     │         進場點 P_entry        │           - 檢查投信護盤免死金牌？
     │           ╭───╮              │           - 若無護盤：先賣 30% 鎖利，剩餘 70% 保留
     │          │     ╰────────────╯
     │          │
─────┴──────────┼─────────────────────────────────────────────────────────────► 時間
                ▼ 跌幅達 6%: 觸發【層級 1 硬停損】 (無條件清倉)
                ▼ 單日三大法人賣超 > 1.8 萬張 且破月線: 觸發【層級 2 法人巨額出貨逃頂】
```

### 1. 程式實裝規則 (Rule Implementation)
```python
def evaluate_exit(position, current_row, avg_daily_vol):
    """
    返回: (action_code, sell_shares, reason)
    action_code: 'HOLD', 'PARTIAL_30', 'FULL_EXIT'
    """
    p = current_row["收盤價"]
    p_entry = position["entry_price"]
    p_max = position["highest_price"]
    shares = position["shares"]
    sma20 = current_row["SMA_20"]
    sma50 = current_row["SMA_50"]
    tot_inst = current_row["三大法人合計張數"]
    sitc = current_row["投信買賣超張數"]
    
    # 【層級 1：絕對硬停損 (Hard Stop Loss)】
    if p <= p_entry * 0.94:
        return 'FULL_EXIT', shares, "跌破成本 6% 觸發硬停損"

    # 【層級 2：主力巨額倒貨逃頂避險 (Institutional Dump)】
    dump_threshold = -max(2000, int(avg_daily_vol * 0.15))
    if tot_inst < dump_threshold and p < sma20:
        return 'FULL_EXIT', shares, f"三大法人單日爆賣 {tot_inst} 張且跌破月線"

    # 【層級 3：波段移動停利與投信護盤保護】
    trail_drawdown = (p - p_max) / p_max
    if trail_drawdown <= -0.08:
        # A. 投信護盤免死金牌檢驗
        sitc_support_th = max(200, int(avg_daily_vol * 0.02))
        if sitc >= sitc_support_th and p >= sma50:
            # 豁免清倉！僅上移保本線
            position["entry_price"] = max(p_entry, p)
            return 'HOLD', 0, "高點回檔 8% 但投信逆勢護盤且站穩季線，豁免停利"
            
        # B. 階梯分批平倉 (Tiered Scaling Out)
        if not position["tier1_executed"]:
            # 第一梯次：賣出 30% 部位保底鎖利
            sell_30 = int(shares * 0.3)
            position["tier1_executed"] = True
            return 'PARTIAL_30', sell_30, "回檔 8% 執行第一梯次減碼 30% 鎖利"
        else:
            # 第二梯次：若實體跌破月線，清倉剩餘 70%
            if p < sma20:
                return 'FULL_EXIT', shares, "跌破月線，結清剩餘 70% 底倉"

    return 'HOLD', 0, "持股續抱"
```

---

## 模組五：持倉生命週期狀態機 (State Machine Module)

負責在每一日收盤後，精確維護持倉元資料，杜絕歷史狀態錯位。

### 1. 狀態維護結構 (State Schema)
```python
class PositionTracker:
    def __init__(self):
        self.in_position = False
        self.entry_date = None
        self.entry_price = 0.0
        self.highest_price = 0.0
        self.current_shares = 0
        self.total_cost = 0.0
        self.tier1_executed = False
        self.holding_days = 0

    def update_daily(self, close_price):
        if self.in_position:
            self.highest_price = max(self.highest_price, close_price)
            self.holding_days += 1
```

---

## 總結：當前策略實裝的每日執行流水線 (Daily Loop Pipeline)

在真實程式碼或回測主循環中，每日收盤後依序執行以下 5 步：

```python
# 每日盤後定時執行 (16:30 籌碼資料就緒後)
for today in trading_calendar:
    # 1. 取得當日行情與微觀籌碼數據
    row = get_daily_chips_data(symbol, today)
    
    # 2. 若在持倉中 -> 呼叫【模組四：出場與風控防護】
    if position.in_position:
        position.update_daily(row["收盤價"])
        action, sell_qty, reason = evaluate_exit(position, row, avg_vol)
        if action in ['PARTIAL_30', 'FULL_EXIT']:
            execute_order(action, sell_qty, next_day_open, reason)
            
    # 3. 若為空倉中 -> 呼叫【模組一：前置過濾】與【模組二：進場引擎】
    elif not position.in_position:
        ok_filter, _ = check_universe_filter(row, avg_day_trade, sector)
        if ok_filter:
            buy_signal, reason = check_entry_signal(df, today_idx)
            if buy_signal:
                # 呼叫【模組三：動態部位定階】
                buy_qty = calculate_position_size(account_cash, row["收盤價"], row["ATR_14"])
                execute_order('BUY', buy_qty, next_day_open, reason)
```
