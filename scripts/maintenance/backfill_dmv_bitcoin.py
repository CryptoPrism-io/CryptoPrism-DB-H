#!/usr/bin/env python3
"""
Backfill FE_DMV_BITCOIN table for cp_backtest_h database
Extracts historical bitcoin data from FE_DMV_ALL and creates FE_DMV_BITCOIN
"""

import os
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import logging

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("backfill_dmv_bitcoin.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME_AI = os.getenv("DB_NAME", "cp_ai")
DB_NAME_BT = os.getenv("DB_NAME_BT", "cp_backtest_h")

def create_engines():
    """Create database engines"""
    try:
        engine_ai = create_engine(f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME_AI}')
        engine_bt = create_engine(f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME_BT}')

        # Test connections
        with engine_ai.connect() as conn:
            conn.execute(text("SELECT 1"))
        with engine_bt.connect() as conn:
            conn.execute(text("SELECT 1"))

        logger.info(f"✅ Connected to {DB_NAME_AI} and {DB_NAME_BT}")
        return engine_ai, engine_bt
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        raise

def check_bitcoin_exists_in_dmv_all(engine_bt):
    """Check if bitcoin exists in FE_DMV_ALL"""
    try:
        with engine_bt.connect() as conn:
            result = conn.execute(text("""
                SELECT COUNT(*) as count FROM "FE_DMV_ALL" WHERE slug = 'bitcoin'
            """)).fetchone()

        count = result[0]
        logger.info(f"📊 Found {count} bitcoin rows in {DB_NAME_BT}.FE_DMV_ALL")
        return count > 0
    except Exception as e:
        logger.error(f"❌ Error checking bitcoin in FE_DMV_ALL: {e}")
        return False

def extract_bitcoin_from_dmv_all(engine_bt):
    """Extract all bitcoin data from FE_DMV_ALL"""
    try:
        logger.info("📥 Extracting bitcoin data from FE_DMV_ALL...")

        query = """
            SELECT * FROM "FE_DMV_ALL"
            WHERE slug = 'bitcoin'
            ORDER BY timestamp DESC
        """

        with engine_bt.connect() as conn:
            bitcoin_df = pd.read_sql_query(query, conn)

        logger.info(f"✅ Extracted {len(bitcoin_df)} bitcoin records")

        if len(bitcoin_df) > 0:
            logger.info(f"   Date range: {bitcoin_df['timestamp'].min()} to {bitcoin_df['timestamp'].max()}")
            logger.info(f"   NULL timestamps: {bitcoin_df['timestamp'].isna().sum()}")

        return bitcoin_df
    except Exception as e:
        logger.error(f"❌ Error extracting bitcoin data: {e}")
        raise

def check_dmv_bitcoin_exists(engine_bt):
    """Check if FE_DMV_BITCOIN table already exists"""
    try:
        with engine_bt.connect() as conn:
            result = conn.execute(text("""
                SELECT EXISTS(
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'FE_DMV_BITCOIN'
                )
            """)).fetchone()

        exists = result[0]
        if exists:
            with engine_bt.connect() as conn:
                count = conn.execute(text("""
                    SELECT COUNT(*) FROM "FE_DMV_BITCOIN"
                """)).fetchone()[0]
            logger.info(f"ℹ️  FE_DMV_BITCOIN already exists with {count} rows")
        else:
            logger.info("ℹ️  FE_DMV_BITCOIN table does not exist (will be created)")

        return exists
    except Exception as e:
        logger.error(f"❌ Error checking FE_DMV_BITCOIN: {e}")
        raise

def fill_null_timestamps(df, engine_bt):
    """Fill NULL timestamps using related signal tables"""
    if df['timestamp'].isna().sum() == 0:
        logger.info("✅ No NULL timestamps to fill")
        return df

    logger.warning(f"⚠️  Found {df['timestamp'].isna().sum()} NULL timestamps")

    try:
        with engine_bt.connect() as conn:
            # Try to get bitcoin timestamps from TVV_SIGNALS
            tvv_query = """
                SELECT DISTINCT timestamp FROM "FE_TVV_SIGNALS"
                WHERE slug = 'bitcoin'
                ORDER BY timestamp DESC
                LIMIT 1
            """
            tvv_result = conn.execute(text(tvv_query)).fetchone()

        if tvv_result and tvv_result[0]:
            latest_ts = tvv_result[0]
            null_count = df['timestamp'].isna().sum()
            df.loc[df['timestamp'].isna(), 'timestamp'] = latest_ts
            logger.info(f"✅ Filled {null_count} NULL timestamps with {latest_ts}")
        else:
            logger.warning("⚠️  Could not find bitcoin timestamp in FE_TVV_SIGNALS")

    except Exception as e:
        logger.warning(f"⚠️  Error filling NULL timestamps: {e}")

    return df

def backfill_dmv_bitcoin(engine_bt, bitcoin_df):
    """Backfill FE_DMV_BITCOIN table"""
    try:
        # Check if table exists and decide action
        table_exists = check_dmv_bitcoin_exists(engine_bt)

        # Clean data
        bitcoin_df = fill_null_timestamps(bitcoin_df, engine_bt)

        logger.info(f"💾 Writing {len(bitcoin_df)} records to FE_DMV_BITCOIN...")

        # Determine if_exists parameter
        if_exists = 'append' if table_exists else 'replace'

        # Write to database
        bitcoin_df.to_sql('FE_DMV_BITCOIN', con=engine_bt, if_exists=if_exists, index=False)

        logger.info(f"✅ FE_DMV_BITCOIN backfilled successfully")

        # Verify
        with engine_bt.connect() as conn:
            count = conn.execute(text("""
                SELECT COUNT(*) FROM "FE_DMV_BITCOIN"
            """)).fetchone()[0]

            null_count = conn.execute(text("""
                SELECT COUNT(*) FROM "FE_DMV_BITCOIN" WHERE timestamp IS NULL
            """)).fetchone()[0]

        logger.info(f"✅ Verification: {count} total rows, {null_count} NULL timestamps")

        return True
    except Exception as e:
        logger.error(f"❌ Error backfilling FE_DMV_BITCOIN: {e}")
        raise

def get_column_comparison(engine_bt):
    """Compare columns between FE_DMV_ALL and FE_DMV_BITCOIN"""
    try:
        with engine_bt.connect() as conn:
            # Get columns from FE_DMV_ALL
            dmv_all_cols = conn.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'FE_DMV_ALL'
                ORDER BY ordinal_position
            """)).fetchall()

            # Get columns from FE_DMV_BITCOIN (if exists)
            dmv_bitcoin_cols = conn.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'FE_DMV_BITCOIN'
                ORDER BY ordinal_position
            """)).fetchall()

        dmv_all_col_names = [col[0] for col in dmv_all_cols]
        dmv_bitcoin_col_names = [col[0] for col in dmv_bitcoin_cols]

        logger.info(f"\n📋 Column Comparison:")
        logger.info(f"   FE_DMV_ALL columns: {len(dmv_all_col_names)}")
        logger.info(f"   FE_DMV_BITCOIN columns: {len(dmv_bitcoin_col_names)}")

        if dmv_bitcoin_col_names:
            missing = set(dmv_all_col_names) - set(dmv_bitcoin_col_names)
            if missing:
                logger.warning(f"   Missing columns in FE_DMV_BITCOIN: {missing}")
    except Exception as e:
        logger.warning(f"⚠️  Could not compare columns: {e}")

def main():
    logger.info("=" * 80)
    logger.info("FE_DMV_BITCOIN Backfill Script")
    logger.info(f"Target Database: {DB_NAME_BT}")
    logger.info("=" * 80)

    try:
        # Create connections
        engine_ai, engine_bt = create_engines()

        # Check if bitcoin exists in FE_DMV_ALL
        if not check_bitcoin_exists_in_dmv_all(engine_bt):
            logger.warning("⚠️  Bitcoin not found in FE_DMV_ALL")
            logger.info("ℹ️  This might indicate FE_DMV_ALL has already been cleaned")
            return False

        # Extract bitcoin data
        bitcoin_df = extract_bitcoin_from_dmv_all(engine_bt)

        if bitcoin_df.empty:
            logger.warning("⚠️  No bitcoin data extracted")
            return False

        # Backfill FE_DMV_BITCOIN
        backfill_dmv_bitcoin(engine_bt, bitcoin_df)

        # Compare columns
        get_column_comparison(engine_bt)

        logger.info("\n" + "=" * 80)
        logger.info("✅ Backfill completed successfully!")
        logger.info("=" * 80)

        return True

    except Exception as e:
        logger.error(f"\n❌ Backfill failed: {e}")
        logger.info("=" * 80)
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
