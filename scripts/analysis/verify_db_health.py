#!/usr/bin/env python3
"""
Database Health Verification Script
Checks cp_ai and cp_backtest_h for data sync, recent ingestion, and pipeline health
"""

import os
import psycopg2
from datetime import datetime, timedelta
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

# Load environment variables
load_dotenv()

DB_HOST = os.getenv('DB_HOST')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME_AI = os.getenv('DB_NAME_AI', 'cp_ai')
DB_NAME_BT = os.getenv('DB_NAME_BT', 'cp_backtest_h')

def connect_db(db_name):
    """Connect to a specific database"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=db_name
        )
        return conn
    except Exception as e:
        print(f"❌ Failed to connect to {db_name}: {e}")
        return None

def check_recent_data(conn, db_name):
    """Check if recent data exists in OHLCV table"""
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Check latest timestamp in OHLCV
        cursor.execute("""
            SELECT MAX(timestamp) as latest_ts, COUNT(*) as total_rows
            FROM ohlcv_1h_250_coins
        """)
        result = cursor.fetchone()
        cursor.close()

        latest_ts = result['latest_ts']
        total_rows = result['total_rows']

        if latest_ts:
            hours_old = (datetime.now(latest_ts.tzinfo) - latest_ts).total_seconds() / 3600
            print(f"  Latest data: {latest_ts}")
            print(f"  Hours old: {hours_old:.1f} hours")
            print(f"  Total rows: {total_rows}")

            if hours_old > 48:
                print(f"  ⚠️  WARNING: Data is {hours_old:.1f} hours old (expected <24h)")
                return False
            else:
                print(f"  ✅ Data is fresh")
                return True
        else:
            print(f"  ❌ No data found in OHLCV table")
            return False

    except Exception as e:
        print(f"  ❌ Error checking data: {e}")
        return False

def check_data_sync(conn_ai, conn_bt):
    """Check if cp_ai and cp_backtest_h are in sync"""
    try:
        cursor_ai = conn_ai.cursor(cursor_factory=RealDictCursor)
        cursor_bt = conn_bt.cursor(cursor_factory=RealDictCursor)

        # Get latest timestamp in both databases
        cursor_ai.execute("SELECT MAX(timestamp) as latest_ts, COUNT(*) as count FROM ohlcv_1h_250_coins")
        ai_data = cursor_ai.fetchone()

        cursor_bt.execute("SELECT MAX(timestamp) as latest_ts, COUNT(*) as count FROM ohlcv_1h_250_coins")
        bt_data = cursor_bt.fetchone()

        cursor_ai.close()
        cursor_bt.close()

        ai_ts = ai_data['latest_ts']
        bt_ts = bt_data['latest_ts']
        ai_count = ai_data['count']
        bt_count = bt_data['count']

        print(f"  cp_ai latest:       {ai_ts} ({ai_count} rows)")
        print(f"  cp_backtest_h latest: {bt_ts} ({bt_count} rows)")

        # Check if in sync (timestamps should match, allow 1 hour tolerance for processing delays)
        if ai_ts and bt_ts:
            time_diff = abs((ai_ts - bt_ts).total_seconds() / 3600)
            print(f"  Time difference: {time_diff:.2f} hours")

            if time_diff > 2:
                print(f"  ⚠️  WARNING: Databases are {time_diff:.2f} hours out of sync")
                return False
            else:
                print(f"  ✅ Databases are in sync")
                return True
        else:
            print(f"  ❌ One or both databases have no data")
            return False

    except Exception as e:
        print(f"  ❌ Error checking sync: {e}")
        return False

def check_signal_tables(conn, db_name):
    """Check if signal tables are being populated"""
    signal_tables = [
        'FE_TVV_SIGNALS',
        'FE_OSCILLATORS_SIGNALS',
        'FE_MOMENTUM_SIGNALS',
        'FE_RATIOS_SIGNALS',
        'FE_DMV_ALL'
    ]

    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        all_good = True

        for table in signal_tables:
            cursor.execute(f"""
                SELECT MAX(timestamp) as latest_ts, COUNT(*) as count
                FROM "{table}"
            """)
            result = cursor.fetchone()

            if result['latest_ts']:
                hours_old = (datetime.now(result['latest_ts'].tzinfo) - result['latest_ts']).total_seconds() / 3600
                status = "✅" if hours_old < 48 else "⚠️"
                print(f"  {status} {table:30} | Latest: {result['latest_ts']} | {hours_old:5.1f}h old | {result['count']:7} rows")
                if hours_old > 48:
                    all_good = False
            else:
                print(f"  ❌ {table:30} | No data")
                all_good = False

        cursor.close()
        return all_good

    except Exception as e:
        print(f"  ❌ Error checking signal tables: {e}")
        return False

def check_data_gaps(conn, db_name):
    """Check for data gaps in recent history"""
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Get data from last 2 days, group by hour
        cursor.execute("""
            SELECT DATE_TRUNC('hour', timestamp) as hour, COUNT(DISTINCT slug) as unique_coins
            FROM ohlcv_1h_250_coins
            WHERE timestamp > NOW() - INTERVAL '48 hours'
            GROUP BY DATE_TRUNC('hour', timestamp)
            ORDER BY hour DESC
            LIMIT 48
        """)

        results = cursor.fetchall()
        cursor.close()

        if not results:
            print(f"  ⚠️  No data in last 48 hours")
            return False

        # Check if we have data for most hours (at least 80% of expected hours)
        hours_with_data = len(results)
        expected_hours = 48
        completeness = (hours_with_data / expected_hours) * 100

        print(f"  Data hours: {hours_with_data}/{expected_hours} ({completeness:.1f}%)")

        if completeness < 80:
            print(f"  ⚠️  WARNING: Only {completeness:.1f}% data completeness in last 48h")
            return False
        else:
            print(f"  ✅ Good data completeness")
            return True

    except Exception as e:
        print(f"  ❌ Error checking gaps: {e}")
        return False

def main():
    print("=" * 80)
    print("CryptoPrism Database Health Verification")
    print(f"Check Time: {datetime.now()}")
    print("=" * 80)

    # Connect to both databases
    conn_ai = connect_db(DB_NAME_AI)
    conn_bt = connect_db(DB_NAME_BT)

    if not conn_ai or not conn_bt:
        print("\n❌ Cannot proceed without database connections")
        return False

    all_healthy = True

    # Check cp_ai database
    print(f"\n📊 Checking {DB_NAME_AI} database:")
    print("-" * 80)
    ai_healthy = check_recent_data(conn_ai, DB_NAME_AI)
    all_healthy = all_healthy and ai_healthy

    # Check cp_backtest_h database
    print(f"\n📊 Checking {DB_NAME_BT} database:")
    print("-" * 80)
    bt_healthy = check_recent_data(conn_bt, DB_NAME_BT)
    all_healthy = all_healthy and bt_healthy

    # Check sync between databases
    print(f"\n🔄 Checking database synchronization:")
    print("-" * 80)
    sync_healthy = check_data_sync(conn_ai, conn_bt)
    all_healthy = all_healthy and sync_healthy

    # Check data gaps in cp_ai
    print(f"\n📈 Checking data gaps in {DB_NAME_AI} (last 48h):")
    print("-" * 80)
    gaps_healthy = check_data_gaps(conn_ai, DB_NAME_AI)
    all_healthy = all_healthy and gaps_healthy

    # Check signal tables in cp_ai
    print(f"\n🎯 Checking signal tables in {DB_NAME_AI}:")
    print("-" * 80)
    signals_healthy = check_signal_tables(conn_ai, DB_NAME_AI)
    all_healthy = all_healthy and signals_healthy

    # Final summary
    print("\n" + "=" * 80)
    if all_healthy:
        print("✅ ALL SYSTEMS HEALTHY - Databases working fine!")
    else:
        print("⚠️  ISSUES DETECTED - See warnings above")
    print("=" * 80)

    conn_ai.close()
    conn_bt.close()

    return all_healthy

if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
