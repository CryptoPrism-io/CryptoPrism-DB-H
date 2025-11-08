#!/usr/bin/env python3
"""
Check Data Gaps for Specific Date Range
========================================
Purpose: Quickly analyze hourly data coverage for a specific date range without full database scan
Usage: python check_daterange_gaps.py --start-date 2025-10-01 --end-date 2025-10-15 --table ohlcv_1h_250_coins
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

def analyze_date_range(start_date, end_date, table_name):
    """
    Analyze hourly data coverage for specific date range

    Args:
        start_date: Start date (YYYY-MM-DD format)
        end_date: End date (YYYY-MM-DD format)
        table_name: Table to analyze
    """

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError as e:
        logger.error(f"❌ Invalid date format: {e}. Use YYYY-MM-DD")
        return

    engine = create_db_engine()

    logger.info(f"=" * 80)
    logger.info(f"Date Range Gap Analysis: {table_name}")
    logger.info(f"=" * 80)
    logger.info(f"Date Range: {start_date} to {end_date}")
    logger.info(f"Database: {DB_NAME_BT}")
    logger.info("")

    try:
        with engine.connect() as connection:
            # Query data for date range
            query = f"""
            SELECT
                DATE(timestamp) as date,
                COUNT(DISTINCT timestamp) as unique_hours,
                COUNT(DISTINCT slug) as unique_coins,
                COUNT(*) as total_records,
                MIN(timestamp) as earliest_record,
                MAX(timestamp) as latest_record
            FROM "{table_name}"
            WHERE timestamp >= '{start_date}'::date
              AND timestamp < '{end_date}'::date + INTERVAL '1 day'
            GROUP BY DATE(timestamp)
            ORDER BY date ASC
            """

            result_df = pd.read_sql_query(query, connection)

            if result_df.empty:
                logger.warning(f"⚠️  No data found for {table_name} between {start_date} and {end_date}")
                return

            # Display daily summary
            logger.info("Daily Hourly Coverage:")
            logger.info("-" * 80)
            logger.info(f"{'Date':<12} {'Hours':<10} {'Coins':<10} {'Expected':<10} {'Status':<15}")
            logger.info("-" * 80)

            for _, row in result_df.iterrows():
                date_val = row['date']
                hours = int(row['unique_hours'])
                coins = int(row['unique_coins'])
                expected = 24
                status = "✅ OK" if hours == expected else f"⚠️  LOW ({hours}/24)"

                logger.info(f"{str(date_val):<12} {hours:<10} {coins:<10} {expected:<10} {status:<15}")

            # Overall statistics
            logger.info("-" * 80)
            total_hours = result_df['unique_hours'].sum()
            expected_hours = len(result_df) * 24
            coverage = (total_hours / expected_hours * 100) if expected_hours > 0 else 0

            logger.info("")
            logger.info("Summary Statistics:")
            logger.info(f"   Total Days: {len(result_df)}")
            logger.info(f"   Total Hours: {int(total_hours)}")
            logger.info(f"   Expected Hours: {expected_hours}")
            logger.info(f"   Coverage: {coverage:.2f}%")
            logger.info(f"   Total Records: {int(result_df['total_records'].sum())}")
            logger.info(f"   Avg Coins per Hour: {result_df['total_records'].sum() / total_hours:.0f}")

            # Identify problematic days
            low_coverage_days = result_df[result_df['unique_hours'] < 24]
            if not low_coverage_days.empty:
                logger.info("")
                logger.warning("Days with Low Coverage (< 24 hours):")
                for _, row in low_coverage_days.iterrows():
                    missing = 24 - int(row['unique_hours'])
                    logger.warning(f"   {row['date']}: {int(row['unique_hours'])}/24 hours (missing {missing})")

    except Exception as e:
        logger.error(f"❌ Error querying database: {e}")
    finally:
        engine.dispose()

def main():
    parser = argparse.ArgumentParser(
        description="Check hourly data gaps for specific date range"
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
    parser.add_argument(
        "--table",
        default="ohlcv_1h_250_coins",
        help="Table to analyze (default: ohlcv_1h_250_coins)"
    )

    args = parser.parse_args()

    analyze_date_range(args.start_date, args.end_date, args.table)

if __name__ == "__main__":
    main()
