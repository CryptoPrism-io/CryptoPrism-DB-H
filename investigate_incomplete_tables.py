#!/usr/bin/env python3
"""
Investigate Incomplete Tables
1. FE_RATIOS_SIGNALS - why starts March 12
2. FE_DMV_ALL - why only Oct 31
3. FE_DMV_SCORES - schema issue
"""

import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME_BT = os.getenv("DB_NAME_BT", "cp_backtest_h")

engine = create_engine(f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME_BT}')

print("\n" + "="*80)
print("INVESTIGATION: INCOMPLETE TABLES")
print("="*80)

# ============================================================================
# 1. FE_RATIOS_SIGNALS - Missing Feb 13 to March 11
# ============================================================================
print("\n" + "="*80)
print("1. FE_RATIOS_SIGNALS - Missing Feb 13 to March 11")
print("="*80)

query = """
SELECT
    MIN(timestamp::date) as min_date,
    MAX(timestamp::date) as max_date,
    COUNT(*) as total_records,
    COUNT(DISTINCT slug) as unique_coins,
    COUNT(DISTINCT timestamp::date) as unique_days
FROM "FE_RATIOS_SIGNALS"
WHERE timestamp::date < '2025-03-12'
"""

df = pd.read_sql(query, con=engine)
print(f"\nData BEFORE March 12:")
print(f"   Records: {df['total_records'].iloc[0]:,}")
print(f"   Min Date: {df['min_date'].iloc[0]}")

# Check what data exists in other tables for that period
query2 = """
SELECT
    MIN(timestamp::date) as min_date,
    MAX(timestamp::date) as max_date,
    COUNT(*) as total_records
FROM "FE_MOMENTUM_SIGNALS"
WHERE timestamp::date >= '2025-02-13' AND timestamp::date < '2025-03-12'
"""

df2 = pd.read_sql(query2, con=engine)
print(f"\nFE_MOMENTUM_SIGNALS for Feb 13 - March 11:")
print(f"   Records: {df2['total_records'].iloc[0]:,}")
print(f"   Date Range: {df2['min_date'].iloc[0]} → {df2['max_date'].iloc[0]}")

print("\n💡 DIAGNOSIS:")
print("   FE_RATIOS_SIGNALS is missing Feb 13 - March 11 data")
print("   Other signal tables (MOMENTUM, OSCILLATORS) have this period")
print("   Likely cause: Ratios calculation requires lookback period")
print("   OR: Script 2 backfill didn't process ratios for this period")

# ============================================================================
# 2. FE_DMV_ALL - Only has Oct 31
# ============================================================================
print("\n" + "="*80)
print("2. FE_DMV_ALL - Only has Oct 31 data")
print("="*80)

query3 = """
SELECT
    timestamp::date as date,
    COUNT(*) as records,
    COUNT(DISTINCT slug) as coins
FROM "FE_DMV_ALL"
GROUP BY timestamp::date
ORDER BY date DESC
LIMIT 10
"""

df3 = pd.read_sql(query3, con=engine)
print(f"\nRecent dates in FE_DMV_ALL:")
print(df3.to_string(index=False))

query4 = """
SELECT COUNT(*) as total FROM "FE_DMV_ALL"
"""
df4 = pd.read_sql(query4, con=engine)
print(f"\nTotal records in FE_DMV_ALL: {df4['total'].iloc[0]:,}")

print("\n💡 DIAGNOSIS:")
print("   FE_DMV_ALL only has Oct 31 data (200 records)")
print("   Cause: Script 3 (DMV Core) ran 9.5 hours after R script")
print("   By that time, cp_ai had been overwritten by hourly cron")
print("   Script 3 read from cp_ai which only had Oct 31 data")
print("\n   FIX NEEDED:")
print("   - Script 3 should read signal tables from cp_backtest_h (not cp_ai)")
print("   - Then aggregate historical data and append to cp_backtest_h")

# ============================================================================
# 3. FE_DMV_SCORES - Schema Issue
# ============================================================================
print("\n" + "="*80)
print("3. FE_DMV_SCORES - Schema Investigation")
print("="*80)

# Check if table exists
query5 = """
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'FE_DMV_SCORES'
ORDER BY ordinal_position
"""

try:
    df5 = pd.read_sql(query5, con=engine)
    if len(df5) > 0:
        print(f"\nFE_DMV_SCORES columns:")
        print(df5.to_string(index=False))

        # Count records
        query6 = """SELECT COUNT(*) as total FROM "FE_DMV_SCORES" """
        df6 = pd.read_sql(query6, con=engine)
        print(f"\nTotal records: {df6['total'].iloc[0]:,}")

        # Check if timestamp column exists
        if 'timestamp' not in df5['column_name'].values:
            print("\n💡 DIAGNOSIS:")
            print("   FE_DMV_SCORES table exists but has NO 'timestamp' column")
            print("   This is a schema issue - validation script expected timestamp column")
            print("\n   Columns present:", df5['column_name'].tolist())
    else:
        print("❌ Table FE_DMV_SCORES not found")
except Exception as e:
    print(f"❌ Error: {str(e)}")

print("\n" + "="*80)
print("SUMMARY OF ISSUES")
print("="*80)
print("""
1. FE_RATIOS_SIGNALS:
   - Missing: Feb 13 - March 11 (27 days)
   - Has: March 12 - Oct 30
   - Fix: Need to backfill earlier period (if possible with lookback requirements)

2. FE_DMV_ALL:
   - Has: ONLY Oct 31 (200 records)
   - Missing: Feb 13 - Oct 30 (260 days)
   - Fix: Re-run Script 3 reading from cp_backtest_h signal tables

3. FE_DMV_SCORES:
   - Schema doesn't have 'timestamp' column
   - Need to check actual column structure
""")

engine.dispose()
