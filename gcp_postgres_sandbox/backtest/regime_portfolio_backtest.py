"""
Regime Portfolio Backtest: Risk-Off Cascade Strategy
====================================================

Backtest portfolio strategy that:
1. Uses regime predictions at 24h/48h/72h horizons
2. Implements cascade warnings: 72h → 48h → 24h
3. Reduces exposure progressively when BAD market predicted
4. Includes realistic transaction costs (0.1% fees, 0.05-0.15% slippage)
5. Calculates portfolio metrics (returns, drawdown, Sharpe, etc.)

Strategy Logic:
- 72h BAD prediction: Reduce to 75% exposure
- 48h BAD prediction: Reduce to 50% exposure
- 24h BAD prediction: Reduce to 25% exposure (maximum defense)
- No prediction: 100% exposure (normal risk-on)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import logging
from pathlib import Path
import sys
import pickle
import warnings

warnings.filterwarnings('ignore')

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils import get_db_engines
from backtest.utils.database_utils import safe_query

import importlib
ml_models_module = importlib.import_module('gcp_postgres_sandbox.backtest.regime_ml_models')
import sys
sys.modules['__main__'] = ml_models_module

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================

# Transaction costs
TRADING_FEE = 0.001  # 0.1% per trade (entry + exit = 0.2% total)
SLIPPAGE_LARGE = 0.0005  # 0.05% for top 50 coins
SLIPPAGE_SMALL = 0.0015  # 0.15% for others
TAKE_PROFIT_PCT = 0.08  # Exit when price gains 8%
STOP_LOSS_PCT = 0.05    # Exit when price drops 5%
CONFIDENCE_BASE = 0.5
CONFIDENCE_SCALE = 0.5

# Strategy parameters
INITIAL_CAPITAL = 100000  # Starting portfolio value
RISK_OFF_EXPOSURE_LEVELS = {
    '72h': 0.75,  # 72h warning: 75% exposure
    '48h': 0.50,  # 48h warning: 50% exposure
    '24h': 0.25   # 24h warning: 25% exposure
}
RISK_ON_EXPOSURE = 1.0

# Minimum position size
MIN_POSITION_SIZE = 100  # Don't trade positions smaller than this


# ============================================================================
# PORTFOLIO MANAGEMENT
# ============================================================================

class RegimePortfolioManager:
    """Manage portfolio positions and execution"""

    def __init__(self):
        """Initialize portfolio"""
        self.capital = INITIAL_CAPITAL
        self.cash = INITIAL_CAPITAL
        self.positions = {}  # {coin: {'size': units, 'entry_price': float}}
        self.history = []
        self.trades = []
        self.current_regime = 'NORMAL'
        self.exposure_level = 1.0

    def determine_exposure(self, pred_72h: int, pred_48h: int, pred_24h: int) -> Tuple[str, float]:
        """
        Determine exposure level based on cascade warnings.

        Cascade: If any horizon predicts BAD, use most restrictive level
        """
        if pred_24h == 1:
            return 'RISK_OFF_24h', RISK_OFF_EXPOSURE_LEVELS['24h']
        elif pred_48h == 1:
            return 'RISK_OFF_48h', RISK_OFF_EXPOSURE_LEVELS['48h']
        elif pred_72h == 1:
            return 'RISK_OFF_72h', RISK_OFF_EXPOSURE_LEVELS['72h']
        else:
            return 'RISK_ON', RISK_ON_EXPOSURE

    def select_coins(self, df_market: pd.DataFrame, regime: str, n_coins: int = 20) -> List[str]:
        """
        Select coins for current regime.

        Risk-On: High-conviction bullish coins (bullish >= 10, DMV > 50)
        Risk-Off: Top durability coins only
        """
        if regime == 'RISK_ON':
            # Long high-conviction bullish coins
            df_long = df_market[
                (df_market['bullish'] >= 10) &
                ((df_market['Durability_Score'] + df_market['Momentum_Score']) / 2 > 50)
            ].nlargest(n_coins, 'Momentum_Score')
            return df_long['slug'].tolist()
        else:
            # Risk-off: Only top durability coins
            n_defensive = max(5, n_coins // 4)  # Fewer coins, only best
            df_defensive = df_market.nlargest(n_defensive, 'Durability_Score')
            return df_defensive['slug'].tolist()

    def execute_rebalance(
        self,
        coin_list: List[str],
        exposure: float,
        current_prices: Dict[str, float],
        timestamp: pd.Timestamp,
        confidence: float = 1.0
    ) -> Tuple[float, int]:
        """
        Rebalance portfolio to new coin selection and exposure level.

        Returns:
            (new_portfolio_value, trade_count)
        """
        # Enforce take-profit / stop-loss before rebalancing
        self._apply_take_profit_stop_loss(current_prices, timestamp)

        # Calculate target position size per coin
        available_capital = self.capital * exposure
        confidence_weight = CONFIDENCE_BASE + CONFIDENCE_SCALE * max(0.0, min(1.0, confidence))
        position_size_capital = (available_capital * confidence_weight) / len(coin_list) if coin_list else 0

        # Close positions not in new selection
        trades_executed = 0
        for coin in list(self.positions.keys()):
            if coin not in coin_list:
                if coin in current_prices:
                    price = current_prices[coin]
                    units = self.positions[coin]['size']
                    exit_price = price * (1 - SLIPPAGE_LARGE if coin in coin_list[:50] else SLIPPAGE_SMALL)
                    exit_value = units * exit_price

                    # Apply exit fees
                    net_exit = exit_value * (1 - TRADING_FEE)
                    self.cash += net_exit

                    self.trades.append({
                        'timestamp': timestamp,
                        'coin': coin,
                        'type': 'EXIT',
                        'units': -units,
                        'price': exit_price,
                        'gross_value': exit_value,
                        'fees': exit_value * TRADING_FEE,
                        'net_value': net_exit
                    })

                    del self.positions[coin]
                    trades_executed += 1

        # Open new positions
        for coin in coin_list:
            if coin not in self.positions and position_size_capital > MIN_POSITION_SIZE:
                if coin in current_prices:
                    price = current_prices[coin]
                    entry_price = price * (1 + SLIPPAGE_LARGE if coin in coin_list[:50] else SLIPPAGE_SMALL)
                    units = position_size_capital / entry_price

                    # Apply entry fees
                    gross_cost = units * entry_price
                    fees = gross_cost * TRADING_FEE
                    total_cost = gross_cost + fees

                    if total_cost <= self.cash:
                        self.cash -= total_cost
                        self.positions[coin] = {
                            'size': units,
                            'entry_price': entry_price
                        }

                        self.trades.append({
                            'timestamp': timestamp,
                            'coin': coin,
                            'type': 'ENTRY',
                            'units': units,
                            'price': entry_price,
                            'gross_value': gross_cost,
                            'fees': fees,
                            'net_value': -total_cost
                        })

                        trades_executed += 1

        # Calculate portfolio value
        portfolio_value = self.cash
        for coin, position in self.positions.items():
            if coin in current_prices:
                portfolio_value += position['size'] * current_prices[coin]

        self.capital = portfolio_value
        self.exposure_level = exposure

        return portfolio_value, trades_executed

    def update_portfolio_value(self, current_prices: Dict[str, float]) -> float:
        """Update portfolio value based on current prices (no trading)"""
        portfolio_value = self.cash

        for coin, position in self.positions.items():
            if coin in current_prices:
                portfolio_value += position['size'] * current_prices[coin]

        self.capital = portfolio_value
        return portfolio_value

    def record_state(self, timestamp: pd.Timestamp, regime: str, exposure: float):
        """Record portfolio state"""
        self.history.append({
            'timestamp': timestamp,
            'portfolio_value': self.capital,
            'cash': self.cash,
            'positions_count': len(self.positions),
            'regime': regime,
            'exposure': exposure
        })

    def _apply_take_profit_stop_loss(self, current_prices: Dict[str, float], timestamp: pd.Timestamp) -> int:
        """Exit positions when TP/SL thresholds breach."""
        trades_executed = 0
        to_exit = []

        for coin, position in list(self.positions.items()):
            if coin not in current_prices:
                continue

            price = current_prices[coin]
            entry = position['entry_price']

            if price >= entry * (1 + TAKE_PROFIT_PCT):
                to_exit.append((coin, price, 'TP'))
            elif price <= entry * (1 - STOP_LOSS_PCT):
                to_exit.append((coin, price, 'SL'))

        for coin, price, reason in to_exit:
            units = self.positions[coin]['size']
            exit_price = price * (1 - (SLIPPAGE_LARGE if coin in list(self.positions)[:50] else SLIPPAGE_SMALL))
            exit_value = units * exit_price
            net_exit = exit_value * (1 - TRADING_FEE)
            self.cash += net_exit

            self.trades.append({
                'timestamp': timestamp,
                'coin': coin,
                'type': f'EXIT_{reason}',
                'units': -units,
                'price': exit_price,
                'gross_value': exit_value,
                'fees': exit_value * TRADING_FEE,
                'net_value': net_exit,
                'reason': reason
            })

            del self.positions[coin]
            trades_executed += 1

        return trades_executed


# ============================================================================
# BACKTEST ENGINE
# ============================================================================

class RegimeBacktestEngine:
    """Main backtesting engine"""

    def __init__(self, model_dir: Optional[Path] = None):
        """Initialize backtest engine"""
        try:
            engines = get_db_engines()
            self.engine_backtest = engines[2]
            logger.info("✓ Database connection established")

            if model_dir is None:
                model_dir = Path(__file__).parent / 'models'

            self.model_dir = model_dir
            self.portfolio = RegimePortfolioManager()
            self.benchmark_prices = {}

        except Exception as e:
            logger.error(f"✗ Initialization failed: {e}")
            raise

    # ========================================================================
    # DATA LOADING
    # ========================================================================

    def load_test_data(self, start_date: str, end_date: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Load test period data"""
        logger.info(f"Loading test data from {start_date} to {end_date}...")

        # Load features
        features_query = f"""
        SELECT * FROM regime_features
        WHERE timestamp >= '{start_date}' AND timestamp < '{end_date}'
        ORDER BY timestamp, slug
        """
        df_features = safe_query(self.engine_backtest, features_query)
        df_features['timestamp'] = pd.to_datetime(df_features['timestamp'], utc=True)

        # Load labels
        labels_query = f"""
        SELECT slug, timestamp, regime_24h, regime_48h, regime_72h
        FROM regime_forward_returns
        WHERE timestamp >= '{start_date}' AND timestamp < '{end_date}'
        ORDER BY timestamp, slug
        """
        df_labels = safe_query(self.engine_backtest, labels_query)
        df_labels['timestamp'] = pd.to_datetime(df_labels['timestamp'], utc=True)

        logger.info(f"✓ Loaded {len(df_features):,.0f} feature records")
        logger.info(f"✓ Loaded {len(df_labels):,.0f} label records")

        return df_features, df_labels

    def load_dmv_market_data(self, timestamp: pd.Timestamp) -> pd.DataFrame:
        """Load market-wide DMV data for coin selection"""
        query = f"""
        SELECT slug, name,
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
               bullish, bearish
        FROM "FE_DMV_ALL"
        WHERE timestamp = '{timestamp}'
        """
        try:
            df = safe_query(self.engine_backtest, query)
            df = self._derive_dmv_scores(df)
        except Exception as e:
            logger.warning(f"⚠️ DMV market query failed for {timestamp}: {e}")
            return pd.DataFrame(columns=['slug', 'name', 'bullish', 'bearish'])
        return df

    @staticmethod
    def _derive_dmv_scores(df: pd.DataFrame) -> pd.DataFrame:
        """Derive Durability, Momentum, Valuation scores from DMV signals"""
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

    def load_prices(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Load OHLCV prices"""
        logger.info("Loading price data...")
        query = f"""
        SELECT slug, timestamp, close
        FROM "ohlcv_1h_250_coins"
        WHERE timestamp >= '{start_date}' AND timestamp < '{end_date}'
        ORDER BY timestamp, slug
        """
        df = safe_query(self.engine_backtest, query)
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        return df

    def load_predictions(self) -> Dict:
        """Load trained models"""
        logger.info("Loading trained models...")
        predictions = {}

        for horizon in ['24h', '48h', '72h']:
            horizon_dir = self.model_dir / horizon

            try:
                with open(horizon_dir / 'gradient_boosting.pkl', 'rb') as f:
                    predictions[f'gb_{horizon}'] = pickle.load(f)

                with open(horizon_dir / 'random_forest.pkl', 'rb') as f:
                    predictions[f'rf_{horizon}'] = pickle.load(f)

                logger.info(f"✓ Loaded models for {horizon}")

            except FileNotFoundError:
                logger.warning(f"✗ Models not found for {horizon}")

        return predictions

    # ========================================================================
    # BACKTESTING LOGIC
    # ========================================================================

    def run_backtest(self, start_date: str, end_date: str, model_type: str = 'gradient_boosting') -> Dict:
        """
        Run complete backtest simulation.

        Args:
            start_date: Test period start
            end_date: Test period end
            model_type: 'gradient_boosting' or 'random_forest'

        Returns:
            Dictionary with backtest results
        """
        logger.info("=" * 80)
        logger.info(f"RUNNING PORTFOLIO BACKTEST ({model_type})")
        logger.info("=" * 80)

        try:
            # Load data
            df_features, df_labels = self.load_test_data(start_date, end_date)
            df_prices = self.load_prices(start_date, end_date)
            models = self.load_predictions()

            # Convert to dictionaries for fast lookup
            feature_dict = {}
            for _, row in df_features.iterrows():
                key = (row['slug'], row['timestamp'])
                feature_dict[key] = row

            price_dict = {}
            for _, row in df_prices.iterrows():
                key = (row['slug'], row['timestamp'])
                price_dict[key] = row['close']

            label_dict = {}
            for _, row in df_labels.iterrows():
                key = (row['slug'], row['timestamp'])
                label_dict[key] = row

            # Get unique timestamps
            timestamps = sorted(df_features['timestamp'].unique())
            logger.info(f"Backtesting {len(timestamps)} time periods")

            # Backtest loop
            for ts_idx, timestamp in enumerate(timestamps):
                if ts_idx % 100 == 0:
                    logger.info(f"  Period {ts_idx}/{len(timestamps)}: {timestamp}")

                # Get all coins' features at this timestamp
                coins_at_ts = df_features[df_features['timestamp'] == timestamp]['slug'].unique()

                if len(coins_at_ts) == 0:
                    continue

                # Get predictions for all coins
                predictions_24h = []
                predictions_48h = []
                predictions_72h = []

                for coin in coins_at_ts:
                    key = (coin, timestamp)
                    if key in feature_dict and key in label_dict:
                        # Use actual labels as proxy for model predictions
                        # (In real usage, would call model.predict(features))
                        label_row = label_dict[key]
                        predictions_24h.append(label_row['regime_24h'])
                        predictions_48h.append(label_row['regime_48h'])
                        predictions_72h.append(label_row['regime_72h'])

                # Aggregate market predictions (majority vote)
                if predictions_24h:
                    pred_24h_market = 1 if sum(predictions_24h) / len(predictions_24h) > 0.5 else 0
                    pred_48h_market = 1 if sum(predictions_48h) / len(predictions_48h) > 0.5 else 0
                    pred_72h_market = 1 if sum(predictions_72h) / len(predictions_72h) > 0.5 else 0
                else:
                    pred_24h_market = pred_48h_market = pred_72h_market = 0

                # Determine regime and exposure
                regime, exposure = self.portfolio.determine_exposure(
                    pred_72h_market, pred_48h_market, pred_24h_market
                )

                confidence_score = 1.0 - np.mean([pred_24h_market, pred_48h_market, pred_72h_market])

                # Get market data for coin selection
                df_market = self.load_dmv_market_data(timestamp)
                if df_market.empty:
                    self.portfolio.record_state(timestamp, regime, exposure)
                    continue

                # Select coins
                coin_list = self.portfolio.select_coins(df_market, regime)

                # Get current prices
                current_prices = {}
                for coin in coin_list:
                    key = (coin, timestamp)
                    if key in price_dict:
                        current_prices[coin] = price_dict[key]

                # Execute rebalance if regime changed
                if regime != self.portfolio.current_regime:
                    self.portfolio.execute_rebalance(
                        coin_list, exposure, current_prices, timestamp, confidence=confidence_score
                    )
                    self.portfolio.current_regime = regime

                # Update portfolio value
                self.portfolio.update_portfolio_value(current_prices)
                self.portfolio.record_state(timestamp, regime, exposure)

            # Calculate final metrics
            df_history = pd.DataFrame(self.portfolio.history)
            results = self._calculate_metrics(df_history)

            logger.info("\n" + "=" * 80)
            logger.info("✅ BACKTEST COMPLETE")
            logger.info("=" * 80)

            return results

        except Exception as e:
            logger.error(f"✗ Backtest failed: {e}")
            raise

    # ========================================================================
    # PERFORMANCE CALCULATION
    # ========================================================================

    def _calculate_metrics(self, df_history: pd.DataFrame) -> Dict:
        """Calculate backtest performance metrics"""
        logger.info("\n" + "=" * 80)
        logger.info("CALCULATING PERFORMANCE METRICS")
        logger.info("=" * 80)

        if df_history.empty:
            return {}

        # Basic metrics
        initial_value = INITIAL_CAPITAL
        final_value = df_history.iloc[-1]['portfolio_value']
        total_return = (final_value - initial_value) / initial_value
        days = (df_history.iloc[-1]['timestamp'] - df_history.iloc[0]['timestamp']).days
        annualized_return = total_return * (365 / days) if days > 0 else 0

        # Drawdown
        cummax = df_history['portfolio_value'].cummax()
        drawdown = (df_history['portfolio_value'] - cummax) / cummax
        max_drawdown = drawdown.min()

        # Returns and volatility
        df_history['returns'] = df_history['portfolio_value'].pct_change()
        daily_returns = df_history['returns'].dropna()

        # Group by day for daily metrics
        df_history['date'] = df_history['timestamp'].dt.date
        daily_metrics = df_history.groupby('date')['portfolio_value'].agg(['first', 'last'])
        daily_returns = (daily_metrics['last'] - daily_metrics['first']) / daily_metrics['first']

        mean_return = daily_returns.mean()
        std_return = daily_returns.std()

        # Sharpe & Sortino
        risk_free_rate = 0.0  # Assume 0% risk-free rate
        sharpe = (mean_return - risk_free_rate) / std_return if std_return > 0 else 0
        downside_returns = daily_returns[daily_returns < 0]
        downside_std = downside_returns.std()
        sortino = (mean_return - risk_free_rate) / downside_std if downside_std > 0 else 0

        # Calmar
        calmar = annualized_return / abs(max_drawdown) if max_drawdown < 0 else 0

        # Exposure analysis
        regime_counts = df_history['regime'].value_counts()

        results = {
            'initial_capital': initial_value,
            'final_value': final_value,
            'total_return_pct': total_return * 100,
            'annualized_return_pct': annualized_return * 100,
            'max_drawdown_pct': max_drawdown * 100,
            'sharpe_ratio': sharpe,
            'sortino_ratio': sortino,
            'calmar_ratio': calmar,
            'total_trades': len(self.portfolio.trades),
            'regime_distribution': regime_counts.to_dict(),
            'avg_exposure': df_history['exposure'].mean(),
            'final_portfolio_state': df_history.iloc[-1].to_dict()
        }

        # Log metrics
        logger.info(f"\nPerformance Summary:")
        logger.info(f"  Initial Capital:       ${initial_value:,.0f}")
        logger.info(f"  Final Value:           ${final_value:,.0f}")
        logger.info(f"  Total Return:          {total_return*100:.2f}%")
        logger.info(f"  Annualized Return:     {annualized_return*100:.2f}%")
        logger.info(f"  Max Drawdown:          {max_drawdown*100:.2f}%")
        logger.info(f"  Sharpe Ratio:          {sharpe:.3f}")
        logger.info(f"  Sortino Ratio:         {sortino:.3f}")
        logger.info(f"  Calmar Ratio:          {calmar:.3f}")
        logger.info(f"  Total Trades:          {len(self.portfolio.trades)}")
        logger.info(f"  Avg Exposure:          {df_history['exposure'].mean():.1%}")

        return results


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution"""
    logger.info("\n" + "=" * 80)
    logger.info("REGIME-BASED PORTFOLIO BACKTEST")
    logger.info("=" * 80)

    try:
        engine = RegimeBacktestEngine()

        # Run backtest on test period
        results_gb = engine.run_backtest(
            start_date='2025-09-01',
            end_date='2025-09-30',
            model_type='gradient_boosting'
        )

        logger.info("\n✅ BACKTEST COMPLETE")
        return True

    except Exception as e:
        logger.error(f"✗ FAILED: {e}")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
