# ============================================
# CryptoPrism-DB-H: Timestamp Integrity Check
# ============================================
# Description: Validates hourly timestamp continuity in cp_backtest_h
# Input Tables: All FE_* tables in cp_backtest_h
# Output: Console report of missing timestamps
# Frequency: On-demand QA check

import time
import pandas as pd
import warnings
import logging
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Configuration
warnings.filterwarnings('ignore')
start_time = time.time()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("timestamp_integrity.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Environment loading
if not os.getenv("GITHUB_ACTIONS"):
    load_dotenv()
else:
    logger.info("Running in GitHub Actions")

# Database connection
try:
    db_host = os.getenv("DB_HOST")
    db_name_bt = os.getenv("DB_NAME_BT", "cp_backtest_h")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_port = os.getenv("DB_PORT", "5432")

    # Validate required environment variables
    required_vars = {"DB_HOST": db_host, "DB_USER": db_user, "DB_PASSWORD": db_password}
    missing_vars = [k for k, v in required_vars.items() if not v]

    if missing_vars:
        raise ValueError(f"❌ Missing environment variables: {', '.join(missing_vars)}")

    # Create database engine
    engine_backtest = create_engine(
        f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name_bt}",
        pool_pre_ping=True
    )

    logger.info(f"✅ Connected to database: {db_name_bt}")

except Exception as e:
    logger.error(f"❌ Database connection failed: {e}")
    raise

def check_table_integrity(engine, table_name):
    """
    Check timestamp integrity for a given table
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Checking table: {table_name}")
    logger.info(f"{'='*60}")

    try:
        # Get min, max, and count
        query = f"""
        SELECT
            MIN(timestamp) as min_ts,
            MAX(timestamp) as max_ts,
            COUNT(DISTINCT timestamp) as unique_timestamps,
            COUNT(*) as total_records,
            COUNT(DISTINCT slug) as unique_coins
        FROM "{table_name}"
        """

        df_stats = pd.read_sql(query, con=engine)

        if df_stats.empty or pd.isna(df_stats['min_ts'].iloc[0]):
            logger.warning(f"⚠️ Table {table_name} is empty or has no timestamps")
            return

        min_ts = df_stats['min_ts'].iloc[0]
        max_ts = df_stats['max_ts'].iloc[0]
        unique_timestamps = df_stats['unique_timestamps'].iloc[0]
        total_records = df_stats['total_records'].iloc[0]
        unique_coins = df_stats['unique_coins'].iloc[0]

        # Calculate expected hourly records
        time_diff = max_ts - min_ts
        expected_hours = int(time_diff.total_seconds() / 3600) + 1

        logger.info(f"📅 Min Timestamp: {min_ts}")
        logger.info(f"📅 Max Timestamp: {max_ts}")
        logger.info(f"⏱️  Time Range: {time_diff} ({expected_hours} hours)")
        logger.info(f"🔢 Unique Timestamps: {unique_timestamps}")
        logger.info(f"🔢 Expected Hours: {expected_hours}")
        logger.info(f"🔢 Total Records: {total_records:,}")
        logger.info(f"🪙 Unique Coins: {unique_coins}")

        # Check for missing timestamps
        if unique_timestamps < expected_hours:
            missing_count = expected_hours - unique_timestamps
            logger.warning(f"⚠️ MISSING {missing_count} hourly timestamps!")

            # Find the gaps
            query_gaps = f"""
            WITH RECURSIVE hourly_series AS (
                SELECT MIN(timestamp) as hour_ts
                FROM "{table_name}"
                UNION ALL
                SELECT hour_ts + INTERVAL '1 hour'
                FROM hourly_series
                WHERE hour_ts < (SELECT MAX(timestamp) FROM "{table_name}")
            ),
            existing_hours AS (
                SELECT DISTINCT timestamp as hour_ts
                FROM "{table_name}"
            )
            SELECT hs.hour_ts as missing_timestamp
            FROM hourly_series hs
            LEFT JOIN existing_hours eh ON hs.hour_ts = eh.hour_ts
            WHERE eh.hour_ts IS NULL
            ORDER BY hs.hour_ts
            LIMIT 100
            """

            df_gaps = pd.read_sql(query_gaps, con=engine)

            if not df_gaps.empty:
                logger.warning(f"\n🔴 Missing timestamps (showing first 100):")
                for idx, row in df_gaps.iterrows():
                    logger.warning(f"   • {row['missing_timestamp']}")

                if len(df_gaps) == 100:
                    logger.warning(f"   ... and potentially more (limit reached)")

        else:
            logger.info(f"✅ No missing hourly timestamps!")

        # Check for duplicate timestamps per coin
        query_dupes = f"""
        SELECT slug, timestamp, COUNT(*) as duplicate_count
        FROM "{table_name}"
        GROUP BY slug, timestamp
        HAVING COUNT(*) > 1
        ORDER BY duplicate_count DESC
        LIMIT 10
        """

        df_dupes = pd.read_sql(query_dupes, con=engine)

        if not df_dupes.empty:
            logger.warning(f"\n⚠️ Found duplicate records (slug + timestamp):")
            for idx, row in df_dupes.iterrows():
                logger.warning(f"   • {row['slug']} @ {row['timestamp']}: {row['duplicate_count']} records")
        else:
            logger.info(f"✅ No duplicate records found!")

    except Exception as e:
        logger.error(f"❌ Error checking {table_name}: {e}")

def get_all_tables(engine):
    """
    Get all tables in the database
    """
    query = """
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_type = 'BASE TABLE'
    ORDER BY table_name
    """

    df_tables = pd.read_sql(query, con=engine)
    return df_tables['table_name'].tolist()

# Main execution
try:
    logger.info("🚀 Starting Timestamp Integrity Check")
    logger.info(f"📊 Database: {db_name_bt}")

    # Get all tables
    all_tables = get_all_tables(engine_backtest)
    logger.info(f"\n📋 Found {len(all_tables)} tables in database")

    # Focus on main tables (FE_* and ohlcv)
    priority_tables = [
        "FE_DMV_ALL",
        "FE_DMV_SCORES",
        "ohlcv_1h_250_coins",
        "FE_TVV_SIGNALS",
        "FE_OSCILLATORS_SIGNALS",
        "FE_MOMENTUM_SIGNALS",
        "FE_RATIOS_SIGNALS"
    ]

    # Check which priority tables exist
    existing_priority = [t for t in priority_tables if t in all_tables]

    logger.info(f"\n🎯 Priority tables to check: {len(existing_priority)}")
    for table in existing_priority:
        logger.info(f"   • {table}")

    # Check each priority table
    for table in existing_priority:
        check_table_integrity(engine_backtest, table)

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info(f"✅ Integrity check completed!")
    logger.info(f"⏱️  Total execution time: {time.time() - start_time:.2f} seconds")
    logger.info(f"{'='*60}")

except Exception as e:
    logger.error(f"❌ Fatal error: {e}")
    raise

finally:
    if 'engine_backtest' in locals():
        engine_backtest.dispose()
        logger.info("🔌 Database connection closed")
