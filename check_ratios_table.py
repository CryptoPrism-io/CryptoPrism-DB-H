#!/usr/bin/env python3
"""
Check if FE_RATIOS table exists in cp_backtest_h
"""

import pandas as pd
from sqlalchemy import create_engine
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
print("CHECKING FE_RATIOS TABLE IN cp_backtest_h")
print("="*80)

# Check if table exists
query_check = """
SELECT EXISTS (
   SELECT FROM information_schema.tables
   WHERE table_schema = 'public'
   AND table_name = 'FE_RATIOS'
);
"""

exists = pd.read_sql(query_check, con=engine)['exists'].iloc[0]

if exists:
    print("\n✅ FE_RATIOS table EXISTS")

    # Get table info
    query = """
    SELECT
        MIN(timestamp::date) as min_date,
        MAX(timestamp::date) as max_date,
        COUNT(*) as total_records,
        COUNT(DISTINCT slug) as unique_coins,
        COUNT(DISTINCT timestamp::date) as unique_days
    FROM "FE_RATIOS"
    """

    df = pd.read_sql(query, con=engine)
    print(f"\n   Date Range: {df['min_date'].iloc[0]} → {df['max_date'].iloc[0]}")
    print(f"   Total Records: {df['total_records'].iloc[0]:,}")
    print(f"   Unique Coins: {df['unique_coins'].iloc[0]}")
    print(f"   Unique Days: {df['unique_days'].iloc[0]}")
else:
    print("\n❌ FE_RATIOS table does NOT exist")
    print("   Expected: Script 2 should have written both FE_RATIOS and FE_RATIOS_SIGNALS")

# Also check FE_RATIOS_SIGNALS for comparison
print("\n" + "-"*80)
print("FE_RATIOS_SIGNALS (for comparison):")
print("-"*80)

query2 = """
SELECT
    MIN(timestamp::date) as min_date,
    MAX(timestamp::date) as max_date,
    COUNT(*) as total_records,
    COUNT(DISTINCT slug) as unique_coins,
    COUNT(DISTINCT timestamp::date) as unique_days
FROM "FE_RATIOS_SIGNALS"
"""

df2 = pd.read_sql(query2, con=engine)
print(f"   Date Range: {df2['min_date'].iloc[0]} → {df2['max_date'].iloc[0]}")
print(f"   Total Records: {df2['total_records'].iloc[0]:,}")
print(f"   Unique Coins: {df2['unique_coins'].iloc[0]}")
print(f"   Unique Days: {df2['unique_days'].iloc[0]}")

print("\n" + "="*80 + "\n")

engine.dispose()
