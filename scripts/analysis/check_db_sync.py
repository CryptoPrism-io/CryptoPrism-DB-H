#!/usr/bin/env python3
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment
if not os.getenv("GITHUB_ACTIONS"):
    load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT", "5432")

# Connect to both databases
engine_cpai = create_engine(f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/cp_ai')
engine_backtest = create_engine(f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/cp_backtest_h')

print("=" * 80)
print("OHLCV SYNC STATUS - cp_ai vs cp_backtest_h")
print("=" * 80)

# Get stats for both databases
with engine_cpai.connect() as conn:
    result = conn.execute(text("""
        SELECT
            COUNT(*) as total_count,
            MIN(timestamp) as min_ts,
            MAX(timestamp) as max_ts
        FROM ohlcv_1h_250_coins
    """)).fetchone()
    print(f"\ncp_ai (PRIMARY):")
    print(f"  Total records: {result[0]:,}")
    print(f"  Min timestamp: {result[1]}")
    print(f"  Max timestamp: {result[2]}")

with engine_backtest.connect() as conn:
    result = conn.execute(text("""
        SELECT
            COUNT(*) as total_count,
            MIN(timestamp) as min_ts,
            MAX(timestamp) as max_ts
        FROM ohlcv_1h_250_coins
    """)).fetchone()
    print(f"\ncp_backtest_h (ARCHIVE):")
    print(f"  Total records: {result[0]:,}")
    print(f"  Min timestamp: {result[1]}")
    print(f"  Max timestamp: {result[2]}")

# Check Nov data specifically
print(f"\n" + "=" * 80)
print("November Data Sync Details")
print("=" * 80)

with engine_cpai.connect() as conn:
    result = conn.execute(text("""
        SELECT
            DATE(timestamp) as date,
            COUNT(*) as count
        FROM ohlcv_1h_250_coins
        WHERE timestamp >= '2025-11-01'
        GROUP BY DATE(timestamp)
        ORDER BY date
    """)).fetchall()
    print(f"\ncp_ai Nov data:")
    for row in result:
        print(f"  Nov {row[0].day:2d}: {row[1]:5,} rows")

with engine_backtest.connect() as conn:
    result = conn.execute(text("""
        SELECT
            DATE(timestamp) as date,
            COUNT(*) as count
        FROM ohlcv_1h_250_coins
        WHERE timestamp >= '2025-11-01'
        GROUP BY DATE(timestamp)
        ORDER BY date
    """)).fetchall()
    print(f"\ncp_backtest_h Nov data:")
    if not result:
        print("  ❌ NO DATA FOR NOVEMBER!")
    else:
        for row in result:
            print(f"  Nov {row[0].day:2d}: {row[1]:5,} rows")

engine_cpai.dispose()
engine_backtest.dispose()

print("\n" + "=" * 80)
print("SYNC STATUS: ", end="")
with engine_cpai.connect() as conn:
    cp_ai_count = conn.execute(text("SELECT COUNT(*) FROM ohlcv_1h_250_coins WHERE timestamp >= '2025-11-05'")).scalar()
with engine_backtest.connect() as conn:
    cp_backtest_count = conn.execute(text("SELECT COUNT(*) FROM ohlcv_1h_250_coins WHERE timestamp >= '2025-11-05'")).scalar()

if cp_ai_count > 0 and cp_backtest_count == 0:
    print("❌ BROKEN - cp_ai has Nov 5+ data but cp_backtest_h has ZERO")
elif cp_ai_count == cp_backtest_count:
    print("✅ IN SYNC")
else:
    print(f"⚠️ PARTIAL - cp_ai: {cp_ai_count:,}, cp_backtest_h: {cp_backtest_count:,}")
print("=" * 80)
