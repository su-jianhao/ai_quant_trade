"""Taiwan stock microstructure & institutional chips fetcher via FinMind REST API."""

from __future__ import annotations

import time
from typing import Optional

import numpy as np
import pandas as pd
import requests

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


def _finmind_get(dataset: str, stock_id: str, start_date: str, end_date: str, retries: int = 3) -> list[dict]:
    """Fetch a dataset from FinMind REST API with exponential backoff."""
    params = {
        "dataset": dataset,
        "data_id": stock_id,
        "start_date": start_date,
        "end_date": end_date,
    }
    for attempt in range(retries):
        try:
            resp = requests.get(FINMIND_URL, params=params, timeout=15)
            if resp.status_code == 200:
                payload = resp.json()
                if payload.get("status") == 200:
                    return payload.get("data", [])
            if resp.status_code in (429, 502, 503, 504):
                time.sleep(1.5 * (2 ** attempt))
                continue
            return []
        except requests.RequestException:
            time.sleep(1.0 * (attempt + 1))
    return []


def _classify_chip_pattern(row: pd.Series, pct_chg: float = 0.0) -> str:
    """Diagnose practical Taiwan chip pattern label."""
    f_net = row.get("foreign_net_lots", 0.0) or 0.0
    t_net = row.get("trust_net_lots", 0.0) or 0.0
    inst = row.get("inst_total_net_lots", 0.0) or 0.0
    m_chg = row.get("margin_net_change", 0.0) or 0.0
    sm_ratio = row.get("short_margin_ratio", 0.0) or 0.0

    if sm_ratio >= 25.0 and pct_chg >= 0:
        return "潛在軋空"
    if f_net > 0 and t_net > 0 and m_chg <= 0:
        return "波段起漲"
    if f_net > 0 and t_net > 0:
        return "外投同買"
    if inst < 0 and m_chg > 0 and pct_chg > 0:
        return "拉高出貨"
    if t_net > 0 and m_chg < 0 and pct_chg < 0:
        return "主力洗盤"
    if inst < 0:
        return "法人調節"
    if inst > 0:
        return "法人偏多"
    return "籌碼中性"


def fetch_taiwan_chips(
    ticker: str,
    start_date: str,
    end_date: str,
    daily_df: Optional[pd.DataFrame] = None,
) -> tuple[pd.DataFrame, str]:
    """Fetch institutional investors, margin/short, day trading, and foreign holding % for a TW ticker.

    Returns (chips_df, stock_name).
    """
    stock_id = ticker.split(".")[0].strip()
    stock_name = stock_id

    # 1. Institutional investors
    inst_rows = _finmind_get("TaiwanStockInstitutionalInvestorsBuySell", stock_id, start_date, end_date)
    if inst_rows:
        idf = pd.DataFrame(inst_rows)
        idf["net_lots"] = (pd.to_numeric(idf["buy"], errors="coerce").fillna(0.0)
                           - pd.to_numeric(idf["sell"], errors="coerce").fillna(0.0)) / 1000.0
        piv = idf.pivot_table(index="date", columns="name", values="net_lots", aggfunc="sum", fill_value=0.0)
        foreign = piv.get("Foreign_Investor", 0.0) + piv.get("Foreign_Dealer_Self", 0.0)
        trust = piv.get("Investment_Trust", 0.0)
        dealer = piv.get("Dealer_self", 0.0) + piv.get("Dealer_Hedging", 0.0) + piv.get("Dealer", 0.0)
        inst_df = pd.DataFrame({
            "date": piv.index,
            "foreign_net_lots": np.round(foreign, 1),
            "trust_net_lots": np.round(trust, 1),
            "dealer_net_lots": np.round(dealer, 1),
        }).reset_index(drop=True)
        inst_df["inst_total_net_lots"] = (
            inst_df["foreign_net_lots"] + inst_df["trust_net_lots"] + inst_df["dealer_net_lots"]
        ).round(1)
    else:
        inst_df = pd.DataFrame(columns=[
            "date", "foreign_net_lots", "trust_net_lots", "dealer_net_lots", "inst_total_net_lots"
        ])

    # 2. Margin Purchase & Short Sale
    margin_rows = _finmind_get("TaiwanStockMarginPurchaseShortSale", stock_id, start_date, end_date)
    if margin_rows:
        mdf = pd.DataFrame(margin_rows)
        margin_df = pd.DataFrame({
            "date": mdf["date"],
            "margin_buy": pd.to_numeric(mdf.get("MarginPurchaseBuy", 0), errors="coerce").fillna(0.0),
            "margin_sell": pd.to_numeric(mdf.get("MarginPurchaseSell", 0), errors="coerce").fillna(0.0),
            "margin_balance": pd.to_numeric(mdf.get("MarginPurchaseTodayBalance", 0), errors="coerce").fillna(0.0),
            "short_buy": pd.to_numeric(mdf.get("ShortSaleBuy", 0), errors="coerce").fillna(0.0),
            "short_sell": pd.to_numeric(mdf.get("ShortSaleSell", 0), errors="coerce").fillna(0.0),
            "short_balance": pd.to_numeric(mdf.get("ShortSaleTodayBalance", 0), errors="coerce").fillna(0.0),
        }).sort_values("date").reset_index(drop=True)
        margin_df["margin_net_change"] = margin_df["margin_balance"].diff().fillna(0.0)
        margin_df["short_net_change"] = margin_df["short_balance"].diff().fillna(0.0)
        margin_df["short_margin_ratio"] = np.where(
            margin_df["margin_balance"] > 0,
            np.round(margin_df["short_balance"] / margin_df["margin_balance"] * 100.0, 2),
            0.0,
        )
    else:
        margin_df = pd.DataFrame(columns=[
            "date", "margin_buy", "margin_sell", "margin_balance", "margin_net_change",
            "short_buy", "short_sell", "short_balance", "short_net_change", "short_margin_ratio",
        ])

    # 3. Day Trading
    dt_rows = _finmind_get("TaiwanStockDayTrading", stock_id, start_date, end_date)
    if dt_rows:
        ddf = pd.DataFrame(dt_rows)
        dt_df = pd.DataFrame({
            "date": ddf["date"],
            "day_trading_lots": np.round(pd.to_numeric(ddf.get("Volume", 0), errors="coerce").fillna(0.0) / 1000.0, 1),
        })
    else:
        dt_df = pd.DataFrame(columns=["date", "day_trading_lots"])

    # 4. Foreign Shareholding % & Chinese Stock Name
    sh_rows = _finmind_get("TaiwanStockShareholding", stock_id, start_date, end_date)
    if sh_rows:
        sdf = pd.DataFrame(sh_rows)
        if "stock_name" in sdf.columns and sdf["stock_name"].dropna().any():
            stock_name = str(sdf["stock_name"].dropna().iloc[-1])
        sh_df = pd.DataFrame({
            "date": sdf["date"],
            "foreign_holding_ratio": pd.to_numeric(
                sdf.get("ForeignInvestmentSharesRatio", np.nan), errors="coerce"
            ),
        }).drop_duplicates(subset=["date"], keep="last")
    else:
        sh_df = pd.DataFrame(columns=["date", "foreign_holding_ratio"])

    # Merge all chips tables on date
    dates = sorted(set(inst_df["date"]).union(margin_df["date"]).union(dt_df["date"]).union(sh_df["date"]))
    if not dates:
        return pd.DataFrame(), stock_name

    merged = pd.DataFrame({"date": dates})
    for sub in (inst_df, margin_df, dt_df, sh_df):
        if not sub.empty:
            merged = merged.merge(sub, on="date", how="left")

    merged["ticker"] = ticker
    merged["tdcc_large_holder_ratio"] = np.nan

    # Compute day_trading_ratio using total volume from daily_df if available
    if daily_df is not None and not daily_df.empty and "day_trading_lots" in merged.columns:
        vol_map = (daily_df["volume"] / 1000.0).to_dict()
        vol_lots = merged["date"].map(lambda d: vol_map.get(pd.Timestamp(d), np.nan))
        merged["day_trading_ratio"] = np.where(
            vol_lots > 0,
            np.round(merged["day_trading_lots"].fillna(0.0) / vol_lots * 100.0, 2),
            np.nan,
        )
        pct_map = daily_df["pct_change"].to_dict()
        merged["chip_pattern"] = [
            _classify_chip_pattern(row, float(pct_map.get(pd.Timestamp(row["date"]), 0.0)))
            for _, row in merged.iterrows()
        ]
    else:
        merged["day_trading_ratio"] = np.nan
        merged["chip_pattern"] = [_classify_chip_pattern(row, 0.0) for _, row in merged.iterrows()]

    return merged.sort_values("date").reset_index(drop=True), stock_name
