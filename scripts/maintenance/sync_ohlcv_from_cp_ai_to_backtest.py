#!/usr/bin/env python3
"""
One-off sync: export incremental OHLCV from cp_ai to CSV and upsert into cp_backtest_h.

Steps
- Find latest timestamp present in cp_backtest_h.ohlcv_1h_250_coins
- Pull rows from cp_ai.ohlcv_1h_250_coins where timestamp > latest_ts (or last 3 days if latest_ts is NULL)
- Save to csv_output/ohlcv_incremental_<start>_<end>.csv
- Insert into cp_backtest_h with ON CONFLICT (slug,timestamp) DO NOTHING via temp table

Requires env vars in .env: DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME (cp_ai), DB_NAME_BT (cp_backtest_h)
"""

import os
from datetime import datetime, timedelta, timezone
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv


def engine_for(db_name: str):
    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    pw = os.getenv("DB_PASSWORD")
    port = os.getenv("DB_PORT", "5432")
    if not host or not user or not pw:
        raise SystemExit("Missing DB_HOST/DB_USER/DB_PASSWORD in environment")
    return create_engine(f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db_name}")


def remove_duplicates(engine, table_name: str, key_columns: list):
    """Remove duplicate rows, keeping only the first occurrence (by ID)."""
    col_list = ", ".join(key_columns)
    with engine.begin() as conn:
        # Find duplicates
        dup_result = conn.execute(text(f"""
            SELECT {col_list}, COUNT(*) as dup_count
            FROM {table_name}
            GROUP BY {col_list}
            HAVING COUNT(*) > 1
        """)).fetchall()

        if not dup_result:
            print(f"[OK] No duplicates found in {table_name}")
            return 0

        dup_count = len(dup_result)
        print(f"[WARN] Found {dup_count} duplicate (slug, timestamp) pairs in {table_name}")

        # Remove duplicates: keep row with lowest ID (first inserted), delete others
        delete_result = conn.execute(text(f"""
            DELETE FROM {table_name}
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM {table_name}
                GROUP BY {col_list}
            )
        """))

        deleted_rows = delete_result.rowcount if delete_result.rowcount is not None else 0
        print(f"[OK] Removed {deleted_rows} duplicate rows from {table_name}")
        return deleted_rows


def main():
    load_dotenv()
    db_ai = os.getenv("DB_NAME", "cp_ai")
    db_bt = os.getenv("DB_NAME_BT", "cp_backtest_h")

    eng_ai = engine_for(db_ai)
    eng_bt = engine_for(db_bt)

    # Determine latest backtest timestamp
    with eng_bt.connect() as con_bt:
        latest = pd.read_sql("SELECT MAX(timestamp) AS latest_ts FROM ohlcv_1h_250_coins", con_bt, parse_dates=["latest_ts"]) ["latest_ts"].iloc[0]

    # Define incremental window
    if pd.isna(latest):
        end_dt = datetime.now(timezone.utc).replace(minute=59, second=59, microsecond=0)
        start_dt = end_dt - timedelta(days=3)
    else:
        start_dt = latest + timedelta(seconds=1)
        end_dt = datetime.now(timezone.utc).replace(minute=59, second=59, microsecond=0)

    if start_dt >= end_dt:
        print("[OK] Nothing to sync: backtest already up-to-date")
        # Still check for duplicates even if no new data
        print("\nRunning duplicate cleanup check...")
        remove_duplicates(eng_bt, "ohlcv_1h_250_coins", ["slug", "timestamp"])
        return

    print(f"Sync window: {start_dt} -> {end_dt}")

    # Pull incremental from cp_ai
    q = text(
        """
        SELECT id, slug, name, symbol, timestamp, open, high, low, close, volume, market_cap
        FROM ohlcv_1h_250_coins
        WHERE timestamp > :s AND timestamp <= :e
        ORDER BY timestamp, slug
        """
    )
    with eng_ai.connect() as con_ai:
        df = pd.read_sql(q, con_ai, params={"s": start_dt, "e": end_dt}, parse_dates=["timestamp"])

    if df.empty:
        print("[OK] No incremental rows in cp_ai for the window")
        # Still check for duplicates even if no new data
        print("\nRunning duplicate cleanup check...")
        remove_duplicates(eng_bt, "ohlcv_1h_250_coins", ["slug", "timestamp"])
        return

    # Export to CSV for audit
    os.makedirs("csv_output", exist_ok=True)
    csv_name = f"csv_output/ohlcv_incremental_{start_dt.strftime('%Y%m%d%H%M%S')}_{end_dt.strftime('%Y%m%d%H%M%S')}.csv"
    df.to_csv(csv_name, index=False)
    print(f"[OK] Exported {len(df)} rows to {csv_name}")

    # Upsert into backtest via temp table and ON CONFLICT DO NOTHING
    tmp = f"ohlcv_1h_250_coins_tmp_{int(datetime.now().timestamp())}"
    with eng_bt.begin() as con_bt:
        df.to_sql(tmp, con_bt, if_exists="replace", index=False)
        ins = text(
            f"""
            INSERT INTO ohlcv_1h_250_coins (id, slug, name, symbol, timestamp, open, high, low, close, volume, market_cap)
            SELECT id, slug, name, symbol, timestamp, open, high, low, close, volume, market_cap
            FROM "{tmp}"
            ON CONFLICT (slug, timestamp) DO NOTHING
            """
        )
        res = con_bt.execute(ins)
        con_bt.execute(text(f'DROP TABLE "{tmp}"'))
        print(f"[OK] Inserted {res.rowcount if res.rowcount is not None else 0} new rows into cp_backtest_h")

    # Run duplicate cleanup after sync
    print("\nRunning post-sync duplicate cleanup check...")
    remove_duplicates(eng_bt, "ohlcv_1h_250_coins", ["slug", "timestamp"])


if __name__ == "__main__":
    main()
