#!/usr/bin/env python3
import psycopg2
import os
from dotenv import load_dotenv

# Load environment variables
if not os.getenv("GITHUB_ACTIONS"):
    load_dotenv()

print("=" * 80)
print("DELETING OCT 1-14 SIGNAL DATA")
print("=" * 80)

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    database=os.getenv("DB_NAME_BT", "cp_backtest_h"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    port=os.getenv("DB_PORT", "5432")
)

cursor = conn.cursor()
tables = [
    "FE_TVV_SIGNALS",
    "FE_OSCILLATORS_SIGNALS",
    "FE_MOMENTUM_SIGNALS",
    "FE_RATIOS_SIGNALS",
    "FE_DMV_ALL",
    "FE_DMV_SCORES"
]

for table in tables:
    try:
        cursor.execute(f"""
            DELETE FROM "{table}"
            WHERE timestamp >= '2025-10-01'::date
              AND timestamp < '2025-10-15'::date
        """)
        deleted = cursor.rowcount
        print(f"✅ {table}: Deleted {deleted:,} records")
    except Exception as e:
        print(f"❌ {table}: {e}")

conn.commit()
conn.close()
print("\n" + "=" * 80)
print("DELETION COMPLETE")
print("=" * 80)
