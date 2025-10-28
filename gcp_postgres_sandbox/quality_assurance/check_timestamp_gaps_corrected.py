# ============================================
# CryptoPrism-DB-H: Corrected Timestamp Gap Analysis
# ============================================
# Description: Accurate hourly timestamp gap detection for :59:59 pattern
# Input Tables: All FE_* tables in cp_backtest_h
# Output: Report of gaps > 1.5 hours (if any)
# Frequency: On-demand QA check

import time
import pandas as pd
import warnings
import logging
import os
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Configuration
warnings.filterwarnings('ignore')
start_time = time.time()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("timestamp_gaps_corrected.log"), logging.StreamHandler()]
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

    required_vars = {"DB_HOST": db_host, "DB_USER": db_user, "DB_PASSWORD": db_password}
    missing_vars = [k for k, v in required_vars.items() if not v]

    if missing_vars:
        raise ValueError(f"Missing environment variables: {', '.join(missing_vars)}")

    engine_backtest = create_engine(
        f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name_bt}",
        pool_pre_ping=True
    )

    logger.info(f"Connected to database: {db_name_bt}")

except Exception as e:
    logger.error(f"Database connection failed: {e}")
    raise

def analyze_timestamp_gaps(engine, table_name, days=30, sample_coins=5):
    """
    Analyze actual time gaps between consecutive records
    """
    logger.info(f"\n{'='*70}")
    logger.info(f"Analyzing: {table_name}")
    logger.info(f"{'='*70}")

    try:
        # Get overall stats
        query_stats = f"""
        SELECT
            MIN(timestamp) as min_ts,
            MAX(timestamp) as max_ts,
            COUNT(DISTINCT timestamp) as unique_timestamps,
            COUNT(*) as total_records,
            COUNT(DISTINCT slug) as unique_coins
        FROM "{table_name}"
        WHERE timestamp >= NOW() - INTERVAL '{days} days'
        """

        df_stats = pd.read_sql(query_stats, con=engine)

        if df_stats.empty or pd.isna(df_stats['min_ts'].iloc[0]):
            logger.warning(f"No data in last {days} days")
            return

        min_ts = df_stats['min_ts'].iloc[0]
        max_ts = df_stats['max_ts'].iloc[0]
        unique_timestamps = df_stats['unique_timestamps'].iloc[0]
        total_records = df_stats['total_records'].iloc[0]
        unique_coins = df_stats['unique_coins'].iloc[0]

        logger.info(f"Time Range: {min_ts} to {max_ts}")
        logger.info(f"Unique Timestamps: {unique_timestamps}")
        logger.info(f"Total Records: {total_records:,}")
        logger.info(f"Unique Coins: {unique_coins}")

        # Analyze gaps using actual time differences
        query_gaps = f"""
        WITH gaps AS (
            SELECT
                slug,
                timestamp as current_ts,
                LAG(timestamp) OVER (PARTITION BY slug ORDER BY timestamp) as prev_ts,
                EXTRACT(EPOCH FROM (
                    timestamp - LAG(timestamp) OVER (PARTITION BY slug ORDER BY timestamp)
                )) / 3600.0 AS hours_gap
            FROM "{table_name}"
            WHERE timestamp >= NOW() - INTERVAL '{days} days'
        )
        SELECT
            slug,
            prev_ts,
            current_ts,
            hours_gap
        FROM gaps
        WHERE hours_gap IS NOT NULL
        AND hours_gap > 1.5
        ORDER BY hours_gap DESC
        LIMIT 100
        """

        df_gaps = pd.read_sql(query_gaps, con=engine)

        if df_gaps.empty:
            logger.info("SUCCESS: No gaps larger than 1.5 hours found!")
            logger.info("Hourly data integrity is PERFECT")
        else:
            logger.warning(f"WARNING: Found {len(df_gaps)} gaps > 1.5 hours")
            logger.warning("\nLargest gaps:")
            for idx, row in df_gaps.head(20).iterrows():
                logger.warning(
                    f"   {row['slug']}: {row['prev_ts']} -> {row['current_ts']} "
                    f"(gap: {row['hours_gap']:.2f} hours)"
                )
            if len(df_gaps) > 20:
                logger.warning(f"   ... and {len(df_gaps) - 20} more gaps")

        # Get gap distribution statistics
        query_gap_stats = f"""
        WITH gaps AS (
            SELECT
                EXTRACT(EPOCH FROM (
                    timestamp - LAG(timestamp) OVER (PARTITION BY slug ORDER BY timestamp)
                )) / 3600.0 AS hours_gap
            FROM "{table_name}"
            WHERE timestamp >= NOW() - INTERVAL '{days} days'
        )
        SELECT
            COUNT(*) as total_gaps,
            MIN(hours_gap) as min_gap,
            AVG(hours_gap) as avg_gap,
            MAX(hours_gap) as max_gap,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY hours_gap) as median_gap,
            COUNT(CASE WHEN hours_gap > 1.5 THEN 1 END) as gaps_over_1_5h,
            COUNT(CASE WHEN hours_gap <= 1.5 THEN 1 END) as normal_gaps
        FROM gaps
        WHERE hours_gap IS NOT NULL
        """

        df_gap_stats = pd.read_sql(query_gap_stats, con=engine)

        if not df_gap_stats.empty:
            stats = df_gap_stats.iloc[0]
            logger.info(f"\nGap Statistics:")
            logger.info(f"   Total Gaps Analyzed: {stats['total_gaps']:,}")
            logger.info(f"   Min Gap: {stats['min_gap']:.3f} hours")
            logger.info(f"   Avg Gap: {stats['avg_gap']:.3f} hours")
            logger.info(f"   Median Gap: {stats['median_gap']:.3f} hours")
            logger.info(f"   Max Gap: {stats['max_gap']:.3f} hours")
            logger.info(f"   Normal Gaps (<=1.5h): {stats['normal_gaps']:,}")
            logger.info(f"   Problematic Gaps (>1.5h): {stats['gaps_over_1_5h']:,}")

            # Calculate integrity percentage
            if stats['total_gaps'] > 0:
                integrity_pct = (stats['normal_gaps'] / stats['total_gaps']) * 100
                logger.info(f"   Integrity Score: {integrity_pct:.2f}%")

        # Sample analysis: Check specific coins
        query_sample = f"""
        SELECT DISTINCT slug
        FROM "{table_name}"
        WHERE timestamp >= NOW() - INTERVAL '{days} days'
        ORDER BY slug
        LIMIT {sample_coins}
        """

        df_sample_coins = pd.read_sql(query_sample, con=engine)

        if not df_sample_coins.empty:
            logger.info(f"\nSample Coin Analysis (first {sample_coins} coins):")
            for coin in df_sample_coins['slug']:
                query_coin_gaps = f"""
                WITH gaps AS (
                    SELECT
                        EXTRACT(EPOCH FROM (
                            timestamp - LAG(timestamp) OVER (ORDER BY timestamp)
                        )) / 3600.0 AS hours_gap
                    FROM "{table_name}"
                    WHERE slug = '{coin}'
                    AND timestamp >= NOW() - INTERVAL '{days} days'
                )
                SELECT
                    COUNT(*) as records,
                    MAX(hours_gap) as max_gap
                FROM gaps
                WHERE hours_gap IS NOT NULL
                """

                df_coin = pd.read_sql(query_coin_gaps, con=engine)
                if not df_coin.empty:
                    coin_stats = df_coin.iloc[0]
                    status = "OK" if coin_stats['max_gap'] <= 1.5 else f"GAP: {coin_stats['max_gap']:.2f}h"
                    logger.info(f"   {coin}: {coin_stats['records']} records, Max gap: {status}")

    except Exception as e:
        logger.error(f"Error analyzing {table_name}: {e}")

# Main execution
try:
    logger.info("="*70)
    logger.info("Corrected Timestamp Gap Analysis")
    logger.info(f"Database: {db_name_bt}")
    logger.info("="*70)

    # Priority tables
    priority_tables = [
        "FE_TVV_SIGNALS",
        "FE_OSCILLATORS_SIGNALS",
        "FE_MOMENTUM_SIGNALS",
        "FE_RATIOS_SIGNALS",
        "FE_DMV_ALL"
    ]

    # Get existing tables
    query_tables = """
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_type = 'BASE TABLE'
    ORDER BY table_name
    """
    df_all_tables = pd.read_sql(query_tables, con=engine_backtest)
    all_tables = df_all_tables['table_name'].tolist()

    existing_priority = [t for t in priority_tables if t in all_tables]

    logger.info(f"\nAnalyzing {len(existing_priority)} tables")

    # Analyze each table
    for table in existing_priority:
        analyze_timestamp_gaps(engine_backtest, table, days=30, sample_coins=5)

    # Summary
    logger.info(f"\n{'='*70}")
    logger.info(f"Analysis completed!")
    logger.info(f"Execution time: {time.time() - start_time:.2f} seconds")
    logger.info(f"{'='*70}")

except Exception as e:
    logger.error(f"Fatal error: {e}")
    raise

finally:
    if 'engine_backtest' in locals():
        engine_backtest.dispose()
        logger.info("Database connection closed")
