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

engine = create_engine(f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/cp_backtest_h')

print("=" * 80)
print("CHECKING FOR DUPLICATES: cp_backtest_h.ohlcv_1h_250_coins")
print("=" * 80)

with engine.connect() as conn:
    # Check for duplicates
    result = conn.execute(text("""
        SELECT slug, timestamp, COUNT(*) as duplicate_count
        FROM ohlcv_1h_250_coins
        GROUP BY slug, timestamp
        HAVING COUNT(*) > 1
        ORDER BY duplicate_count DESC, slug, timestamp
        LIMIT 20
    """)).fetchall()

    if not result:
        print("\n✅ NO DUPLICATES FOUND!")
        print("All (slug, timestamp) pairs are unique in cp_backtest_h.ohlcv_1h_250_coins")

        # Show total row count
        total = conn.execute(text("SELECT COUNT(*) FROM ohlcv_1h_250_coins")).scalar()
        unique_pairs = conn.execute(text("""
            SELECT COUNT(*) FROM (
                SELECT DISTINCT slug, timestamp FROM ohlcv_1h_250_coins
            ) t
        """)).scalar()

        print(f"\nTotal rows: {total:,}")
        print(f"Unique (slug, timestamp) pairs: {unique_pairs:,}")

        if total == unique_pairs:
            print("✅ CONFIRMED: Every row is unique!")
    else:
        print(f"\n❌ FOUND {len(result)} DUPLICATE ENTRIES:\n")
        print(f"{'Slug':<30} | {'Timestamp':<30} | {'Count':<5}")
        print("-" * 70)
        for row in result:
            print(f"{row[0]:<30} | {str(row[1]):<30} | {row[2]:<5}")

engine.dispose()
print("\n" + "=" * 80)
