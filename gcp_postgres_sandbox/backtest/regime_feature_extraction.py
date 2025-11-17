"""
Regime Feature Extraction: 108h Rolling Window Analysis
=======================================================

Extract ~150+ time-series features from 108-hour rolling windows subdivided into
9 blocks of 12 hours each.

Feature Categories:
1. Per-Block Features (9 blocks): Durability, Momentum, Conviction, Valuation
2. Cross-Block Trends: Evolution, acceleration, reversals across blocks
3. Market-Wide Features: Aggregate statistics across coins
4. High-Conviction Features: Signal confluence metrics
5. Critical Thresholds: Rule-based trigger flags

This module creates the feature matrix for ML model training without look-ahead bias.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import logging
from pathlib import Path
import sys
from scipy import stats

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import get_db_engines
from backtest.utils.database_utils import safe_query, create_table_if_not_exists

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================

# Window configuration: 108 hours = 9 blocks of 12 hours
WINDOW_HOURS = 108
BLOCK_HOURS = 12
NUM_BLOCKS = WINDOW_HOURS // BLOCK_HOURS  # 9 blocks
FEATURE_TIMESTAMP_OFFSET = timedelta(minutes=59, seconds=59)

# Feature thresholds for critical conditions
CRITICAL_THRESHOLDS = {
    'share_poor_high': 0.75,          # >75% coins are POOR rated
    'share_good_low': 0.15,           # <15% coins are GOOD rated
    'net_conviction_low': -80,        # Strong net bearish conviction
    'dmv_composite_critical': -15,    # Very weak overall quality
    'momentum_collapse': -70,         # Momentum near floor
}


# ============================================================================
# FEATURE EXTRACTION ENGINE
# ============================================================================

class RegimeFeatureExtractor:
    """Extract time-series features from 108h rolling windows"""

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
    # DATA LOADING
    # ========================================================================

    def load_dmv_data(self, start_date: str, end_date: str, slug_filter: Optional[str] = None) -> pd.DataFrame:
        """
        Load DMV data (Durability, Momentum, Valuation scores) for feature extraction.

        Returns:
            DataFrame with columns: slug, timestamp, Durability_Score, Momentum_Score, Valuation_Score
        """
        logger.info(f"Loading DMV data from {start_date} to {end_date}...")

        try:
            query = f"""
            SELECT slug, timestamp,
                   "d_rat_beta_bin", "d_rat_pain_bin",
                   "d_tvv_ema21_108", "d_tvv_ema9_18",
                   "d_tvv_sma21_108", "d_tvv_sma9_18",
                   "m_mom_cmo_bin", "m_mom_mom_bin", "m_mom_roc_bin",
                   "m_mom_smi_bin", "m_mom_williams_%%_bin",
                   "m_osc_adx_bin", "m_osc_ao_bin", "m_osc_cci_bin",
                   "m_osc_macd_crossover_bin", "m_osc_trix_bin", "m_osc_uo_bin",
                   "m_rat_alpha_bin", "m_rat_ror_bin", "m_rat_win_rate_bin",
                   "m_tvv_cmf", "m_tvv_obv_1d_binary",
                   "v_rat_common_sense_bin", "v_rat_information_bin",
                   "v_rat_sharpe_bin", "v_rat_sortino_bin",
                   "v_rat_teynor_bin", "v_rat_win_loss_bin",
                   bullish, bearish, neutral
            FROM "FE_DMV_ALL"
            WHERE timestamp >= '{start_date}' AND timestamp < '{end_date}'
            ORDER BY timestamp, slug
            """

            df = safe_query(self.engine_backtest, query)
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
            df = self._enrich_dmv_scores(df)
            if slug_filter:
                df = df[df['slug'] == slug_filter]

            logger.info(f"✓ Loaded {len(df):,.0f} DMV records")
            logger.info(f"✓ Coins: {df['slug'].nunique()}")

            return df

        except Exception as e:
            logger.error(f"✗ Data loading failed: {e}")
            raise

    # ========================================================================
    # DMV SCORE DERIVATION
    # ========================================================================

    @staticmethod
    def _enrich_dmv_scores(df: pd.DataFrame) -> pd.DataFrame:
        """
        Derive Durability, Momentum, and Valuation scores from the raw DMV signals.
        """
        score_map = {
            'Durability_Score': 'd_',
            'Momentum_Score': 'm_',
            'Valuation_Score': 'v_'
        }

        for score_col, prefix in score_map.items():
            cols = [col for col in df.columns if col.startswith(prefix)]
            if not cols:
                df[score_col] = 0.0
                continue

            numeric_signals = df[cols].apply(pd.to_numeric, errors='coerce')
            df[score_col] = numeric_signals.mean(axis=1, skipna=True).fillna(0) * 100

        return df

    # ========================================================================
    # PER-BLOCK FEATURES
    # ========================================================================

    def extract_per_block_features(self, df: pd.DataFrame, coin: str, timestamp: pd.Timestamp) -> Dict:
        """
        Extract features within each 12-hour block of the 108h window.

        For each block i (0-8):
        - Durability stats (mean, std, trend)
        - Momentum stats
        - Conviction stats
        - Valuation stats
        """
        features = {}

        # Get 108-hour window data for this coin
        window_start = timestamp - timedelta(hours=WINDOW_HOURS)
        window_data = df[
            (df['slug'] == coin) &
            (df['timestamp'] > window_start) &
            (df['timestamp'] <= timestamp)
        ].sort_values('timestamp')

        if len(window_data) == 0:
            return {}

        # Split into blocks
        blocks = []
        for block_idx in range(NUM_BLOCKS):
            block_start = window_start + timedelta(hours=block_idx * BLOCK_HOURS)
            block_end = block_start + timedelta(hours=BLOCK_HOURS)

            block_data = window_data[
                (window_data['timestamp'] > block_start) &
                (window_data['timestamp'] <= block_end)
            ]
            blocks.append(block_data)

        # Extract features per block
        for block_idx, block_data in enumerate(blocks):
            if len(block_data) == 0:
                continue

            # Durability features
            features[f'b{block_idx}_durability_mean'] = block_data['Durability_Score'].mean()
            features[f'b{block_idx}_durability_std'] = block_data['Durability_Score'].std()
            features[f'b{block_idx}_durability_trend'] = self._calculate_trend(
                block_data['Durability_Score'].values
            )

            # Momentum features
            features[f'b{block_idx}_momentum_mean'] = block_data['Momentum_Score'].mean()
            features[f'b{block_idx}_momentum_std'] = block_data['Momentum_Score'].std()
            features[f'b{block_idx}_momentum_positive_ratio'] = (
                (block_data['Momentum_Score'] > 50).sum() / len(block_data)
            )

            # Conviction features (bullish/bearish signal counts)
            features[f'b{block_idx}_bullish_mean'] = block_data['bullish'].mean()
            features[f'b{block_idx}_bearish_mean'] = block_data['bearish'].mean()
            net_conviction = block_data['bullish'].mean() - np.abs(block_data['bearish'].mean())
            features[f'b{block_idx}_net_conviction'] = net_conviction

            total_signals = (
                block_data['bullish'].mean() +
                np.abs(block_data['bearish'].mean())
            )
            features[f'b{block_idx}_conviction_ratio'] = (
                block_data['bullish'].mean() / total_signals if total_signals > 0 else 0.5
            )

            # Valuation features
            features[f'b{block_idx}_valuation_mean'] = block_data['Valuation_Score'].mean()
            features[f'b{block_idx}_valuation_std'] = block_data['Valuation_Score'].std()

        return features

    @staticmethod
    def _calculate_trend(values: np.ndarray) -> float:
        """
        Calculate linear trend (slope) of values.
        Positive = increasing, Negative = decreasing
        """
        if len(values) < 2 or np.isnan(values).all():
            return 0.0

        x = np.arange(len(values))
        y = np.array(values)

        # Remove NaN values
        mask = ~np.isnan(y)
        if mask.sum() < 2:
            return 0.0

        x_clean = x[mask]
        y_clean = y[mask]

        # Linear regression slope
        try:
            slope, _ = np.polyfit(x_clean, y_clean, 1)
            return float(slope)
        except:
            return 0.0

    # ========================================================================
    # CROSS-BLOCK TREND FEATURES
    # ========================================================================

    def extract_cross_block_features(self, per_block_features: Dict, coin: str, timestamp: pd.Timestamp) -> Dict:
        """
        Extract features that span across multiple blocks (trend analysis).

        Includes:
        - Durability/Momentum evolution across blocks
        - Acceleration (2nd derivative)
        - Reversals and regime changes
        - Deterioration patterns
        """
        features = {}

        # Extract block means
        durability_means = [
            per_block_features.get(f'b{i}_durability_mean', np.nan)
            for i in range(NUM_BLOCKS)
        ]
        momentum_means = [
            per_block_features.get(f'b{i}_momentum_mean', np.nan)
            for i in range(NUM_BLOCKS)
        ]
        conviction_nets = [
            per_block_features.get(f'b{i}_net_conviction', np.nan)
            for i in range(NUM_BLOCKS)
        ]
        valuation_means = [
            per_block_features.get(f'b{i}_valuation_mean', np.nan)
            for i in range(NUM_BLOCKS)
        ]

        # Durability evolution
        features['durability_trend'] = self._calculate_trend(np.array(durability_means))
        features['durability_acceleration'] = self._calculate_acceleration(np.array(durability_means))
        features['durability_volatility'] = np.nanstd(durability_means)
        features['durability_collapse_flag'] = 1 if (
            np.nanmean(durability_means[-3:]) < (np.nanmean(durability_means[:3]) - 20)
        ) else 0

        # Momentum evolution
        features['momentum_trend'] = self._calculate_trend(np.array(momentum_means))
        features['momentum_acceleration'] = self._calculate_acceleration(np.array(momentum_means))
        features['momentum_reversal_count'] = self._count_reversals(np.array(momentum_means))

        # Conviction evolution (critical for market turning points)
        features['conviction_trend'] = self._calculate_trend(np.array(conviction_nets))
        features['conviction_deterioration'] = conviction_nets[-1] - conviction_nets[0] if len(conviction_nets) >= 2 else 0

        # Flags for critical conviction patterns
        features['conviction_collapse_flag'] = 1 if (
            np.nanmean(conviction_nets[-3:]) < CRITICAL_THRESHOLDS['net_conviction_low']
        ) else 0
        features['conviction_surge_flag'] = 1 if (
            np.nanmean(conviction_nets[-3:]) > 50
        ) else 0

        # Valuation evolution
        features['valuation_trend'] = self._calculate_trend(np.array(valuation_means))
        features['valuation_collapse_flag'] = 1 if (
            np.nanmean(valuation_means[-3:]) < (np.nanmean(valuation_means[:3]) - 15)
        ) else 0

        return features

    @staticmethod
    def _calculate_acceleration(values: np.ndarray) -> float:
        """
        Calculate acceleration (2nd derivative / curvature).
        Positive = accelerating upward, Negative = accelerating downward
        """
        if len(values) < 3 or np.isnan(values).all():
            return 0.0

        # Remove NaN and calculate differences
        mask = ~np.isnan(values)
        if mask.sum() < 3:
            return 0.0

        values_clean = values[mask]

        if len(values_clean) < 3:
            return 0.0

        # First differences (velocity)
        first_diff = np.diff(values_clean)
        # Second differences (acceleration)
        second_diff = np.diff(first_diff)

        return float(np.mean(second_diff)) if len(second_diff) > 0 else 0.0

    @staticmethod
    def _count_reversals(values: np.ndarray) -> int:
        """Count number of sign changes in values"""
        if len(values) < 2 or np.isnan(values).all():
            return 0

        mask = ~np.isnan(values)
        if mask.sum() < 2:
            return 0

        values_clean = values[mask]
        signs = np.sign(values_clean)
        return int(np.sum(np.abs(np.diff(signs)))) // 2

    # ========================================================================
    # MARKET-WIDE FEATURES
    # ========================================================================

    def extract_market_features(self, df: pd.DataFrame, timestamp: pd.Timestamp) -> Dict:
        """
        Extract market-wide aggregate features (across all coins).

        Includes:
        - Average durability/momentum/valuation
        - Market breadth metrics
        - Market correlation
        """
        features = {}

        window_start = timestamp - timedelta(hours=WINDOW_HOURS)
        window_data = df[
            (df['timestamp'] > window_start) &
            (df['timestamp'] <= timestamp)
        ]

        if len(window_data) == 0:
            return {}

        # Market average scores
        features['market_avg_durability'] = window_data['Durability_Score'].mean()
        features['market_avg_momentum'] = window_data['Momentum_Score'].mean()
        features['market_avg_valuation'] = window_data['Valuation_Score'].mean()

        # Conviction metrics
        features['market_total_bullish'] = window_data['bullish'].sum()
        features['market_total_bearish'] = np.abs(window_data['bearish'].sum())
        features['market_conviction_net'] = (
            window_data['bullish'].sum() - np.abs(window_data['bearish'].sum())
        )

        # Breadth (% of coins in bullish/bearish state)
        features['market_bullish_breadth'] = (
            (window_data['bullish'] > 0).sum() / window_data['bullish'].count()
        )
        features['market_bearish_breadth'] = (
            (window_data['bearish'] < 0).sum() / window_data['bearish'].count()
        )

        return features

    # ========================================================================
    # HIGH-CONVICTION FEATURES
    # ========================================================================

    def extract_high_conviction_features(self, df: pd.DataFrame, timestamp: pd.Timestamp) -> Dict:
        """
        Extract features related to high-conviction signals (Strategy 9).

        High conviction when:
        - bullish >= 15
        - bearish <= -15
        """
        features = {}

        window_start = timestamp - timedelta(hours=WINDOW_HOURS)
        window_data = df[
            (df['timestamp'] > window_start) &
            (df['timestamp'] <= timestamp)
        ]

        if len(window_data) == 0:
            return {}

        # Count high-conviction coins
        high_bullish = (window_data['bullish'] >= 15).sum()
        high_bearish = (window_data['bearish'] <= -15).sum()

        features['high_bullish_count'] = high_bullish
        features['high_bearish_count'] = high_bearish
        features['high_conviction_total'] = high_bullish + high_bearish

        # Imbalance
        total_hc = high_bullish + high_bearish
        features['conviction_imbalance'] = (
            high_bearish / total_hc if total_hc > 0 else 0.5
        )

        return features

    # ========================================================================
    # CRITICAL THRESHOLD TRIGGERS
    # ========================================================================

    def extract_critical_threshold_features(self, df: pd.DataFrame, timestamp: pd.Timestamp, coin: str) -> Dict:
        """
        Extract rule-based features for critical market conditions.

        Identifies:
        - High share of POOR rated coins
        - DMV composite collapse
        - Extreme conviction deterioration
        """
        features = {}

        window_start = timestamp - timedelta(hours=WINDOW_HOURS)
        window_data = df[
            (df['timestamp'] > window_start) &
            (df['timestamp'] <= timestamp)
        ]

        if len(window_data) == 0:
            return {}

        # Rating distribution
        poor_coins = (window_data['Valuation_Score'] < 40).sum()
        good_coins = (window_data['Valuation_Score'] >= 60).sum()
        share_poor = poor_coins / len(window_data) if len(window_data) > 0 else 0
        share_good = good_coins / len(window_data) if len(window_data) > 0 else 0

        features['share_poor'] = share_poor
        features['share_good'] = share_good
        features['share_fair'] = 1 - share_poor - share_good

        # Change in composition
        if len(window_data) >= 2:
            first_half = window_data.iloc[:len(window_data)//2]
            second_half = window_data.iloc[len(window_data)//2:]

            poor_first = (first_half['Valuation_Score'] < 40).sum() / len(first_half)
            poor_second = (second_half['Valuation_Score'] < 40).sum() / len(second_half)

            features['share_poor_increase'] = poor_second - poor_first

        # Critical condition flags
        features['critical_share_poor'] = 1 if (
            share_poor > CRITICAL_THRESHOLDS['share_poor_high']
        ) else 0

        features['critical_share_good_low'] = 1 if (
            share_good < CRITICAL_THRESHOLDS['share_good_low']
        ) else 0

        # DMV collapse: Low composite scores with downtrend
        avg_valuation = window_data['Valuation_Score'].mean()
        features['critical_dmv_collapse'] = 1 if (
            avg_valuation < CRITICAL_THRESHOLDS['dmv_composite_critical']
        ) else 0

        # Combined critical condition
        features['critical_combined'] = 1 if (
            features['critical_share_poor'] and
            features['critical_dmv_collapse'] and
            window_data['bearish'].mean() < CRITICAL_THRESHOLDS['momentum_collapse']
        ) else 0

        return features

    # ========================================================================
    # FEATURE MATRIX CONSTRUCTION
    # ========================================================================

    def extract_all_features(self, df: pd.DataFrame, coin: str, timestamp: pd.Timestamp) -> Dict:
        """
        Extract all features for a given coin and timestamp.

        Returns:
            Dictionary with ~150 feature keys and values
        """
        feature_timestamp = timestamp + FEATURE_TIMESTAMP_OFFSET
        features = {'slug': coin, 'timestamp': feature_timestamp}

        # Per-block features
        per_block = self.extract_per_block_features(df, coin, timestamp)
        features.update(per_block)

        # Cross-block features
        cross_block = self.extract_cross_block_features(per_block, coin, timestamp)
        features.update(cross_block)

        # Market-wide features
        market = self.extract_market_features(df, timestamp)
        features.update(market)

        # High-conviction features
        conviction = self.extract_high_conviction_features(df, timestamp)
        features.update(conviction)

        # Critical threshold features
        critical = self.extract_critical_threshold_features(df, timestamp, coin)
        features.update(critical)

        return features

    # ========================================================================
    # BATCH PROCESSING
    # ========================================================================

    def extract_features_batch(
        self,
        start_date: str,
        end_date: str,
        frequency_hours: int = 4,
        slug_filter: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Extract features for all coins at regular intervals.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            frequency_hours: Extract features every N hours (default 4h)

        Returns:
            DataFrame with all extracted features
        """
        logger.info("=" * 80)
        logger.info("BATCH FEATURE EXTRACTION")
        logger.info("=" * 80)

        try:
            # Load DMV data
            df = self.load_dmv_data(start_date, end_date, slug_filter=slug_filter)

            # Get unique coins
            coins = df['slug'].unique()
            if slug_filter:
                logger.info(f"Restricting feature extraction to slug: {slug_filter}")
            timestamps = pd.date_range(
                start=start_date,
                end=end_date,
                freq=f'{frequency_hours}h',
                tz='UTC'
            )

            logger.info(f"Extracting features for {len(coins)} coins at {len(timestamps)} timestamps")

            all_features = []

            for ts_idx, timestamp in enumerate(timestamps):
                if ts_idx % 100 == 0:
                    logger.info(f"  Processing timestamp {ts_idx}/{len(timestamps)}: {timestamp}")

                for coin in coins:
                    try:
                        features = self.extract_all_features(df, coin, timestamp)
                        all_features.append(features)
                    except Exception as e:
                        logger.warning(f"    Feature extraction failed for {coin} at {timestamp}: {e}")
                        continue

            df_features = pd.DataFrame(all_features)

            logger.info(f"✓ Extracted {len(df_features):,.0f} feature vectors")
            logger.info(f"✓ Features per vector: {len(df_features.columns) - 2}")  # -slug, -timestamp

            return df_features

        except Exception as e:
            logger.error(f"✗ Batch extraction failed: {e}")
            raise

    # ========================================================================
    # DATABASE STORAGE
    # ========================================================================

    def save_to_database(self, df_features: pd.DataFrame) -> bool:
        """Save extracted features to database table"""
        logger.info("=" * 80)
        logger.info("SAVING FEATURES TO DATABASE")
        logger.info("=" * 80)

        try:
            # Create table
            create_query = """
            CREATE TABLE IF NOT EXISTS regime_features (
                id SERIAL PRIMARY KEY,
                slug VARCHAR(50) NOT NULL,
                timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                -- Per-block features (9 blocks × metrics)
                b0_durability_mean FLOAT, b0_durability_std FLOAT, b0_durability_trend FLOAT,
                b0_momentum_mean FLOAT, b0_momentum_std FLOAT, b0_momentum_positive_ratio FLOAT,
                b0_bullish_mean FLOAT, b0_bearish_mean FLOAT, b0_net_conviction FLOAT, b0_conviction_ratio FLOAT,
                b0_valuation_mean FLOAT, b0_valuation_std FLOAT,
                b1_durability_mean FLOAT, b1_durability_std FLOAT, b1_durability_trend FLOAT,
                b1_momentum_mean FLOAT, b1_momentum_std FLOAT, b1_momentum_positive_ratio FLOAT,
                b1_bullish_mean FLOAT, b1_bearish_mean FLOAT, b1_net_conviction FLOAT, b1_conviction_ratio FLOAT,
                b1_valuation_mean FLOAT, b1_valuation_std FLOAT,
                b2_durability_mean FLOAT, b2_durability_std FLOAT, b2_durability_trend FLOAT,
                b2_momentum_mean FLOAT, b2_momentum_std FLOAT, b2_momentum_positive_ratio FLOAT,
                b2_bullish_mean FLOAT, b2_bearish_mean FLOAT, b2_net_conviction FLOAT, b2_conviction_ratio FLOAT,
                b2_valuation_mean FLOAT, b2_valuation_std FLOAT,
                b3_durability_mean FLOAT, b3_durability_std FLOAT, b3_durability_trend FLOAT,
                b3_momentum_mean FLOAT, b3_momentum_std FLOAT, b3_momentum_positive_ratio FLOAT,
                b3_bullish_mean FLOAT, b3_bearish_mean FLOAT, b3_net_conviction FLOAT, b3_conviction_ratio FLOAT,
                b3_valuation_mean FLOAT, b3_valuation_std FLOAT,
                b4_durability_mean FLOAT, b4_durability_std FLOAT, b4_durability_trend FLOAT,
                b4_momentum_mean FLOAT, b4_momentum_std FLOAT, b4_momentum_positive_ratio FLOAT,
                b4_bullish_mean FLOAT, b4_bearish_mean FLOAT, b4_net_conviction FLOAT, b4_conviction_ratio FLOAT,
                b4_valuation_mean FLOAT, b4_valuation_std FLOAT,
                b5_durability_mean FLOAT, b5_durability_std FLOAT, b5_durability_trend FLOAT,
                b5_momentum_mean FLOAT, b5_momentum_std FLOAT, b5_momentum_positive_ratio FLOAT,
                b5_bullish_mean FLOAT, b5_bearish_mean FLOAT, b5_net_conviction FLOAT, b5_conviction_ratio FLOAT,
                b5_valuation_mean FLOAT, b5_valuation_std FLOAT,
                b6_durability_mean FLOAT, b6_durability_std FLOAT, b6_durability_trend FLOAT,
                b6_momentum_mean FLOAT, b6_momentum_std FLOAT, b6_momentum_positive_ratio FLOAT,
                b6_bullish_mean FLOAT, b6_bearish_mean FLOAT, b6_net_conviction FLOAT, b6_conviction_ratio FLOAT,
                b6_valuation_mean FLOAT, b6_valuation_std FLOAT,
                b7_durability_mean FLOAT, b7_durability_std FLOAT, b7_durability_trend FLOAT,
                b7_momentum_mean FLOAT, b7_momentum_std FLOAT, b7_momentum_positive_ratio FLOAT,
                b7_bullish_mean FLOAT, b7_bearish_mean FLOAT, b7_net_conviction FLOAT, b7_conviction_ratio FLOAT,
                b7_valuation_mean FLOAT, b7_valuation_std FLOAT,
                b8_durability_mean FLOAT, b8_durability_std FLOAT, b8_durability_trend FLOAT,
                b8_momentum_mean FLOAT, b8_momentum_std FLOAT, b8_momentum_positive_ratio FLOAT,
                b8_bullish_mean FLOAT, b8_bearish_mean FLOAT, b8_net_conviction FLOAT, b8_conviction_ratio FLOAT,
                b8_valuation_mean FLOAT, b8_valuation_std FLOAT,
                -- Cross-block features
                durability_trend FLOAT, durability_acceleration FLOAT, durability_volatility FLOAT, durability_collapse_flag INT,
                momentum_trend FLOAT, momentum_acceleration FLOAT, momentum_reversal_count INT,
                conviction_trend FLOAT, conviction_deterioration FLOAT, conviction_collapse_flag INT, conviction_surge_flag INT,
                valuation_trend FLOAT, valuation_collapse_flag INT,
                -- Market features
                market_avg_durability FLOAT, market_avg_momentum FLOAT, market_avg_valuation FLOAT,
                market_total_bullish FLOAT, market_total_bearish FLOAT, market_conviction_net FLOAT,
                market_bullish_breadth FLOAT, market_bearish_breadth FLOAT,
                -- High-conviction features
                high_bullish_count INT, high_bearish_count INT, high_conviction_total INT, conviction_imbalance FLOAT,
                -- Critical threshold features
                share_poor FLOAT, share_good FLOAT, share_fair FLOAT, share_poor_increase FLOAT,
                critical_share_poor INT, critical_share_good_low INT, critical_dmv_collapse INT, critical_combined INT,
                UNIQUE(slug, timestamp)
            );

            CREATE INDEX IF NOT EXISTS idx_regime_features_slug_ts
                ON regime_features(slug, timestamp);
            """

            create_table_if_not_exists(self.engine_backtest, 'regime_features', create_query)

            # Insert data
            logger.info(f"Inserting {len(df_features):,.0f} feature vectors...")
            df_features.to_sql(
                'regime_features',
                self.engine_backtest,
                if_exists='append',
                index=False,
                method='multi',
                chunksize=1000
            )

            logger.info("✓ Features saved successfully")

            return True

        except Exception as e:
            logger.error(f"✗ Database save failed: {e}")
            raise


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution function"""
    logger.info("\n" + "=" * 80)
    logger.info("REGIME FEATURE EXTRACTION (108h × 9×12h blocks)")
    logger.info("=" * 80)

    try:
        # Initialize extractor
        extractor = RegimeFeatureExtractor()

        # Extract features for historical period
        # Adjust dates as needed based on available data
        start_date = '2025-03-01'  # Allow for lookback
        end_date = '2025-11-08'

        target_slug = 'ethereum'
        logger.info(f"Extracting features for period: {start_date} to {end_date} (slug={target_slug})")

        # Extract features at 4-hour frequency
        df_features = extractor.extract_features_batch(
            start_date=start_date,
            end_date=end_date,
            frequency_hours=4,
            slug_filter=target_slug
        )

        # Save to database
        extractor.save_to_database(df_features)

        logger.info("\n" + "=" * 80)
        logger.info("✅ FEATURE EXTRACTION COMPLETE")
        logger.info("=" * 80)
        logger.info(f"\nFeature count: {len(df_features.columns) - 2}")  # -slug, -timestamp
        logger.info(f"Feature vectors: {len(df_features):,.0f}")
        logger.info(f"\nNext step: Train ML models using regime_ml_models.py")

        return True

    except Exception as e:
        logger.error(f"\n✗ FAILED: {e}")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
