#!/usr/bin/env python3
"""
3-Day Activity Report: Database Statistics & Timestamps
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

DB_HOST = '34.55.195.199'
DB_PORT = 5432
DB_USER = 'yogass09'
DB_PASSWORD = 'jaimaakamakhya'

print("\n" + "=" * 100)
print("3-DAY ACTIVITY REPORT: CryptoPrism-DB-H")
print("Generated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"))
print("=" * 100)

databases = {
    'cp_ai': 'cp_ai (Primary/Live)',
    'cp_backtest_h': 'cp_backtest_h (Backtest/Archive)',
    'dbcp': 'dbcp (General Purpose)'
}

# 3 days ago
three_days_ago = datetime.utcnow() - timedelta(days=3)

for db_name, db_label in databases.items():
    print(f"\n{'─' * 100}")
    print(f"📊 DATABASE: {db_label}")
    print(f"{'─' * 100}")

    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=db_name
        )

        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Get all tables
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)

        tables = [row['table_name'] for row in cursor.fetchall()]

        if not tables:
            print("  ⚠️  No tables found")
            conn.close()
            continue

        print(f"\n  📈 LATEST TIMESTAMP & ROW COUNTS (Last 3 Days)\n")
        print(f"  {'Table Name':<35} {'Latest Timestamp':<30} {'3-Day Count':>12}")
        print(f"  {'-' * 77}")

        for table in sorted(tables):
            try:
                # Get latest timestamp
                cursor.execute(f"""
                    SELECT MAX(timestamp) as latest_ts FROM "{table}"
                    WHERE EXISTS (SELECT 1 FROM information_schema.columns
                                 WHERE table_name = '{table}' AND column_name = 'timestamp')
                """)

                ts_result = cursor.fetchone()
                latest_ts = ts_result['latest_ts'] if ts_result and ts_result['latest_ts'] else None

                # Get 3-day count
                if latest_ts:
                    cursor.execute(f"""
                        SELECT COUNT(*) as count FROM "{table}"
                        WHERE timestamp > %s
                    """, (three_days_ago,))
                    count_result = cursor.fetchone()
                    count_3days = count_result['count'] if count_result else 0
                else:
                    count_3days = 0

                # Format output
                ts_str = latest_ts.strftime("%Y-%m-%d %H:%M:%S UTC") if latest_ts else "N/A (no timestamp)"
                print(f"  {table:<35} {ts_str:<30} {count_3days:>12,}")

            except Exception as e:
                print(f"  {table:<35} ERROR: {str(e)[:40]:<30}")
                continue

        # Summary stats for this database
        print(f"\n  📊 DATABASE SUMMARY\n")

        cursor.execute("""
            SELECT COUNT(*) as total_tables FROM information_schema.tables
            WHERE table_schema = 'public'
        """)
        total_tables = cursor.fetchone()['total_tables']

        # Get total rows across all main signal tables
        cursor.execute("""
            SELECT COUNT(*) as total FROM "ohlcv_1h_250_coins"
        """)
        ohlcv_total = cursor.fetchone()['total']

        print(f"  Total Tables: {total_tables}")
        print(f"  Total OHLCV Rows: {ohlcv_total:,}")

        conn.close()

    except Exception as e:
        print(f"  ❌ Connection Error: {str(e)}")
        continue

print(f"\n{'─' * 100}")
print("✅ REPORT COMPLETE")
print("=" * 100 + "\n")

# Now get latest timestamps from all databases in a summary table
print("=" * 100)
print("LATEST TIMESTAMPS SUMMARY - ALL DATABASES")
print("=" * 100)
print(f"\n{'Database':<25} {'Table Name':<35} {'Latest Timestamp':<30}")
print(f"{'-' * 90}")

for db_name, db_label in databases.items():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=db_name
        )

        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Key tables to check
        key_tables = [
            'ohlcv_1h_250_coins',
            'FE_TVV_SIGNALS',
            'FE_OSCILLATORS_SIGNALS',
            'FE_MOMENTUM_SIGNALS',
            'FE_RATIOS_SIGNALS',
            'FE_DMV_ALL',
            'FE_DMV_BITCOIN'
        ]

        for table in key_tables:
            try:
                cursor.execute(f"""
                    SELECT MAX(timestamp) as latest_ts FROM "{table}"
                """)

                result = cursor.fetchone()
                latest_ts = result['latest_ts'] if result and result['latest_ts'] else None
                ts_str = latest_ts.strftime("%Y-%m-%d %H:%M:%S") if latest_ts else "N/A"

                print(f"{db_label:<25} {table:<35} {ts_str:<30}")
            except:
                pass

        conn.close()

    except Exception as e:
        print(f"{db_label:<25} CONNECTION ERROR: {str(e)}")

print(f"\n{'=' * 90}\n")
