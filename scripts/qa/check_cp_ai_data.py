#!/usr/bin/env python3
"""
Check cp_ai Current Data State
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
print("CP_AI DATABASE CURRENT STATE")
print("="*80)

# Check OHLCV data
query = """
SELECT
    MIN(timestamp::date) as min_date,
    MAX(timestamp::date) as max_date,
    COUNT(*) as total_records,
    COUNT(DISTINCT slug) as unique_coins
FROM ohlcv_1h_250_coins
"""

df = pd.read_sql(query, con=engine)
print(f"\nohlcv_1h_250_coins:")
print(f"   Date Range: {df['min_date'].iloc[0]} → {df['max_date'].iloc[0]}")
print(f"   Total Records: {df['total_records'].iloc[0]:,}")
print(f"   Unique Coins: {df['unique_coins'].iloc[0]}")

# Check FE_DMV_ALL
query2 = """
SELECT
    MIN(timestamp::date) as min_date,
    MAX(timestamp::date) as max_date,
    COUNT(*) as total_records,
    COUNT(DISTINCT slug) as unique_coins
FROM "FE_DMV_ALL"
"""

df2 = pd.read_sql(query2, con=engine)
print(f"\nFE_DMV_ALL:")
print(f"   Date Range: {df2['min_date'].iloc[0]} → {df2['max_date'].iloc[0]}")
print(f"   Total Records: {df2['total_records'].iloc[0]:,}")
print(f"   Unique Coins: {df2['unique_coins'].iloc[0]}")

print("\n" + "="*80 + "\n")

engine.dispose()
