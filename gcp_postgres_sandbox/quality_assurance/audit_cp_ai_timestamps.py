# ============================================
# CryptoPrism-DB-H: cp_ai Timestamp Audit
# ============================================
# Description: Audit cp_ai database for available data and gaps
# Purpose: Understand what data exists before backfilling cp_backtest_h
# Output: Detailed report of data availability

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
    handlers=[logging.FileHandler("audit_cp_ai.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Environment loading
if not os.getenv("GITHUB_ACTIONS"):
    load_dotenv()

# Database connections
try:
    db_host = os.getenv("DB_HOST")
    db_name_ai = os.getenv("DB_NAME_AI", "cp_ai")
    db_name_bt = os.getenv("DB_NAME_BT", "cp_backtest_h")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_port = os.getenv("DB_PORT", "5432")

    required_vars = {"DB_HOST": db_host, "DB_USER": db_user, "DB_PASSWORD": db_password}
    missing_vars = [k for k, v in required_vars.items() if not v]

    if missing_vars:
        raise ValueError(f"Missing environment variables: {', '.join(missing_vars)}")

    # Create engines
    engine_cpai = create_engine(
        f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name_ai}",
        pool_pre_ping=True
    )

    engine_backtest = create_engine(
        f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name_bt}",
        pool_pre_ping=True
    )

    logger.info(f"Connected to databases: {db_name_ai}, {db_name_bt}")

except Exception as e:
    logger.error(f"Database connection failed: {e}")
    raise

def audit_table(engine, db_name, table_name):
    """
    Audit a single table for data availability
    """
    logger.info(f"\n{'='*70}")
    logger.info(f"Auditing: {db_name}.{table_name}")
    logger.info(f"{'='*70}")

    try:
        # Get overall statistics
        query_stats = f"""
        SELECT
            COUNT(*) as total_records,
            MIN(timestamp) as oldest_record,
            MAX(timestamp) as newest_record,
            COUNT(DISTINCT timestamp) as unique_timestamps,
            COUNT(DISTINCT slug) as unique_coins
        FROM "{table_name}"
        """

        df_stats = pd.read_sql(query_stats, con=engine)

        if df_stats.empty or df_stats['total_records'].iloc[0] == 0:
            logger.warning(f"Table {table_name} is empty or does not exist")
            return None

        stats = df_stats.iloc[0]
        logger.info(f"Total Records: {stats['total_records']:,}")
        logger.info(f"Oldest Record: {stats['oldest_record']}")
        logger.info(f"Newest Record: {stats['newest_record']}")
        logger.info(f"Unique Timestamps: {stats['unique_timestamps']:,}")
        logger.info(f"Unique Coins: {stats['unique_coins']:,}")

        # Calculate expected hours
        if pd.notna(stats['oldest_record']) and pd.notna(stats['newest_record']):
            time_diff = stats['newest_record'] - stats['oldest_record']
            expected_hours = int(time_diff.total_seconds() / 3600) + 1
            coverage_pct = (stats['unique_timestamps'] / expected_hours) * 100 if expected_hours > 0 else 0

            logger.info(f"Time Span: {time_diff}")
            logger.info(f"Expected Hours: {expected_hours:,}")
            logger.info(f"Coverage: {coverage_pct:.2f}%")

        # Check for gaps > 1.5 hours
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
        )
        SELECT
            COUNT(*) as total_gaps
        FROM gaps
        WHERE hours_gap > 1.5
        """

        df_gaps = pd.read_sql(query_gaps, con=engine)
        gaps_count = df_gaps['total_gaps'].iloc[0] if not df_gaps.empty else 0

        if gaps_count > 0:
            logger.warning(f"Found {gaps_count:,} gaps > 1.5 hours")

            # Get sample of largest gaps
            query_sample_gaps = f"""
            WITH gaps AS (
                SELECT
                    slug,
                    timestamp as current_ts,
                    LAG(timestamp) OVER (PARTITION BY slug ORDER BY timestamp) as prev_ts,
                    EXTRACT(EPOCH FROM (
                        timestamp - LAG(timestamp) OVER (PARTITION BY slug ORDER BY timestamp)
                    )) / 3600.0 AS hours_gap
                FROM "{table_name}"
            )
            SELECT slug, prev_ts, current_ts, hours_gap
            FROM gaps
            WHERE hours_gap > 1.5
            ORDER BY hours_gap DESC
            LIMIT 10
            """

            df_sample_gaps = pd.read_sql(query_sample_gaps, con=engine)
            logger.warning("Largest gaps (top 10):")
            for _, row in df_sample_gaps.iterrows():
                logger.warning(
                    f"   {row['slug']}: {row['prev_ts']} -> {row['current_ts']} "
                    f"({row['hours_gap']:.2f} hours)"
                )
        else:
            logger.info("SUCCESS: No gaps > 1.5 hours found")

        # Daily distribution
        query_daily = f"""
        SELECT
            DATE(timestamp) as date,
            COUNT(DISTINCT timestamp) as hours_count,
            COUNT(*) as records_count
        FROM "{table_name}"
        GROUP BY DATE(timestamp)
        ORDER BY date DESC
        LIMIT 30
        """

        df_daily = pd.read_sql(query_daily, con=engine)
        logger.info(f"\nDaily distribution (last 30 days):")
        logger.info(f"{'Date':<12} {'Hours':<8} {'Records':<10} {'Status'}")
        logger.info("-" * 50)
        for _, row in df_daily.iterrows():
            date_str = row['date'].strftime('%Y-%m-%d')
            hours = row['hours_count']
            records = row['records_count']
            status = "OK" if hours >= 20 else f"LOW ({hours}/24)"
            logger.info(f"{date_str:<12} {hours:<8} {records:<10,} {status}")

        return stats

    except Exception as e:
        logger.error(f"Error auditing {table_name}: {e}")
        return None

# Main execution
try:
    logger.info("="*70)
    logger.info("cp_ai Database Audit")
    logger.info("="*70)

    # Check OHLCV source data
    logger.info("\n### OHLCV Source Data ###")
    ohlcv_stats = audit_table(engine_cpai, "cp_ai", "ohlcv_1h_250_coins")

    # Check FE tables
    fe_tables = [
        "FE_TVV_SIGNALS",
        "FE_OSCILLATORS_SIGNALS",
        "FE_MOMENTUM_SIGNALS",
        "FE_RATIOS_SIGNALS"
    ]

    logger.info("\n### Feature Engineering Tables ###")
    fe_stats = {}
    for table in fe_tables:
        stats = audit_table(engine_cpai, "cp_ai", table)
        if stats is not None:
            fe_stats[table] = stats

    # Compare with cp_backtest_h
    logger.info("\n" + "="*70)
    logger.info("Comparison: cp_ai vs cp_backtest_h")
    logger.info("="*70)

    for table in fe_tables:
        logger.info(f"\n{table}:")

        # Get cp_backtest_h stats
        query_bt = f"""
        SELECT
            COUNT(*) as total_records,
            MIN(timestamp) as oldest_record,
            MAX(timestamp) as newest_record
        FROM "{table}"
        """

        try:
            df_bt = pd.read_sql(query_bt, con=engine_backtest)
            if not df_bt.empty and df_bt['total_records'].iloc[0] > 0:
                bt_stats = df_bt.iloc[0]
                logger.info(f"   cp_ai:")
                if table in fe_stats:
                    logger.info(f"      Records: {fe_stats[table]['total_records']:,}")
                    logger.info(f"      Range: {fe_stats[table]['oldest_record']} to {fe_stats[table]['newest_record']}")
                logger.info(f"   cp_backtest_h:")
                logger.info(f"      Records: {bt_stats['total_records']:,}")
                logger.info(f"      Range: {bt_stats['oldest_record']} to {bt_stats['newest_record']}")

                if table in fe_stats:
                    missing_records = fe_stats[table]['total_records'] - bt_stats['total_records']
                    logger.info(f"   Difference: {missing_records:,} records {'missing from' if missing_records > 0 else 'extra in'} cp_backtest_h")
            else:
                logger.warning(f"   cp_backtest_h.{table} is empty!")
        except Exception as e:
            logger.error(f"   Error checking cp_backtest_h: {e}")

    # Summary
    logger.info(f"\n{'='*70}")
    logger.info("Audit Summary")
    logger.info(f"{'='*70}")

    if ohlcv_stats:
        logger.info(f"OHLCV Data Available:")
        logger.info(f"   Date Range: {ohlcv_stats['oldest_record']} to {ohlcv_stats['newest_record']}")
        logger.info(f"   Total Records: {ohlcv_stats['total_records']:,}")
        logger.info(f"   Ready for processing: YES")
    else:
        logger.error("OHLCV Data: NOT AVAILABLE - Cannot proceed with backfill")

    logger.info(f"\nExecution Time: {time.time() - start_time:.2f} seconds")

except Exception as e:
    logger.error(f"Fatal error: {e}")
    raise

finally:
    if 'engine_cpai' in locals():
        engine_cpai.dispose()
    if 'engine_backtest' in locals():
        engine_backtest.dispose()
    logger.info("Database connections closed")
