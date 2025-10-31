#!/usr/bin/env python3
"""
Check OHLCV Date Coverage in cp_ai

This script checks what dates are available in the source ohlcv_1h_250_coins table
to understand if DMV_ALL gaps are due to missing source data.
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
DB_NAME = os.getenv("DB_NAME", "cp_ai")

engine = create_engine(f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}')

print("\n" + "="*80)
print("OHLCV DATE COVERAGE IN cp_ai")
print("="*80)

# Check date range and coverage in OHLCV table
query = """
SELECT
    timestamp::date as date,
    COUNT(*) as records_per_day,
    COUNT(DISTINCT slug) as unique_coins
FROM ohlcv_1h_250_coins
GROUP BY timestamp::date
ORDER BY date
"""

df = pd.read_sql(query, con=engine)

if len(df) > 0:
    print(f"\n✅ Found OHLCV data for {len(df)} unique days")
    print(f"   Date Range: {df['date'].min()} → {df['date'].max()}")
    print(f"\n   First 10 days:")
    print(df.head(10).to_string(index=False))
    print(f"\n   Last 10 days:")
    print(df.tail(10).to_string(index=False))

    # Check for gaps in OHLCV data
    print("\n" + "="*80)
    print("CHECKING FOR GAPS IN OHLCV DATA")
    print("="*80)

    min_date = pd.to_datetime(df['date'].min())
    max_date = pd.to_datetime(df['date'].max())
    expected_dates = pd.date_range(start=min_date, end=max_date, freq='D')
    actual_dates = pd.to_datetime(df['date'])

    missing_dates = set(expected_dates) - set(actual_dates)
    missing_dates_sorted = sorted(missing_dates)

    if missing_dates_sorted:
        print(f"\n❌ Found {len(missing_dates_sorted)} days with NO OHLCV data:")
        for date in missing_dates_sorted[:20]:  # Show first 20
            print(f"   - {date.date()}")
        if len(missing_dates_sorted) > 20:
            print(f"   ... and {len(missing_dates_sorted) - 20} more")
    else:
        print(f"\n✅ NO GAPS: OHLCV data is continuous from {min_date.date()} to {max_date.date()}")
else:
    print("\n❌ No OHLCV data found in cp_ai")

engine.dispose()

print("\n" + "="*80 + "\n")
