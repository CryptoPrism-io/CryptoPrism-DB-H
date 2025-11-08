#!/usr/bin/env python3
"""Quick duplicate check on main tables."""

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

if not os.getenv("GITHUB_ACTIONS"):
    load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT", "5432")

engine = create_engine(f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/cp_backtest_h')

print("=" * 100)
print("QUICK DUPLICATE CHECK: cp_backtest_h")
print("=" * 100)

# Main tables to check
tables = [
    "ohlcv_1h_250_coins",
    "fe_tvv_signals",
    "fe_oscillators_signals",
    "fe_momentum_signals",
    "fe_ratios_signals",
    "fe_dmv_all",
    "fe_dmv_scores"
]

total_dups = 0

with engine.connect() as conn:
    for table in tables:
        try:
            result = conn.execute(text(f'''
                SELECT COUNT(*) FROM (
                    SELECT slug, timestamp, COUNT(*)
                    FROM "{table}"
                    GROUP BY slug, timestamp
                    HAVING COUNT(*) > 1
                ) x
            ''')).scalar()

            if result and result > 0:
                print(f"❌ {table:30s}: {result} duplicate pairs")
                total_dups += result
            else:
                print(f"✅ {table:30s}: No duplicates")
        except Exception as e:
            print(f"⏭️  {table:30s}: {str(e)[:50]}")

print("\n" + "=" * 100)
if total_dups == 0:
    print("✅ NO DUPLICATES FOUND")
else:
    print(f"❌ TOTAL DUPLICATES: {total_dups}")
print("=" * 100)

engine.dispose()
