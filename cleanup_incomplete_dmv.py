#!/usr/bin/env python3
"""
Cleanup Incomplete DMV Data in cp_backtest_h

This script deletes the incomplete Oct 31-only data from FE_DMV_ALL and FE_DMV_SCORES
in cp_backtest_h before we re-run the backfill with fixed scripts.

Background:
- Original Script 3 (backfill_dmv_core.py) ran and only loaded 199-200 records from cp_ai
- This is because cp_ai only has current data (Oct 26-31)
- We need to delete this incomplete data before running Script 3b which reads from cp_backtest_h
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
print("CLEANUP: REMOVING INCOMPLETE DMV DATA")
print("="*80)

# Check what we have before deletion
print("\nBEFORE CLEANUP:")
print("-"*80)

with engine.connect() as conn:
    # Check FE_DMV_ALL
    query1 = """
    SELECT
        MIN(timestamp::date) as min_date,
        MAX(timestamp::date) as max_date,
        COUNT(*) as total_records,
        COUNT(DISTINCT timestamp::date) as unique_days
    FROM "FE_DMV_ALL"
    """
    df1 = pd.read_sql(query1, conn)
    print(f"\nFE_DMV_ALL:")
    print(f"   Date Range: {df1['min_date'].iloc[0]} → {df1['max_date'].iloc[0]}")
    print(f"   Total Records: {df1['total_records'].iloc[0]:,}")
    print(f"   Unique Days: {df1['unique_days'].iloc[0]}")

    # Check FE_DMV_SCORES
    query2 = """
    SELECT COUNT(*) as total_records
    FROM "FE_DMV_SCORES"
    """
    df2 = pd.read_sql(query2, conn)
    print(f"\nFE_DMV_SCORES:")
    print(f"   Total Records: {df2['total_records'].iloc[0]:,}")

# Delete data
print("\n" + "="*80)
print("DELETING INCOMPLETE DATA...")
print("="*80)

with engine.begin() as conn:
    # Delete all DMV_ALL data
    result1 = conn.execute(text('DELETE FROM "FE_DMV_ALL"'))
    print(f"\n✅ Deleted {result1.rowcount:,} records from FE_DMV_ALL")

    # Delete all DMV_SCORES data
    result2 = conn.execute(text('DELETE FROM "FE_DMV_SCORES"'))
    print(f"✅ Deleted {result2.rowcount:,} records from FE_DMV_SCORES")

# Verify deletion
print("\n" + "="*80)
print("AFTER CLEANUP:")
print("="*80)

with engine.connect() as conn:
    query3 = """SELECT COUNT(*) as total FROM "FE_DMV_ALL" """
    df3 = pd.read_sql(query3, conn)
    print(f"\nFE_DMV_ALL: {df3['total'].iloc[0]} records (should be 0)")

    query4 = """SELECT COUNT(*) as total FROM "FE_DMV_SCORES" """
    df4 = pd.read_sql(query4, conn)
    print(f"FE_DMV_SCORES: {df4['total'].iloc[0]} records (should be 0)")

print("\n" + "="*80)
print("✅ CLEANUP COMPLETE")
print("="*80)
print("\nNext Steps:")
print("1. Re-run Script 1: backfill_dmv_tvv_pct.py")
print("2. Re-run Script 2: backfill_dmv_osc_mom_rat.py")
print("3. Run Script 3b: backfill_dmv_core_historical.py (NEW)")
print("4. Validate: python validate_backfill.py")

engine.dispose()
