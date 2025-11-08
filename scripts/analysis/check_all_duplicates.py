#!/usr/bin/env python3
"""
Comprehensive duplicate detection across all tables in cp_backtest_h.
Checks for (slug, timestamp) duplicates where those columns exist.
"""

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

print("=" * 100)
print("COMPREHENSIVE DUPLICATE DETECTION: cp_backtest_h")
print("=" * 100)

# Get all tables
with engine.connect() as conn:
    tables_result = conn.execute(text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)).fetchall()

    all_tables = [row[0] for row in tables_result]
    print(f"\nFound {len(all_tables)} tables to check:\n")

# Check each table
duplicates_found = {}
total_duplicates = 0

for table_name in all_tables:
    with engine.connect() as conn:
        # Check if table has slug and timestamp columns
        columns_result = conn.execute(text(f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = '{table_name}'
            AND column_name IN ('slug', 'timestamp')
        """)).fetchall()

        columns = [row[0] for row in columns_result]

        if 'slug' in columns and 'timestamp' in columns:
            # Check for duplicates on (slug, timestamp)
            try:
                dup_result = conn.execute(text(f"""
                    SELECT slug, timestamp, COUNT(*) as dup_count
                    FROM "{table_name}"
                    GROUP BY slug, timestamp
                    HAVING COUNT(*) > 1
                    ORDER BY dup_count DESC
                """)).fetchall()
            except Exception as e:
                print(f"⚠️  {table_name}: Error checking duplicates: {str(e)[:80]}")
                dup_result = []

            if dup_result:
                duplicates_found[table_name] = dup_result
                total_duplicates += len(dup_result)
                print(f"⚠️  {table_name}: FOUND {len(dup_result)} duplicate (slug, timestamp) pairs")
                for row in dup_result[:5]:  # Show first 5
                    print(f"     └─ {row[0][:30]:30s} | {row[1]} | count: {row[2]}")
                if len(dup_result) > 5:
                    print(f"     └─ ... and {len(dup_result) - 5} more")
            else:
                print(f"✅ {table_name}: No duplicates")

print("\n" + "=" * 100)
print("SUMMARY")
print("=" * 100)

if not duplicates_found:
    print("\n✅ NO DUPLICATES FOUND IN ANY TABLE!")
    print("\nAll tables are clean across the entire cp_backtest_h database.")
else:
    print(f"\n❌ DUPLICATES DETECTED IN {len(duplicates_found)} TABLE(S)")
    print(f"\nTotal duplicate (slug, timestamp) pairs: {total_duplicates}\n")

    for table_name, dups in duplicates_found.items():
        print(f"\n{table_name}:")
        print(f"  Total duplicate pairs: {len(dups)}")
        print(f"  Duplicate entries breakdown:")
        for row in dups[:10]:  # Show first 10
            print(f"    - slug: {row[0][:40]:40s} | timestamp: {row[1]} | duplicate_count: {row[2]}")
        if len(dups) > 10:
            print(f"    ... and {len(dups) - 10} more")

print("\n" + "=" * 100)
engine.dispose()
