#!/usr/bin/env python3
import os
import psycopg2
from dotenv import load_dotenv

if not os.getenv("GITHUB_ACTIONS"):
    load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    database=os.getenv("DB_NAME_BT", "cp_backtest_h"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    port=os.getenv("DB_PORT", "5432")
)

cursor = conn.cursor()

# Check signal table counts for Oct 1-14
tables = [
    "FE_TVV_SIGNALS",
    "FE_OSCILLATORS_SIGNALS",
    "FE_MOMENTUM_SIGNALS",
    "FE_RATIOS_SIGNALS",
    "FE_DMV_ALL"
]

print("=" * 80)
print("DATA STATUS FOR OCT 1-14, 2025")
print("=" * 80)

for table in tables:
    try:
        cursor.execute(f"""
            SELECT
                COUNT(*) as total,
                COUNT(DISTINCT timestamp)::int as timestamps,
                MIN(timestamp) as min_ts,
                MAX(timestamp) as max_ts
            FROM "{table}"
            WHERE timestamp >= '2025-10-01'::date
              AND timestamp < '2025-10-15'::date
        """)
        result = cursor.fetchone()
        if result:
            total, timestamps, min_ts, max_ts = result
            print(f"\n{table}:")
            print(f"  Records: {total:,}")
            print(f"  Timestamps: {timestamps}")
            if min_ts and max_ts:
                print(f"  Range: {min_ts} to {max_ts}")
    except Exception as e:
        print(f"\n{table}: ERROR - {e}")

conn.close()
