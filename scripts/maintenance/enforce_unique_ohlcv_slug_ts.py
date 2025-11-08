#!/usr/bin/env python3
"""
Enforce uniqueness on (slug, timestamp) for cp_backtest_h.ohlcv_1h_250_coins.

Steps:
- Connect to cp_backtest_h using env vars (.env at repo root).
- Remove duplicate rows keeping the first occurrence.
- Add a UNIQUE constraint on (slug, timestamp) if absent.

Run:
  python scripts/maintenance/enforce_unique_ohlcv_slug_ts.py
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def main():
    load_dotenv()
    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    pw = os.getenv("DB_PASSWORD")
    port = os.getenv("DB_PORT", "5432")
    db = os.getenv("DB_NAME_BT", "cp_backtest_h")
    if not host or not user or not pw:
        raise SystemExit("[ERROR] Missing DB_HOST/DB_USER/DB_PASSWORD in env")
    eng = create_engine(f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}")

    with eng.begin() as con:
        # Remove duplicates, keep first by ctid order
        con.execute(text(
            """
            WITH d AS (
              SELECT ctid, ROW_NUMBER() OVER (PARTITION BY slug, timestamp ORDER BY ctid) rn
              FROM ohlcv_1h_250_coins
            )
            DELETE FROM ohlcv_1h_250_coins t
            USING d
            WHERE t.ctid = d.ctid AND d.rn > 1;
            """
        ))

        # Add unique constraint if missing
        con.execute(text(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE c.contype = 'u'
                  AND c.conname = 'ohlcv_1h_250_coins_slug_ts_uniq'
              ) THEN
                ALTER TABLE public.ohlcv_1h_250_coins
                  ADD CONSTRAINT ohlcv_1h_250_coins_slug_ts_uniq UNIQUE (slug, timestamp);
              END IF;
            END$$;
            """
        ))

        # Helpful indexes (idempotent)
        con.execute(text("CREATE INDEX IF NOT EXISTS idx_ohlcv_ts ON ohlcv_1h_250_coins (timestamp)"))
        con.execute(text("CREATE INDEX IF NOT EXISTS idx_ohlcv_slug ON ohlcv_1h_250_coins (slug)"))

    print("[OK] Uniqueness enforced on (slug, timestamp) and indexes ensured")


if __name__ == "__main__":
    main()

