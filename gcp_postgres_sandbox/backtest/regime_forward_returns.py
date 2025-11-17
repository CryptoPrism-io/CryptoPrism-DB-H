"""
Regime-Based Market Prediction: Forward Returns & Labeling
===========================================================

This module calculates forward returns at multiple horizons and creates regime labels
based on Bitcoin's performance (benchmark).

Regime Definition:
- BAD if BTC drops >= 3% in next 24h, >= 4% in 48h, >= 5% in 72h
- NORMAL otherwise

No look-ahead bias: Only past data is used for features.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Tuple, Dict, List
import logging
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from utils import get_db_engines
from utils.database_utils import safe_query, create_table_if_not_exists

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================

# Regime definition: BTC return thresholds (negative = BAD)
REGIME_THRESHOLDS = {
    '24h': -0.03,   # BAD if BTC drops >= 3%
    '48h': -0.04,   # BAD if BTC drops >= 4%
    '72h': -0.05    # BAD if BTC drops >= 5%
}

HORIZONS = [24, 48, 72]  # Hours ahead to predict


# ============================================================================
# DATABASE MANAGEMENT
# ============================================================================

class RegimeForwardReturnsCalculator:
    """Calculate forward returns and regime labels from historical OHLCV data"""

    def __init__(self):
        """Initialize database connections"""
        try:
            engines = get_db_engines()
            self.engine_backtest = engines[2]  # cp_backtest_h
            logger.info("✓ Database connections established")
        except Exception as e:
            logger.error(f"✗ Database connection failed: {e}")
            raise

    # ========================================================================
    # DATA VALIDATION
    # ========================================================================

    def validate_data_availability(self) -> Dict:
        """
        Check if sufficient OHLCV data exists for forward return calculation
        """
        logger.info("=" * 80)
        logger.info("VALIDATING DATA AVAILABILITY")
        logger.info("=" * 80)

        try:
            query = """
            SELECT
                COUNT(*) as total_records,
                COUNT(DISTINCT slug) as unique_coins,
                MIN(timestamp) as earliest_data,
                MAX(timestamp) as latest_data,
                (MAX(timestamp) - MIN(timestamp)) as duration_days
            FROM "ohlcv_1h_250_coins"
            """
            result = safe_query(self.engine_backtest, query)

            if result.empty:
                logger.error("No OHLCV data found in database!")
                return {}

            stats = result.iloc[0]
            logger.info(f"✓ Total OHLCV records: {stats['total_records']:,.0f}")
            logger.info(f"✓ Unique coins: {stats['unique_coins']:.0f}")
            logger.info(f"✓ Data range: {stats['earliest_data']} to {stats['latest_data']}")
            logger.info(f"✓ Coverage: {stats['duration_days'].days} days")

            # Check Bitcoin data completeness
            btc_query = """
            SELECT
                COUNT(*) as btc_records,
                MIN(timestamp) as btc_start,
                MAX(timestamp) as btc_end
            FROM "ohlcv_1h_250_coins"
            WHERE slug = 'bitcoin'
            """
            btc_result = safe_query(self.engine_backtest, btc_query)

            if not btc_result.empty:
                btc_stats = btc_result.iloc[0]
                logger.info(f"✓ Bitcoin records: {btc_stats['btc_records']:,.0f}")
                logger.info(f"✓ Bitcoin data: {btc_stats['btc_start']} to {btc_stats['btc_end']}")
            else:
                logger.warning("✗ Bitcoin data not found!")

            return {
                'total_records': stats['total_records'],
                'unique_coins': stats['unique_coins'],
                'earliest_data': stats['earliest_data'],
                'latest_data': stats['latest_data'],
                'duration_days': stats['duration_days'].days
            }

        except Exception as e:
            logger.error(f"✗ Validation failed: {e}")
            return {}

    # ========================================================================
    # FORWARD RETURNS CALCULATION
    # ========================================================================

    def calculate_forward_returns(self) -> pd.DataFrame:
        """
        Calculate forward returns for all coins at multiple horizons.

        For each (slug, timestamp), compute:
        - return_24h = (close[t+24h] - close[t]) / close[t]
        - return_48h = (close[t+48h] - close[t]) / close[t]
        - return_72h = (close[t+72h] - close[t]) / close[t]

        Returns:
            DataFrame with columns: slug, timestamp, return_24h, return_48h, return_72h
        """
        logger.info("=" * 80)
        logger.info("CALCULATING FORWARD RETURNS")
        logger.info("=" * 80)

        try:
            # Query all OHLCV data
            logger.info("Fetching OHLCV data from database...")
            query = """
            SELECT slug, timestamp, close
            FROM "ohlcv_1h_250_coins"
            ORDER BY slug, timestamp
            """
            df = safe_query(self.engine_backtest, query)
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)

            logger.info(f"✓ Loaded {len(df):,.0f} OHLCV records")
            logger.info(f"✓ Coins: {df['slug'].nunique()}")
            logger.info(f"✓ Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")

            # Calculate forward returns per coin
            results = []

            for slug in df['slug'].unique():
                coin_data = df[df['slug'] == slug].sort_values('timestamp').reset_index(drop=True)

                forward_returns = pd.DataFrame({
                    'slug': slug,
                    'timestamp': coin_data['timestamp'].values,
                    'close': coin_data['close'].values,
                })

                # Calculate forward returns (align with future prices)
                for horizon_h in HORIZONS:
                    return_col = f'return_{horizon_h}h'

                    # Look ahead (future close / current close - 1)
                    future_close = coin_data['close'].shift(-horizon_h).values
                    current_close = coin_data['close'].values

                    # Only calculate where future data exists (avoid NaN at end)
                    returns = np.where(
                        pd.notna(future_close),
                        (future_close - current_close) / current_close,
                        np.nan
                    )

                    forward_returns[return_col] = returns

                results.append(forward_returns)

                if len(results) % 50 == 0:
                    logger.info(f"  Processed {len(results)} coins...")

            df_returns = pd.concat(results, ignore_index=True)

            # Remove rows with NaN forward returns (last N hours of data)
            df_returns_clean = df_returns.dropna(subset=['return_24h', 'return_48h', 'return_72h'])

            logger.info(f"✓ Calculated forward returns for {len(df_returns_clean):,.0f} records")
            logger.info(f"  Dropped {len(df_returns) - len(df_returns_clean):,.0f} records (missing future prices)")

            return df_returns_clean

        except Exception as e:
            logger.error(f"✗ Forward returns calculation failed: {e}")
            raise

    # ========================================================================
    # REGIME LABELING
    # ========================================================================

    def create_regime_labels(self, df_returns: pd.DataFrame) -> pd.DataFrame:
        """
        Create regime labels based on Bitcoin's forward returns.

        Regime = 1 (BAD) if Bitcoin return >= threshold (negative)
        Regime = 0 (NORMAL) otherwise

        Args:
            df_returns: DataFrame with forward returns

        Returns:
            DataFrame with regime labels added
        """
        logger.info("=" * 80)
        logger.info("CREATING REGIME LABELS (BITCOIN BENCHMARK)")
        logger.info("=" * 80)

        try:
            # Get Bitcoin returns
            btc_returns = df_returns[df_returns['slug'] == 'bitcoin'].copy()
            btc_returns = btc_returns.set_index('timestamp')[['return_24h', 'return_48h', 'return_72h']]

            logger.info(f"✓ Bitcoin records for labeling: {len(btc_returns)}")

            # Create labels
            df_labeled = df_returns.copy()

            # For each record, find corresponding Bitcoin regime at same timestamp
            df_labeled = df_labeled.merge(
                btc_returns.rename(columns={
                    'return_24h': 'btc_return_24h',
                    'return_48h': 'btc_return_48h',
                    'return_72h': 'btc_return_72h'
                }),
                left_on='timestamp',
                right_index=True,
                how='left'
            )

            # Label regimes
            logger.info("Creating regime labels...")
            logger.info(f"  24h threshold: {REGIME_THRESHOLDS['24h']} (BAD if BTC drops >= 3%)")
            logger.info(f"  48h threshold: {REGIME_THRESHOLDS['48h']} (BAD if BTC drops >= 4%)")
            logger.info(f"  72h threshold: {REGIME_THRESHOLDS['72h']} (BAD if BTC drops >= 5%)")

            df_labeled['regime_24h'] = (df_labeled['btc_return_24h'] <= REGIME_THRESHOLDS['24h']).astype(int)
            df_labeled['regime_48h'] = (df_labeled['btc_return_48h'] <= REGIME_THRESHOLDS['48h']).astype(int)
            df_labeled['regime_72h'] = (df_labeled['btc_return_72h'] <= REGIME_THRESHOLDS['72h']).astype(int)

            # Statistics
            for horizon in ['24h', '48h', '72h']:
                bad_count = (df_labeled[f'regime_{horizon}'] == 1).sum()
                bad_pct = 100 * bad_count / len(df_labeled)
                logger.info(f"✓ Regime {horizon}: {bad_count:,.0f} BAD ({bad_pct:.1f}%), {len(df_labeled) - bad_count:,.0f} NORMAL ({100-bad_pct:.1f}%)")

            return df_labeled

        except Exception as e:
            logger.error(f"✗ Regime labeling failed: {e}")
            raise

    # ========================================================================
    # DATA STORAGE
    # ========================================================================

    def save_to_database(self, df_labeled: pd.DataFrame) -> bool:
        """
        Save forward returns and regime labels to database table.

        Table: regime_forward_returns
        """
        logger.info("=" * 80)
        logger.info("SAVING TO DATABASE")
        logger.info("=" * 80)

        try:
            # Drop table if exists to ensure fresh data
            drop_query = "DROP TABLE IF EXISTS regime_forward_returns CASCADE"
            with self.engine_backtest.connect() as conn:
                from sqlalchemy import text
                conn.execute(text(drop_query))
                conn.commit()
            logger.info("✓ Old table dropped")

            # Create table
            create_query = """
            CREATE TABLE regime_forward_returns (
                id SERIAL PRIMARY KEY,
                slug VARCHAR(50) NOT NULL,
                timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                close FLOAT NOT NULL,
                return_24h FLOAT,
                return_48h FLOAT,
                return_72h FLOAT,
                btc_return_24h FLOAT,
                btc_return_48h FLOAT,
                btc_return_72h FLOAT,
                regime_24h INTEGER,
                regime_48h INTEGER,
                regime_72h INTEGER,
                UNIQUE(slug, timestamp)
            );

            CREATE INDEX IF NOT EXISTS idx_regime_returns_slug_ts
                ON regime_forward_returns(slug, timestamp);
            CREATE INDEX IF NOT EXISTS idx_regime_returns_regime
                ON regime_forward_returns(regime_24h, regime_48h, regime_72h);
            """

            with self.engine_backtest.connect() as conn:
                from sqlalchemy import text
                for statement in create_query.split(';'):
                    if statement.strip():
                        conn.execute(text(statement))
                conn.commit()

            logger.info("✓ Table created/verified")

            # Insert data using pandas to_sql with small chunks
            logger.info(f"Inserting {len(df_labeled):,.0f} records...")

            chunk_size = 10000
            total_chunks = (len(df_labeled) + chunk_size - 1) // chunk_size

            for i in range(0, len(df_labeled), chunk_size):
                chunk = df_labeled.iloc[i:i+chunk_size]
                chunk_num = (i // chunk_size) + 1

                try:
                    chunk.to_sql(
                        'regime_forward_returns',
                        self.engine_backtest,
                        if_exists='append',
                        index=False,
                        method='multi',
                        chunksize=1000
                    )
                    logger.info(f"  ✓ Inserted {min(i + chunk_size, len(df_labeled)):,.0f}/{len(df_labeled):,.0f} records...")
                except Exception as e:
                    logger.warning(f"  Chunk {chunk_num} insert error: {str(e)[:100]}")
                    # Try smaller chunks if multi fails
                    try:
                        chunk.to_sql(
                            'regime_forward_returns',
                            self.engine_backtest,
                            if_exists='append',
                            index=False,
                            chunksize=500
                        )
                        logger.info(f"  ✓ Inserted {min(i + chunk_size, len(df_labeled)):,.0f}/{len(df_labeled):,.0f} records (smaller chunks)...")
                    except Exception as e2:
                        logger.error(f"  ✗ Chunk {chunk_num} failed even with smaller chunks: {e2}")
                        raise

            logger.info("✓ Data saved successfully")

            # Verify
            verify_query = "SELECT COUNT(*) as record_count FROM regime_forward_returns"
            result = safe_query(self.engine_backtest, verify_query)
            logger.info(f"✓ Verified: {result.iloc[0]['record_count']:,.0f} records in database")

            return True

        except Exception as e:
            logger.error(f"✗ Database save failed: {e}")
            raise

    # ========================================================================
    # STATISTICS & VALIDATION
    # ========================================================================

    def validate_calculations(self, df_labeled: pd.DataFrame) -> Dict:
        """
        Validate the calculated returns and labels.
        """
        logger.info("=" * 80)
        logger.info("VALIDATING CALCULATIONS")
        logger.info("=" * 80)

        try:
            stats = {
                'total_records': len(df_labeled),
                'unique_coins': df_labeled['slug'].nunique(),
                'date_range': f"{df_labeled['timestamp'].min()} to {df_labeled['timestamp'].max()}",
                'null_returns_24h': df_labeled['return_24h'].isna().sum(),
                'null_returns_48h': df_labeled['return_48h'].isna().sum(),
                'null_returns_72h': df_labeled['return_72h'].isna().sum(),
            }

            for horizon in ['24h', '48h', '72h']:
                col = f'return_{horizon}'
                stats[f'mean_return_{horizon}'] = df_labeled[col].mean()
                stats[f'std_return_{horizon}'] = df_labeled[col].std()
                stats[f'min_return_{horizon}'] = df_labeled[col].min()
                stats[f'max_return_{horizon}'] = df_labeled[col].max()

            logger.info(f"✓ Total records: {stats['total_records']:,.0f}")
            logger.info(f"✓ Unique coins: {stats['unique_coins']}")
            logger.info(f"✓ Date range: {stats['date_range']}")
            logger.info(f"\nReturn Statistics:")
            for horizon in ['24h', '48h', '72h']:
                logger.info(f"  {horizon}:")
                logger.info(f"    Mean: {stats[f'mean_return_{horizon}']:.4f}")
                logger.info(f"    Std:  {stats[f'std_return_{horizon}']:.4f}")
                logger.info(f"    Min:  {stats[f'min_return_{horizon}']:.4f}")
                logger.info(f"    Max:  {stats[f'max_return_{horizon}']:.4f}")

            return stats

        except Exception as e:
            logger.error(f"✗ Validation failed: {e}")
            return {}


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution function"""
    logger.info("\n" + "=" * 80)
    logger.info("REGIME FORWARD RETURNS & LABELING")
    logger.info("=" * 80)

    try:
        # Initialize calculator
        calculator = RegimeForwardReturnsCalculator()

        # Step 1: Validate data
        availability = calculator.validate_data_availability()
        if not availability:
            logger.error("Insufficient data availability. Exiting.")
            return False

        # Step 2: Calculate forward returns
        df_returns = calculator.calculate_forward_returns()

        # Step 3: Create regime labels
        df_labeled = calculator.create_regime_labels(df_returns)

        # Step 4: Save to database
        calculator.save_to_database(df_labeled)

        # Step 5: Validate
        stats = calculator.validate_calculations(df_labeled)

        logger.info("\n" + "=" * 80)
        logger.info("✅ FORWARD RETURNS & REGIME LABELS CREATED SUCCESSFULLY")
        logger.info("=" * 80)
        logger.info(f"\nNext steps:")
        logger.info(f"1. Run: regime_feature_extraction.py (extract 108h rolling features)")
        logger.info(f"2. Run: regime_ml_models.py (train regime prediction models)")
        logger.info(f"3. Run: regime_portfolio_backtest.py (backtest portfolio strategy)")

        return True

    except Exception as e:
        logger.error(f"\n✗ FAILED: {e}")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
