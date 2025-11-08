#!/usr/bin/env python3
"""
Detailed Signal Tables Analysis
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

signal_tables = [
    'FE_TVV_SIGNALS',
    'FE_OSCILLATORS_SIGNALS',
    'FE_MOMENTUM_SIGNALS',
    'FE_RATIOS_SIGNALS',
    'FE_DMV_ALL'
]

print("=" * 100)
print("DETAILED SIGNAL TABLES ANALYSIS")
print("=" * 100)

for table in signal_tables:
    print(f"\n📊 Table: {table}")
    print("-" * 100)

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # 1. Basic count and timestamp info
    cursor.execute(f"""
        SELECT
            COUNT(*) as total_rows,
            COUNT(DISTINCT slug) as unique_coins,
            MAX(timestamp) as latest_ts,
            MIN(timestamp) as oldest_ts
        FROM "{table}"
    """)
    result = cursor.fetchone()

    print(f"  Total rows: {result['total_rows']}")
    print(f"  Unique coins: {result['unique_coins']}")
    print(f"  Latest timestamp: {result['latest_ts']}")
    print(f"  Oldest timestamp: {result['oldest_ts']}")

    if result['latest_ts']:
        hours_old = (datetime.now(result['latest_ts'].tzinfo) - result['latest_ts']).total_seconds() / 3600
        print(f"  Hours old: {hours_old:.1f}h")

    # 2. Distribution by latest timestamp
    cursor.execute(f"""
        SELECT
            timestamp,
            COUNT(DISTINCT slug) as coin_count,
            COUNT(*) as row_count
        FROM "{table}"
        WHERE timestamp > NOW() - INTERVAL '72 hours'
        GROUP BY timestamp
        ORDER BY timestamp DESC
        LIMIT 10
    """)

    print(f"\n  Latest 10 timestamps:")
    results = cursor.fetchall()
    for row in results:
        print(f"    {row['timestamp']} | {row['coin_count']:3d} coins | {row['row_count']:4d} rows")

    # 3. Check if latest hour has full coin coverage
    cursor.execute(f"""
        SELECT timestamp, COUNT(DISTINCT slug) as coin_count
        FROM "{table}"
        GROUP BY timestamp
        ORDER BY timestamp DESC
        LIMIT 1
    """)
    latest_ts_result = cursor.fetchone()

    if latest_ts_result:
        latest_ts = latest_ts_result['timestamp']
        latest_coin_count = latest_ts_result['coin_count']
        print(f"\n  Latest hour ({latest_ts}): {latest_coin_count} coins")

        if latest_coin_count < 200:
            print(f"    ⚠️  WARNING: Expected ~250 coins, got {latest_coin_count}")
        else:
            print(f"    ✅ Good coin coverage")

        # Show which coins are missing from latest hour
        cursor.execute(f"""
            SELECT DISTINCT slug FROM ohlcv_1h_250_coins
            WHERE timestamp = %s
            AND slug NOT IN (
                SELECT DISTINCT slug FROM "{table}"
                WHERE timestamp = %s
            )
            ORDER BY slug
        """, (latest_ts, latest_ts))

        missing = cursor.fetchall()
        if missing:
            missing_coins = [row['slug'] for row in missing]
            print(f"    Missing coins in latest hour: {', '.join(missing_coins[:10])}")
            if len(missing_coins) > 10:
                print(f"                                  ... and {len(missing_coins) - 10} more")

    # 4. Check for duplicates
    cursor.execute(f"""
        SELECT slug, timestamp, COUNT(*) as dup_count
        FROM "{table}"
        GROUP BY slug, timestamp
        HAVING COUNT(*) > 1
    """)

    dupes = cursor.fetchall()
    if dupes:
        print(f"\n  ⚠️  Found {len(dupes)} duplicate (slug, timestamp) pairs:")
        for row in dupes[:5]:
            print(f"    {row['slug']} @ {row['timestamp']}: {row['dup_count']} copies")
    else:
        print(f"\n  ✅ No duplicates found")

    # 5. Column names
    cursor.execute(f"""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = '{table}'
        ORDER BY ordinal_position
    """)

    cols = cursor.fetchall()
    print(f"\n  Columns ({len(cols)}): {', '.join([row['column_name'] for row in cols])}")

    cursor.close()

conn.close()

print("\n" + "=" * 100)
print("END OF ANALYSIS")
print("=" * 100)
