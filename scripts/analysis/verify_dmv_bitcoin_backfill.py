#!/usr/bin/env python3
"""
Verify FE_DMV_BITCOIN backfill results
"""

import psycopg2
from psycopg2.extras import RealDictCursor

DB_HOST = '34.55.195.199'
DB_PORT = 5432
DB_USER = 'yogass09'
DB_PASSWORD = 'jaimaakamakhya'

print("=" * 100)
print("FE_DMV_BITCOIN BACKFILL VERIFICATION")
print("=" * 100)

# Check cp_backtest_h
print("\n1. CP_BACKTEST_H (Backtest Database)")
print("-" * 100)

conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASSWORD,
    database='cp_backtest_h'
)

cursor = conn.cursor(cursor_factory=RealDictCursor)

# Count records
cursor.execute("""
    SELECT
        COUNT(*) as total_rows,
        COUNT(DISTINCT slug) as unique_slugs,
        COUNT(DISTINCT timestamp) as unique_timestamps,
        COUNT(CASE WHEN timestamp IS NULL THEN 1 END) as null_timestamps,
        MIN(timestamp) as earliest_ts,
        MAX(timestamp) as latest_ts
    FROM "FE_DMV_BITCOIN"
""")

result = cursor.fetchone()
print(f"Total rows:           {result['total_rows']:,}")
print(f"Unique slugs:         {result['unique_slugs']}")
print(f"Unique timestamps:    {result['unique_timestamps']:,}")
print(f"NULL timestamps:      {result['null_timestamps']}")
print(f"Date range:           {result['earliest_ts']} to {result['latest_ts']}")

# Check column structure
cursor.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'FE_DMV_BITCOIN'
    ORDER BY ordinal_position
""")

print(f"\nColumns ({len(cursor.fetchall())} total):")
cursor.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'FE_DMV_BITCOIN'
    ORDER BY ordinal_position
""")

for row in cursor.fetchall():
    print(f"  - {row['column_name']:40s} ({row['data_type']})")

# Sample recent data
cursor.execute("""
    SELECT id, slug, name, timestamp
    FROM "FE_DMV_BITCOIN"
    ORDER BY timestamp DESC
    LIMIT 5
""")

print(f"\nRecent records:")
for row in cursor.fetchall():
    print(f"  {row['timestamp']} | {row['slug']:20s} | {row['name']}")

cursor.close()
conn.close()

# Check cp_ai
print("\n\n2. CP_AI (Primary Database)")
print("-" * 100)

conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASSWORD,
    database='cp_ai'
)

cursor = conn.cursor(cursor_factory=RealDictCursor)

# Count records
cursor.execute("""
    SELECT
        COUNT(*) as total_rows,
        MAX(timestamp) as latest_ts
    FROM "FE_DMV_BITCOIN"
""")

result = cursor.fetchone()
if result['total_rows'] > 0:
    print(f"Total rows:           {result['total_rows']}")
    print(f"Latest timestamp:     {result['latest_ts']}")
    print(f"Status:               OK")
else:
    print(f"Status:               Empty (will be populated next hourly run)")

cursor.close()
conn.close()

# Compare FE_DMV_ALL and FE_DMV_BITCOIN
print("\n\n3. COMPARISON: FE_DMV_ALL vs FE_DMV_BITCOIN")
print("-" * 100)

conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASSWORD,
    database='cp_backtest_h'
)

cursor = conn.cursor(cursor_factory=RealDictCursor)

cursor.execute("""
    SELECT
        'FE_DMV_ALL (with bitcoin)' as table_name,
        COUNT(*) as rows,
        COUNT(DISTINCT timestamp) as timestamps,
        COUNT(CASE WHEN timestamp IS NULL THEN 1 END) as null_ts
    FROM "FE_DMV_ALL"
    UNION ALL
    SELECT
        'FE_DMV_BITCOIN (bitcoin only)',
        COUNT(*),
        COUNT(DISTINCT timestamp),
        COUNT(CASE WHEN timestamp IS NULL THEN 1 END)
    FROM "FE_DMV_BITCOIN"
""")

for row in cursor.fetchall():
    print(f"{row[0]:35s} | Rows: {row[1]:6,} | TS: {row[2]:6,} | NULL: {row[3]}")

cursor.close()
conn.close()

print("\n" + "=" * 100)
print("VERIFICATION COMPLETE")
print("=" * 100)
