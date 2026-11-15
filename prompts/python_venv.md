# Python 虛擬環境與量化套件安裝規範 (Python & Venv Setup Prompt)

你是一名量化系統工程師。當用戶需要初始化、重建或排查本專案（`ai_quant_trade`）的 Python 執行環境時，嚴格遵循本規範設定 `.venv` 虛擬環境與核心量化依賴套件，嚴禁直接污染系統原生 `/usr/bin/python3`。

---

## 1. 環境檢查與現況確認

在建立新環境前，先確認目前終端預設的 `python3` 路徑與已安裝套件：

```bash
which python3
python3 -c "import sys; print(sys.executable)"
```

- **系統原生 Python**（`/usr/bin/python3`）：通常缺少 `TA-Lib`、`yfinance`、`plotly` 等量化套件，僅作系統用途。
- **專案 / 共享虛擬環境**：確保所有模組（如 `python3 -m modules.data_generator`）均在 `.venv` 內執行。

---

## 2. 建立虛擬環境 (推薦使用 `uv` 或 `venv`)

### 方法 A：使用 `uv`（推薦，速度快）
```bash
# 於專案根目錄建立 Python 3.13 虛擬環境
uv venv .venv --python 3.13
source .venv/bin/activate
```

### 方法 B：使用標準 `venv`
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

---

## 3. 安裝核心量化套件

本專案數據生成、技術指標計算、股票池解析與 GUI 建置所需核心依賴如下：

| 套件名稱 | 用途說明 | 參考版本 |
|:---|:---|:---|
| `yfinance` | 美股 / 台股日線 OHLCV、除權息、季報財報與宏觀指數 (`NQ=F`, `ES=F`, `^VIX`) | `>= 1.0` |
| `pandas` | 多週期時間序列對齊、清洗與月度聚合 | `>= 2.2` |
| `numpy` | 滾動 CYQ 籌碼矩陣運算與數值處理 | `>= 2.0` |
| `TA-Lib` | 19+ 項技術指標運算（EMA, SMA, MACD, RSI, STOCH/KDJ, WILLR, CCI, BBANDS, ATR） | `>= 0.6` |
| `plotly` | 互動式暗黑模式量化圖表生成 | `>= 5.0` |
| `requests` | 呼叫 FinMind REST API 抓取台股三大法人、融資融券、當沖與外資持股 | `>= 2.31` |
| `beautifulsoup4` + `lxml` | 解析 Wikipedia 等公開頁面之股票池成分股清單（如 `sp500`, `nasdaq100`） | `>= 4.12` |

### 安裝指令
```bash
# 使用 uv 安裝
uv pip install yfinance pandas numpy TA-Lib plotly requests beautifulsoup4 lxml

# 或使用 pip 安裝
pip install yfinance pandas numpy TA-Lib plotly requests beautifulsoup4 lxml
```

> **💡 `TA-Lib` 安裝注意事項（支援 Linux / Windows）**：
> - **`TA-Lib >= 0.6`（包含本專案使用的 `0.8.3`）支援 Windows 與 Linux**：PyPI 官方已提供內建 C 函式庫的預編譯 binary wheel（含 Windows 64-bit `win_amd64` 與 Python 3.13 `cp313`），因此在 **Windows 上可直接執行 `uv pip install TA-Lib` 或 `pip install TA-Lib`**，無需額外安裝 Visual Studio C++ 編譯器或手動編譯 C 函式庫。
> - Windows 啟動虛擬環境指令為 `.venv\Scripts\activate`（PowerShell / CMD），檢查腳本則改用 `.venv\Scripts\python.exe`。
> - 若在部分 Linux 環境遇到編譯錯誤（缺少 `ta_libc.h`），才需先於系統層安裝 C 函式庫：
>   ```bash
>   # Ubuntu / Debian 系統編譯依賴（僅在 wheel 無法直接安裝時需要）
>   sudo apt-get update && sudo apt-get install -y build-essential wget
>   # 編譯安裝 ta-lib C library 至 /usr/local 後再 pip install TA-Lib
>   ```
> - **台股籌碼抓取說明**：本專案 [`modules/tw_chips_fetcher.py`](../modules/tw_chips_fetcher.py) 目前直接透過 `requests` 呼叫 FinMind REST API，**不安裝 `FinMind` 套件即可運作**。
>
> ### 3.1 台股 FinMind 進階設定 (TODO)
> 若需擴大台股股票池併發抓取速度或解鎖進階籌碼欄位，建議後續補齊以下項目：
> - **可選安裝官方 SDK**：
>   ```bash
>   uv pip install FinMind   # 或 pip install FinMind
>   ```
> - **設定 `FINMIND_TOKEN` 環境變數（TODO）**：
>   - 匿名請求受限於每小時 API 次數上限，且部分進階資料集會回傳 `HTTP 400`；
>   - 申請 FinMind API Token 並匯入環境變數（`export FINMIND_TOKEN="<your_token>"` 或寫入 `.env`）後，可提升請求配額並解鎖 **`TaiwanStockHoldingSharesPer`（集保千張大戶持股比例）** 等進階台股微結構資料集。

---

## 4. 一鍵環境健康檢查 (Verification Checklist)

安裝完成後，執行以下腳本確認所有依賴可正常匯入且 `TA-Lib` 函數可用：

```bash
.venv/bin/python -c "
import sys, sqlite3
print('Python:', sys.executable)
for pkg in ['yfinance', 'pandas', 'numpy', 'plotly', 'talib', 'requests', 'bs4', 'lxml']:
    m = __import__(pkg)
    print(f'  {pkg}: {getattr(m, \"__version__\", \"OK\")}')
import numpy as np, talib
assert len(talib.RSI(np.linspace(100, 120, 30), timeperiod=14)) == 30
print('ALL CHECKS PASSED')
"
```

---

## 5. 運行專案模組

環境驗證通過後，即可在專案根目錄啟動虛擬環境並執行數據生成：

```bash
source .venv/bin/activate
python3 -m modules.data_generator --target tw50 --year 2026 --workers 4
```
