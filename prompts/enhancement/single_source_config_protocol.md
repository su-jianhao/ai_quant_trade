# Enhancement Module: 單一參數真理源與原子寫入協議 (Single Source of Truth Config & Atomic I/O)

> **定位**：借鏡 `quantitative_analysis` 的「一處定義、多處消費」設計。調用 `@prompts/enhancement/single_source_config_protocol.md` 時，確保所有策略門檻、風控開關、回測腳本、訊號掃描與前端 UI（`modules/ui/studio.html`）統一讀取同一份設定檔，徹底消除口徑漂移與檔案寫入損壞。

---

## 1. 參數解析優先順序 (Configuration Precedence)

所有回測引擎、訊號掃描腳本與 Prompt 執行器，必須嚴格遵守由高至低的覆寫鏈（**禁止在各腳本內硬編碼不同預設值**）：

1. **最高優先**：當次對話／CLI 明確傳入的執行覆寫參數；
2. **專案真理源**：`projects/<PROJECT_NAME>/config.json`（涵蓋 `broker`、`risk`、`prompts_mix`、`data_sources`、`custom`）；
3. **範本回退預設**：`projects/template/config.json`（僅在專案設定檔缺少特定鍵值時回退）。

---

## 2. 標準化可調風控與策略區塊 (`config.json`)

建議於 `projects/<PROJECT_NAME>/config.json` 維護以下可調鍵值（皆為彈性參數，不寫死）：

```json
{
  "risk": {
    "sizing_mode": "single_shot",
    "risk_budget_pct": 1.5,
    "max_single_position_pct": 25.0,
    "hard_stop_pct": 8.0,
    "hard_stop_atr_mult": 2.5,
    "breakeven_trigger_pct": 15.0,
    "chandelier_atr_mult": 3.0,
    "deadband_pct": 15.0,
    "enable_pyramiding": false,
    "enable_overheat_trim": true,
    "enable_pre_earnings_trim": false
  }
}
```

---

## 3. 原子寫入與口徑快照防呆 (Atomic Write & Run Snapshot)

1. **原子寫入（Atomic File Replacement）**：
   - 更新 `config.json`、`run_meta.json` 或任何 JSON 設定檔時，必須先寫入同目錄暫存檔 `*.json.tmp` 並驗證 JSON 格式無誤後，再以 `os.replace(tmp_path, target_path)` 原子替換，杜絕中斷造成設定檔損毀。
2. **執行快照鎖定（Immutable Run Snapshot）**：
   - 每次產出新時間戳報告時，將當次實際生效的完整參數字典寫入該目錄的 `run_meta.json`，確保日後即使修改了 `config.json`，歷史報告仍可 100% 重現當時的測試條件。
