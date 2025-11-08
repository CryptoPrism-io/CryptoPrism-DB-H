#!/usr/bin/env python3
"""
Deep dive into FE_DMV_ALL table to understand the issue
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

DB_HOST = '34.55.195.199'
DB_PORT = 5432
DB_USER = 'yogass09'
DB_PASSWORD = 'jaimaakamakhya'

conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASSWORD,
    database='cp_ai'
)

cursor = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 100)
print("FE_DMV_ALL TABLE DEEP ANALYSIS")
print("=" * 100)

# Check all timestamps
cursor.execute(f"""
    SELECT timestamp, COUNT(*) as row_count
    FROM "FE_DMV_ALL"
    GROUP BY timestamp
    ORDER BY timestamp DESC
""")

print("\n📊 All timestamps in FE_DMV_ALL:")
results = cursor.fetchall()
for row in results:
    print(f"  {row['timestamp']}: {row['row_count']} rows")

# Check the 06:59:59 timestamp specifically
print("\n📊 Details of 2025-11-08 06:59:59+00:00 timestamp:")
cursor.execute(f"""
    SELECT
        COUNT(*) as total_rows,
        COUNT(DISTINCT slug) as unique_coins,
        COUNT(DISTINCT name) as unique_names
    FROM "FE_DMV_ALL"
    WHERE timestamp = '2025-11-08 06:59:59+00:00'
""")

result = cursor.fetchone()
print(f"  Total rows: {result['total_rows']}")
print(f"  Unique coins (slug): {result['unique_coins']}")
print(f"  Unique names: {result['unique_names']}")

# List the coins
print("\n📊 Coins in 2025-11-08 06:59:59+00:00:")
cursor.execute(f"""
    SELECT slug, name
    FROM "FE_DMV_ALL"
    WHERE timestamp = '2025-11-08 06:59:59+00:00'
    ORDER BY slug
""")

coins = cursor.fetchall()
for i, coin in enumerate(coins, 1):
    print(f"  {i:3d}. {coin['slug']:20s} ({coin['name']})")

# Check if NULL issue with timestamp
print("\n📊 Check for NULL timestamps:")
cursor.execute(f"""
    SELECT COUNT(*) as null_count FROM "FE_DMV_ALL" WHERE timestamp IS NULL
""")
result = cursor.fetchone()
print(f"  NULL timestamps: {result['null_count']}")

# Compare with other signal tables at same timestamp
print("\n📊 Comparison with other signal tables at 2025-11-08 06:59:59+00:00:")
cursor.execute(f"""
    SELECT
        'FE_TVV_SIGNALS' as table_name,
        COUNT(*) as row_count,
        COUNT(DISTINCT slug) as unique_coins
    FROM "FE_TVV_SIGNALS"
    WHERE timestamp = '2025-11-08 06:59:59+00:00'
    UNION ALL
    SELECT
        'FE_OSCILLATORS_SIGNALS',
        COUNT(*),
        COUNT(DISTINCT slug)
    FROM "FE_OSCILLATORS_SIGNALS"
    WHERE timestamp = '2025-11-08 06:59:59+00:00'
    UNION ALL
    SELECT
        'FE_MOMENTUM_SIGNALS',
        COUNT(*),
        COUNT(DISTINCT slug)
    FROM "FE_MOMENTUM_SIGNALS"
    WHERE timestamp = '2025-11-08 06:59:59+00:00'
    UNION ALL
    SELECT
        'FE_RATIOS_SIGNALS',
        COUNT(*),
        COUNT(DISTINCT slug)
    FROM "FE_RATIOS_SIGNALS"
    WHERE timestamp = '2025-11-08 06:59:59+00:00'
    UNION ALL
    SELECT
        'FE_DMV_ALL',
        COUNT(*),
        COUNT(DISTINCT slug)
    FROM "FE_DMV_ALL"
    WHERE timestamp = '2025-11-08 06:59:59+00:00'
""")

for row in cursor.fetchall():
    print(f"  {row['table_name']:25s}: {row['row_count']:4d} rows, {row['unique_coins']:3d} unique coins")

# Check which coins are in other tables but missing from FE_DMV_ALL
print("\n📊 Coins in FE_MOMENTUM_SIGNALS but missing from FE_DMV_ALL at 2025-11-08 06:59:59:")
cursor.execute(f"""
    SELECT DISTINCT slug FROM "FE_MOMENTUM_SIGNALS"
    WHERE timestamp = '2025-11-08 06:59:59+00:00'
    AND slug NOT IN (
        SELECT DISTINCT slug FROM "FE_DMV_ALL"
        WHERE timestamp = '2025-11-08 06:59:59+00:00'
    )
    ORDER BY slug
""")

missing = cursor.fetchall()
if missing:
    print(f"  Found {len(missing)} missing coins:")
    for coin in missing:
        print(f"    - {coin['slug']}")
else:
    print("  No missing coins")

# Check which coin has NULL timestamp
print("\n📊 Coin with NULL timestamp in FE_DMV_ALL:")
cursor.execute(f"""
    SELECT slug, name FROM "FE_DMV_ALL"
    WHERE timestamp IS NULL
""")

null_coins = cursor.fetchall()
if null_coins:
    print(f"  Found {len(null_coins)} coin(s) with NULL timestamp:")
    for coin in null_coins:
        print(f"    - {coin['slug']} ({coin['name']})")
else:
    print("  No NULL timestamps found")

cursor.close()
conn.close()

print("\n" + "=" * 100)
