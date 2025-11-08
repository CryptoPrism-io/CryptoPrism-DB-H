#!/usr/bin/env python3
"""
Validate Backfill Completion
Checks cp_backtest_h for continuous data from Feb 13 - Oct 30, 2025
"""

import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta

# Load environment
load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME_BT = os.getenv("DB_NAME_BT", "cp_backtest_h")

# Create engine
engine = create_engine(f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME_BT}')

print("\n" + "="*80)
print("BACKFILL VALIDATION REPORT")
print("="*80)

# Tables to check
tables = [
    'FE_TVV',
    'FE_TVV_SIGNALS',
    'FE_PCT_CHANGE',
    'FE_OSCILLATORS_SIGNALS',
    'FE_MOMENTUM_SIGNALS',
    'FE_RATIOS_SIGNALS',
    'FE_DMV_ALL',
    'FE_DMV_SCORES'
]

target_start = '2025-02-13'
target_end = '2025-10-30'

print(f"\nTarget Date Range: {target_start} to {target_end}")
print("="*80)

for table in tables:
    print(f"\n📊 {table}:")
    print("-" * 60)

    # Get date range and record count
    query = f"""
    SELECT
        MIN(timestamp::date) as min_date,
        MAX(timestamp::date) as max_date,
        COUNT(*) as total_records,
        COUNT(DISTINCT slug) as unique_coins,
        COUNT(DISTINCT timestamp::date) as unique_days
    FROM "{table}"
    """

    try:
        df = pd.read_sql(query, con=engine)

        if len(df) > 0:
            min_date = df['min_date'].iloc[0]
            max_date = df['max_date'].iloc[0]
            total_records = df['total_records'].iloc[0]
            unique_coins = df['unique_coins'].iloc[0]
            unique_days = df['unique_days'].iloc[0]

            print(f"   Date Range: {min_date} → {max_date}")
            print(f"   Total Records: {total_records:,}")
            print(f"   Unique Coins: {unique_coins}")
            print(f"   Unique Days: {unique_days}")

            # Check if target range is covered
            target_start_dt = datetime.strptime(target_start, '%Y-%m-%d').date()
            target_end_dt = datetime.strptime(target_end, '%Y-%m-%d').date()

            if min_date <= target_start_dt and max_date >= target_end_dt:
                print(f"   ✅ PASS: Covers target range {target_start} to {target_end}")
            else:
                print(f"   ❌ FAIL: Does not cover full target range")
                if min_date > target_start_dt:
                    print(f"      Missing start: {target_start} to {min_date}")
                if max_date < target_end_dt:
                    print(f"      Missing end: {max_date} to {target_end}")
        else:
            print("   ❌ FAIL: No data found")

    except Exception as e:
        print(f"   ❌ ERROR: {str(e)}")

# Check for gaps
print("\n" + "="*80)
print("GAP ANALYSIS (FE_DMV_ALL)")
print("="*80)

gap_query = """
WITH date_series AS (
    SELECT generate_series(
        '2025-02-13'::date,
        '2025-10-30'::date,
        '1 day'::interval
    )::date AS expected_date
),
actual_dates AS (
    SELECT DISTINCT timestamp::date AS actual_date
    FROM "FE_DMV_ALL"
)
SELECT
    ds.expected_date,
    CASE WHEN ad.actual_date IS NULL THEN 'MISSING' ELSE 'PRESENT' END as status
FROM date_series ds
LEFT JOIN actual_dates ad ON ds.expected_date = ad.actual_date
WHERE ad.actual_date IS NULL
ORDER BY ds.expected_date
"""

try:
    gaps = pd.read_sql(gap_query, con=engine)
    if len(gaps) > 0:
        print(f"\n❌ Found {len(gaps)} days with missing data:")
        for idx, row in gaps.iterrows():
            print(f"   - {row['expected_date']}")
    else:
        print("\n✅ No gaps found! Data is continuous from Feb 13 to Oct 30, 2025")
except Exception as e:
    print(f"\n❌ Error checking gaps: {str(e)}")

print("\n" + "="*80)
print("VALIDATION COMPLETE")
print("="*80 + "\n")

engine.dispose()
