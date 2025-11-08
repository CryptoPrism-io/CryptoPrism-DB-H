#!/usr/bin/env python3
"""
Compare cp_ai vs cp_backtest_h OHLCV sync for last 3 days.

Outputs per-day rows/coins and latest timestamp in each DB.
Exits with non-zero if differences are found.
"""

import os
import sys
from datetime import datetime
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv


def mk_engine(db_name: str):
    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    pw = os.getenv("DB_PASSWORD")
    port = os.getenv("DB_PORT", "5432")
    if not host or not user or not pw:
        raise SystemExit("Missing DB_HOST/DB_USER/DB_PASSWORD")
    return create_engine(f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db_name}")


def daily_counts(con):
    q = """
        SELECT timestamp::date AS day,
               COUNT(*) AS rows,
               COUNT(DISTINCT slug) AS coins
        FROM ohlcv_1h_250_coins
        WHERE timestamp::date >= (CURRENT_DATE - INTERVAL '2 days')
        GROUP BY 1
        ORDER BY 1
    """
    return pd.read_sql(q, con, parse_dates=["day"]).assign(day=lambda d: d["day"].dt.date)


def latest_ts(con):
    q = "SELECT MAX(timestamp) AS latest_ts FROM ohlcv_1h_250_coins"
    df = pd.read_sql(q, con, parse_dates=["latest_ts"]).fillna({"latest_ts": pd.NaT})
    return df["latest_ts"].iloc[0]


def main():
    load_dotenv()
    db_ai = os.getenv("DB_NAME", "cp_ai")
    db_bt = os.getenv("DB_NAME_BT", "cp_backtest_h")

    eng_ai = mk_engine(db_ai)
    eng_bt = mk_engine(db_bt)

    with eng_ai.connect() as con_ai, eng_bt.connect() as con_bt:
        ai_daily = daily_counts(con_ai).rename(columns={"rows": "rows_ai", "coins": "coins_ai"})
        bt_daily = daily_counts(con_bt).rename(columns={"rows": "rows_bt", "coins": "coins_bt"})

        merged = pd.merge(ai_daily, bt_daily, on="day", how="outer").sort_values("day")
        merged = merged.fillna(0)
        merged["rows_ai"] = merged["rows_ai"].astype(int)
        merged["rows_bt"] = merged["rows_bt"].astype(int)
        merged["coins_ai"] = merged["coins_ai"].astype(int)
        merged["coins_bt"] = merged["coins_bt"].astype(int)
        merged["delta_rows"] = merged["rows_ai"] - merged["rows_bt"]
        merged["delta_coins"] = merged["coins_ai"] - merged["coins_bt"]

        ai_latest = latest_ts(con_ai)
        bt_latest = latest_ts(con_bt)

    print("\n== OHLCV Sync Check (last 3 days) ==")
    if not merged.empty:
        print(merged.to_string(index=False))
    else:
        print("No rows found in last 3 days for one or both DBs.")

    print("\nLatest timestamps:")
    print(f"  cp_ai        latest_ts: {ai_latest}")
    print(f"  cp_backtest  latest_ts: {bt_latest}")

    issues = []
    if not merged.empty:
        diffs = merged[(merged["delta_rows"] != 0) | (merged["delta_coins"] != 0)]
        if not diffs.empty:
            issues.append("Per-day counts differ between cp_ai and cp_backtest_h")

    # Consider latest_ts difference > 0 as potential drift
    if pd.notna(ai_latest) and pd.notna(bt_latest) and ai_latest != bt_latest:
        issues.append("Latest timestamp differs between cp_ai and cp_backtest_h")

    if issues:
        print("\n[DIFF] Issues detected:")
        for i in issues:
            print(f" - {i}")
        sys.exit(1)
    else:
        print("\n[OK] cp_ai and cp_backtest_h are in sync for last 3 days and latest timestamp")


if __name__ == "__main__":
    main()

