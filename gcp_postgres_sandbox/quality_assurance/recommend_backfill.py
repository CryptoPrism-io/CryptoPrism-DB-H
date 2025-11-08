#!/usr/bin/env python3
"""
Automated Backfill Recommender
================================
Purpose: Analyze data gaps and generate specific backfill commands with date ranges
Usage: python recommend_backfill.py [--detailed]
"""

import logging
import os
import pandas as pd
from datetime import datetime, timedelta
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

def find_data_gaps():
    """
    Analyze all tables to find data gaps
    Returns list of recommended backfill operations
    """

    engine = create_db_engine()

    logger.info(f"=" * 100)
    logger.info(f"Automated Backfill Recommendation")
    logger.info(f"=" * 100)
    logger.info(f"Scanning database: {DB_NAME_BT}")
    logger.info("")

    recommendations = []

    try:
        with engine.connect() as connection:
            # Check OHLCV vs Signal tables
            tables_to_check = {
                'ohlcv_1h_250_coins': 'Price Data',
                'FE_TVV_SIGNALS': 'TVV Signals',
                'FE_OSCILLATORS_SIGNALS': 'Oscillator Signals',
                'FE_MOMENTUM_SIGNALS': 'Momentum Signals',
                'FE_RATIOS_SIGNALS': 'Ratio Signals',
                'FE_DMV_ALL': 'DMV Aggregation'
            }

            table_stats = {}

            # Get stats for each table
            for table, label in tables_to_check.items():
                query = f"""
                SELECT
                    COUNT(*) as record_count,
                    COUNT(DISTINCT timestamp) as unique_timestamps,
                    MIN(timestamp) as min_date,
                    MAX(timestamp) as max_date
                FROM "{table}"
                """

                try:
                    df = pd.read_sql_query(query, connection)

                    if not df.empty and df['record_count'].values[0] > 0:
                        table_stats[table] = {
                            'label': label,
                            'records': df['record_count'].values[0],
                            'timestamps': df['unique_timestamps'].values[0],
                            'min_date': df['min_date'].values[0],
                            'max_date': df['max_date'].values[0]
                        }
                    else:
                        table_stats[table] = {
                            'label': label,
                            'records': 0,
                            'timestamps': 0,
                            'min_date': None,
                            'max_date': None
                        }
                except Exception as e:
                    logger.error(f"   Error querying {table}: {e}")

            # Display current state
            logger.info("Current Data State:")
            logger.info("-" * 100)

            ohlcv_stats = table_stats.get('ohlcv_1h_250_coins', {})
            ohlcv_max = ohlcv_stats.get('max_date')
            ohlcv_min = ohlcv_stats.get('min_date')

            logger.info(f"OHLCV Data:")
            logger.info(f"   Range: {ohlcv_min} to {ohlcv_max}")
            logger.info(f"   Records: {ohlcv_stats.get('records', 0):,}")
            logger.info(f"   Timestamps: {ohlcv_stats.get('timestamps', 0)}")
            logger.info("")

            logger.info("Signal Tables Status:")
            for table, label in tables_to_check.items():
                if table == 'ohlcv_1h_250_coins':
                    continue

                stats = table_stats.get(table, {})
                max_date = stats.get('max_date')
                records = stats.get('records', 0)

                if max_date and ohlcv_max:
                    days_behind = (ohlcv_max.date() - max_date.date()).days
                    status = "✅ Current" if days_behind <= 1 else f"⚠️  {days_behind} days behind"
                else:
                    status = "❌ Missing" if records == 0 else "?"

                logger.info(f"   {label:<30} Last Update: {max_date} {status}")

            logger.info("-" * 100)
            logger.info("")

            # Generate recommendations
            logger.info("Backfill Recommendations:")
            logger.info("")

            # Check for OHLCV gaps
            ohlcv_expected = (ohlcv_max - ohlcv_min).days + 1
            if ohlcv_expected > 0:
                logger.info(f"1. OHLCV Data Coverage:")
                logger.info(f"   Days with data: {ohlcv_stats.get('timestamps', 0) / 24:.0f} days")
                logger.info(f"   Expected days: {ohlcv_expected} days")

            # Check signal gaps
            signal_gaps_found = False

            for table in ['FE_OSCILLATORS_SIGNALS', 'FE_MOMENTUM_SIGNALS', 'FE_RATIOS_SIGNALS']:
                signal_stats = table_stats.get(table, {})
                signal_max = signal_stats.get('max_date')

                if signal_max and ohlcv_max:
                    gap_days = (ohlcv_max.date() - signal_max.date()).days

                    if gap_days > 1:
                        if not signal_gaps_found:
                            logger.info("")
                            logger.info(f"2. Signal Table Gaps Found:")
                            signal_gaps_found = True

                        # Calculate the start date for backfill
                        backfill_start = signal_max + timedelta(days=1)
                        backfill_end = ohlcv_max - timedelta(days=1)

                        logger.info(f"   {table}:")
                        logger.info(f"      Gap: {gap_days} days (last update: {signal_max})")
                        logger.info(f"      Backfill Range: {backfill_start.date()} to {backfill_end.date()}")

                        recommendations.append({
                            'type': 'signal_backfill',
                            'table': table,
                            'start_date': backfill_start.date(),
                            'end_date': backfill_end.date(),
                            'gap_days': gap_days
                        })

            # Check DMV gaps
            dmv_stats = table_stats.get('FE_DMV_ALL', {})
            dmv_max = dmv_stats.get('max_date')

            if dmv_max and ohlcv_max:
                dmv_gap = (ohlcv_max.date() - dmv_max.date()).days

                if dmv_gap > 1:
                    logger.info("")
                    logger.info(f"3. DMV Aggregation Gap:")
                    logger.info(f"   Gap: {dmv_gap} days (last update: {dmv_max})")

                    recommendations.append({
                        'type': 'dmv_backfill',
                        'start_date': dmv_max.date(),
                        'end_date': ohlcv_max.date(),
                        'gap_days': dmv_gap
                    })

            # Generate execution commands
            if recommendations:
                logger.info("")
                logger.info("=" * 100)
                logger.info("EXECUTION STEPS (Run in order):")
                logger.info("=" * 100)
                logger.info("")

                # Collect date ranges for backfill
                earliest_gap = min([r['start_date'] for r in recommendations if 'start_date' in r], default=None)
                latest_gap = max([r['end_date'] for r in recommendations if 'end_date' in r], default=None)

                if earliest_gap and latest_gap:
                    logger.info(f"# Step 1: Backfill Signal Tables ({earliest_gap} to {latest_gap})")
                    logger.info(f"cd gcp_postgres_sandbox/backfill_scripts/")
                    logger.info(f"python backfill_dmv_tvv_pct.py")
                    logger.info(f"python backfill_dmv_osc_mom_rat.py")
                    logger.info(f"python backfill_dmv_core_historical.py")
                    logger.info("")
                    logger.info(f"# Step 2: Validate with QA Scripts")
                    logger.info(f"cd ../quality_assurance/")
                    logger.info(f"python check_signal_completeness.py --start-date {earliest_gap} --end-date {latest_gap}")
                    logger.info(f"python check_timestamp_gaps_corrected.py")
                    logger.info("")

            else:
                logger.info("")
                logger.info("✅ No gaps detected! All data is current and complete.")

            logger.info("")
            logger.info("=" * 100)
            logger.info("Summary:")
            logger.info(f"   Total Gaps Found: {len(recommendations)}")
            logger.info(f"   Backfill Operations Required: {len([r for r in recommendations if r.get('type') == 'signal_backfill'])}")
            logger.info("=" * 100)

    except Exception as e:
        logger.error(f"❌ Error: {e}")
    finally:
        engine.dispose()

def main():
    find_data_gaps()

if __name__ == "__main__":
    main()
