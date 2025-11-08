#!/usr/bin/env python3
"""
Signal Completeness Checker
=============================
Purpose: Compare OHLCV records vs Signal table records to identify where signals are missing
Usage: python check_signal_completeness.py --start-date 2025-10-01 --end-date 2025-11-04
"""

import argparse
import logging
import os
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Load environment variables
if not os.getenv("GITHUB_ACTIONS"):
    if os.path.exists(".env"):
        load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Database configuration
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME_BT = os.getenv("DB_NAME_BT", "cp_backtest_h")

def create_db_engine():
    """Create database engine"""
    return create_engine(
        f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME_BT}'
    )

def check_signal_completeness(start_date, end_date):
    """
    Compare OHLCV vs Signal tables for completeness

    Args:
        start_date: Start date (YYYY-MM-DD format)
        end_date: End date (YYYY-MM-DD format)
    """

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError as e:
        logger.error(f"❌ Invalid date format: {e}. Use YYYY-MM-DD")
        return

    engine = create_db_engine()

    logger.info(f"=" * 100)
    logger.info(f"Signal Completeness Analysis")
    logger.info(f"=" * 100)
    logger.info(f"Date Range: {start_date} to {end_date}")
    logger.info(f"Database: {DB_NAME_BT}")
    logger.info("")

    signal_tables = [
        'FE_TVV_SIGNALS',
        'FE_OSCILLATORS_SIGNALS',
        'FE_MOMENTUM_SIGNALS',
        'FE_RATIOS_SIGNALS'
    ]

    try:
        with engine.connect() as connection:
            # Get OHLCV record count
            ohlcv_query = f"""
            SELECT
                COUNT(*) as total_records,
                COUNT(DISTINCT timestamp) as unique_timestamps,
                COUNT(DISTINCT slug) as unique_coins
            FROM ohlcv_1h_250_coins
            WHERE timestamp >= '{start_date}'::date
              AND timestamp < '{end_date}'::date + INTERVAL '1 day'
            """

            ohlcv_df = pd.read_sql_query(ohlcv_query, connection)
            ohlcv_records = ohlcv_df['total_records'].values[0]
            ohlcv_timestamps = ohlcv_df['unique_timestamps'].values[0]
            ohlcv_coins = ohlcv_df['unique_coins'].values[0]

            logger.info("OHLCV Source Data:")
            logger.info(f"   Total Records: {ohlcv_records:,}")
            logger.info(f"   Unique Timestamps: {ohlcv_timestamps}")
            logger.info(f"   Unique Coins: {ohlcv_coins}")
            logger.info("")

            # Check each signal table
            logger.info("Signal Table Completeness:")
            logger.info("-" * 100)
            logger.info(f"{'Table':<30} {'Records':<15} {'Timestamps':<15} {'Coins':<10} {'Coverage':<10}")
            logger.info("-" * 100)

            missing_gaps = []

            for table in signal_tables:
                signal_query = f"""
                SELECT
                    COUNT(*) as total_records,
                    COUNT(DISTINCT timestamp) as unique_timestamps,
                    COUNT(DISTINCT slug) as unique_coins
                FROM "{table}"
                WHERE timestamp >= '{start_date}'::date
                  AND timestamp < '{end_date}'::date + INTERVAL '1 day'
                """

                try:
                    signal_df = pd.read_sql_query(signal_query, connection)

                    if signal_df.empty or signal_df['total_records'].values[0] == 0:
                        coverage = 0
                        missing = ohlcv_records
                        signal_records = 0
                        signal_timestamps = 0
                    else:
                        signal_records = signal_df['total_records'].values[0]
                        signal_timestamps = signal_df['unique_timestamps'].values[0]
                        coverage = (signal_records / ohlcv_records * 100) if ohlcv_records > 0 else 0
                        missing = ohlcv_records - signal_records

                    status = "✅" if coverage >= 95 else ("⚠️ " if coverage >= 50 else "❌")

                    logger.info(
                        f"{table:<30} {signal_records:<15,} {signal_timestamps:<15} "
                        f"{signal_df['unique_coins'].values[0] if signal_records > 0 else 0:<10} "
                        f"{coverage:.1f}% {status:<5}"
                    )

                    if coverage < 100:
                        missing_gaps.append({
                            'table': table,
                            'missing_records': missing,
                            'coverage': coverage
                        })

                except Exception as e:
                    logger.error(f"   ❌ Error querying {table}: {e}")

            # Summary
            logger.info("-" * 100)

            if missing_gaps:
                logger.info("")
                logger.warning("Tables Requiring Backfill:")
                for gap in missing_gaps:
                    logger.warning(
                        f"   {gap['table']}: {gap['missing_records']:,} records missing "
                        f"({100-gap['coverage']:.1f}% gap)"
                    )
                logger.info("")
                logger.info("Recommended Action:")
                logger.info("   Run backfill_dmv_osc_mom_rat.py to regenerate signal tables")
                logger.info("   Then run backfill_dmv_core_historical.py to aggregate signals")
            else:
                logger.info("")
                logger.info("✅ All signal tables are complete for this date range!")

    except Exception as e:
        logger.error(f"❌ Error: {e}")
    finally:
        engine.dispose()

def main():
    parser = argparse.ArgumentParser(
        description="Check if signal tables match OHLCV data for date range"
    )
    parser.add_argument(
        "--start-date",
        required=True,
        help="Start date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="End date (YYYY-MM-DD)"
    )

    args = parser.parse_args()

    check_signal_completeness(args.start_date, args.end_date)

if __name__ == "__main__":
    main()
