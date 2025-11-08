#!/usr/bin/env python3
"""
Create cp_backtest_h.ohlcv_1h_250_coins from FE_OSCILLATOR.

Logic
- Connects to cp_backtest_h via env (.env at repo root).
- Introspects columns in FE_OSCILLATOR and maps available price fields.
- Creates table ohlcv_1h_250_coins if missing, then replaces its contents.
- Adds index on (timestamp, slug) for efficient backtesting.

Usage
  python scripts/maintenance/build_prices_from_fe_oscillator.py [--dry-run]
"""

import os
import sys
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, text


def get_engine():
    load_dotenv()
    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    pw = os.getenv("DB_PASSWORD")
    port = os.getenv("DB_PORT", "5432")
    db = os.getenv("DB_NAME_BT", "cp_backtest_h")
    if not host or not user or not pw:
        raise SystemExit("[ERROR] Missing DB_HOST/DB_USER/DB_PASSWORD in env")
    return create_engine(f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}")


def get_columns(con, table: str) -> set[str]:
    df = pd.read_sql(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=:t
            """
        ),
        con,
        params={"t": table},
    )
    return set(df["column_name"].tolist())


def main():
    dry_run = "--dry-run" in sys.argv
    eng = get_engine()

    with eng.begin() as con:
        cols = get_columns(con, "FE_OSCILLATOR")
        if not cols:
            raise SystemExit("[ERROR] FE_OSCILLATOR not found in cp_backtest_h")

        def pick(*names, required=False):
            for n in names:
                if n in cols:
                    return n
            if required:
                raise SystemExit(f"[ERROR] Required column missing: one of {names}")
            return None

        # Column mapping
        id_col = pick("id")
        slug_col = pick("slug", required=True)
        name_col = pick("name")
        symbol_col = pick("symbol")
        ts_col = pick("timestamp", required=True)
        open_col = pick("open")
        high_col = pick("high")
        low_col = pick("low")
        close_col = pick("close", "price", required=True)
        vol_col = pick("volume", "quote_volume")
        mcap_col = pick("market_cap", "mcap")

        print("Mapping to ohlcv_1h_250_coins:")
        print(f"  id -> {id_col or 'NULL'}")
        print(f"  slug -> {slug_col}")
        print(f"  name -> {name_col or 'NULL'}")
        print(f"  symbol -> {symbol_col or 'NULL'}")
        print(f"  timestamp -> {ts_col}")
        print(f"  open -> {open_col or 'NULL'}")
        print(f"  high -> {high_col or 'NULL'}")
        print(f"  low -> {low_col or 'NULL'}")
        print(f"  close -> {close_col}")
        print(f"  volume -> {vol_col or 'NULL'}")
        print(f"  market_cap -> {mcap_col or 'NULL'}")

        # Build SELECT clause dynamically
        def sel(expr, alias, cast=None):
            if expr is None:
                return f"NULL{('::' + cast) if cast else ''} AS \"{alias}\""
            return f"\"{expr}\" AS \"{alias}\""

        select_sql = \
            f"SELECT {sel(id_col, 'id', 'integer')}, " \
            + f"{sel(slug_col, 'slug')}, " \
            + f"{sel(name_col, 'name')}, " \
            + f"{sel(symbol_col, 'symbol')}, " \
            + f"{sel(ts_col, 'timestamp', 'timestamptz')}, " \
            + f"{sel(open_col, 'open', 'numeric')}, " \
            + f"{sel(high_col, 'high', 'numeric')}, " \
            + f"{sel(low_col, 'low', 'numeric')}, " \
            + f"{sel(close_col, 'close', 'numeric')}, " \
            + f"{sel(vol_col, 'volume', 'numeric')}, " \
            + f"{sel(mcap_col, 'market_cap', 'numeric')} " \
            + "FROM \"FE_OSCILLATOR\""

        # Create destination table
        create_sql = text(
            """
            CREATE TABLE IF NOT EXISTS ohlcv_1h_250_coins (
                id integer,
                slug text NOT NULL,
                name text,
                symbol text,
                timestamp timestamptz NOT NULL,
                open numeric,
                high numeric,
                low numeric,
                close numeric NOT NULL,
                volume numeric,
                market_cap numeric
            );
            """
        )

        if dry_run:
            print("\n[DRY-RUN] Would create table ohlcv_1h_250_coins if missing.")
            print("[DRY-RUN] Would run SELECT as source:\n" + select_sql)
            return

        con.execute(create_sql)
        # Replace contents safely
        con.execute(text("TRUNCATE TABLE ohlcv_1h_250_coins"))
        insert_sql = f"INSERT INTO ohlcv_1h_250_coins {select_sql}"
        con.execute(text(insert_sql))

        # Indexes for performance
        con.execute(text("CREATE INDEX IF NOT EXISTS idx_ohlcv_ts ON ohlcv_1h_250_coins (timestamp)"))
        con.execute(text("CREATE INDEX IF NOT EXISTS idx_ohlcv_slug ON ohlcv_1h_250_coins (slug)"))
        con.execute(text("CREATE INDEX IF NOT EXISTS idx_ohlcv_ts_slug ON ohlcv_1h_250_coins (timestamp, slug)"))

        # Summary
        summary = pd.read_sql(
            text(
                """
                SELECT COUNT(*) AS rows,
                       MIN(timestamp) AS min_ts,
                       MAX(timestamp) AS max_ts,
                       COUNT(DISTINCT slug) AS coins
                FROM ohlcv_1h_250_coins
                """
            ),
            con,
        )
        print("\n[OK] ohlcv_1h_250_coins rebuilt:")
        print(summary.to_string(index=False))


if __name__ == "__main__":
    main()

