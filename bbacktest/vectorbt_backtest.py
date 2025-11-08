#!/usr/bin/env python3
"""
Vectorbt backtest against cp_backtest_h (strict mode).

- Uses ONLY the backtest database (cp_backtest_h by default).
- No fallbacks to other DBs or CSV files.
- Provides CLI flags for date range and DB name.
- Errors out with clear guidance if data is missing.
"""

import os
import sys
import argparse
import warnings
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
from dotenv import load_dotenv

warnings.filterwarnings("ignore")


def get_engine(db_name: str | None = None):
    load_dotenv()
    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    pw = os.getenv("DB_PASSWORD")
    port = os.getenv("DB_PORT", "5432")
    db = db_name or os.getenv("DB_NAME_BT", "cp_backtest_h")
    if not host or not user or not pw:
        raise SystemExit("[ERROR] Missing DB_HOST/DB_USER/DB_PASSWORD in environment")
    return create_engine(f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}")


def table_exists(engine, table_name: str, schema: str = "public") -> bool:
    try:
        q = (
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema=:s AND table_name=:t LIMIT 1"
        )
        with engine.connect() as con:
            res = con.execute(text(q), {"s": schema, "t": table_name})
            row = res.first()
            return row is not None
    except Exception:
        return False


def load_data(engine_bt, start, end, prices_table: str, signals_table: str):
    """Load prices and DMV signals strictly from cp_backtest_h (no fallbacks)."""
    if not table_exists(engine_bt, prices_table):
        raise SystemExit(f"[ERROR] Prices table '{prices_table}' not found in backtest DB")
    if not table_exists(engine_bt, signals_table):
        raise SystemExit(f"[ERROR] Signals table '{signals_table}' not found in backtest DB")

    px = pd.read_sql(
        f"""
        SELECT timestamp, slug, close
        FROM {prices_table}
        WHERE timestamp >= %(s)s AND timestamp < %(e)s
        """,
        engine_bt,
        params={"s": start, "e": end},
        parse_dates=["timestamp"],
    )

    dmv = pd.read_sql(
        f"""
        SELECT timestamp, slug, bullish, bearish
        FROM "{signals_table}"
        WHERE timestamp >= %(s)s AND timestamp < %(e)s
        """,
        engine_bt,
        params={"s": start, "e": end},
        parse_dates=["timestamp"],
    )

    close = px.pivot(index="timestamp", columns="slug", values="close").sort_index()
    bullish = dmv.pivot(index="timestamp", columns="slug", values="bullish").reindex(close.index).fillna(0)
    bearish = dmv.pivot(index="timestamp", columns="slug", values="bearish").reindex(close.index).fillna(0)

    # Keep only coins that exist in both price and signal frames
    common_cols = close.columns.intersection(bullish.columns).intersection(bearish.columns)
    close = close[common_cols]
    bullish = bullish[common_cols]
    bearish = bearish[common_cols]

    return close, bullish, bearish


def print_available_ranges(engine_bt, prices_table: str, signals_table: str) -> None:
    def summarize(table, date_col='timestamp'):
        if not table_exists(engine_bt, table):
            return f"- {table}: [MISSING]"
        q = f"SELECT MIN({date_col}::date) AS min_date, MAX({date_col}::date) AS max_date, COUNT(DISTINCT {date_col}::date) AS days FROM \"{table}\""
        try:
            df = pd.read_sql(q, engine_bt)
            if df.empty:
                return f"- {table}: [EMPTY]"
            min_date = df['min_date'].iloc[0]
            max_date = df['max_date'].iloc[0]
            days = df['days'].iloc[0]
            return f"- {table}: {min_date} -> {max_date} ({days} days)"
        except Exception as e:
            return f"- {table}: [ERROR] {str(e)[:120]}"

    print("\n== AVAILABLE RANGES (Backtest DB) ==")
    print(summarize(prices_table))
    print(summarize(signals_table))


def run_vectorbt(close, bullish, bearish):
    try:
        import vectorbt as vbt  # type: ignore
    except Exception:
        print("[ERROR] vectorbt is not installed. Run: pip install vectorbt")
        return None

    entries = bullish >= 3
    exits = (bullish == 0) | (bearish <= -2)

    pf = vbt.Portfolio.from_signals(
        close,
        entries,
        exits,
        init_cash=100_000,
        fees=0.001,
        slippage=0.0005,
        cash_sharing=True,
        freq="1h",
    )
    return pf


def parse_args():
    p = argparse.ArgumentParser(description="Vectorbt backtest against cp_backtest_h (strict)")
    p.add_argument("--start", type=str, help="UTC start datetime YYYY-MM-DD[ HH:MM:SS]")
    p.add_argument("--end", type=str, help="UTC end datetime YYYY-MM-DD[ HH:MM:SS]")
    p.add_argument("--days", type=int, default=int(os.getenv("BBACKTEST_DAYS", "14")), help="If no start/end, use last N days")
    p.add_argument("--db-name", type=str, default=os.getenv("DB_NAME_BT", "cp_backtest_h"), help="Backtest DB name (default from env)")
    p.add_argument("--prices-table", type=str, default="ohlcv_1h_250_coins", help="Prices table name")
    p.add_argument("--signals-table", type=str, default="FE_DMV_ALL", help="Signals table name")
    p.add_argument("--list-ranges", action="store_true", help="List available date ranges and exit")
    return p.parse_args()


def main():
    args = parse_args()

    # Window from args
    if args.start and args.end:
        start_dt = pd.to_datetime(args.start, utc=False)
        end_dt = pd.to_datetime(args.end, utc=False)
    else:
        end_dt = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        start_dt = end_dt - timedelta(days=args.days)
    start = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    end = end_dt.strftime("%Y-%m-%d %H:%M:%S")

    print("\n== BBACKTEST: SETUP ==")
    print(f"Window: {start} -> {end} (UTC)")
    print(f"DB: {args.db_name} | prices={args.prices_table} | signals={args.signals_table}")
    engine = get_engine(args.db_name)

    if args.list_ranges:
        print_available_ranges(engine, args.prices_table, args.signals_table)
        sys.exit(0)

    print("\n== BBACKTEST: LOADING DATA ==")
    close, bullish, bearish = load_data(engine, start, end, args.prices_table, args.signals_table)
    print(f"Prices shape: {close.shape}")
    print(f"Signals shape: bullish={bullish.shape}, bearish={bearish.shape}")

    if close.empty:
        print("[ERROR] No price data in the selected window.")
        print_available_ranges(engine, args.prices_table, args.signals_table)
        sys.exit(1)
    if bullish.empty or bearish.empty:
        print("[ERROR] No DMV signals in the selected window.")
        print_available_ranges(engine, args.prices_table, args.signals_table)
        sys.exit(1)

    # Drop thin columns to avoid noisy demo
    nonnan_cols = close.columns[close.notna().sum() > 20]
    close = close[nonnan_cols]
    bullish = bullish.reindex(columns=nonnan_cols, fill_value=0)
    bearish = bearish.reindex(columns=nonnan_cols, fill_value=0)
    print(f"Filtered to columns with data: {len(nonnan_cols)} assets")

    print("\n== BBACKTEST: RUN (vectorbt) ==")
    pf = run_vectorbt(close, bullish, bearish)
    if pf is None:
        sys.exit(1)

    print("\n== BBACKTEST: STATS ==")
    print(pf.stats())


if __name__ == "__main__":
    main()
