"""
Market Insights Report Generator
Comprehensive market analysis using 15 intelligent strategies across 4hr, 24hr, 108hr timeframes
Analyzes all 250 coins using real database data from cp_ai and cp_backtest_h
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import argparse
from pathlib import Path
import sys
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import get_db_engines

# ============================================================================
# DATABASE UTILITIES
# ============================================================================

class DatabaseManager:
    """Manage connections to cp_ai and cp_backtest_h databases"""

    def __init__(self):
        """Initialize database connections"""
        try:
            self.engine_ai, self.engine_backtest = None, None
            engines = get_db_engines()
            if len(engines) >= 2:
                self.engine_ai = engines[1]  # cp_ai
                self.engine_backtest = engines[2]  # cp_backtest_h
        except Exception as e:
            print(f"Warning: Could not initialize database engines: {e}")

    def fetch_dmv_all_current(self, hours_back: int = 108) -> pd.DataFrame:
        """Fetch current DMV data from cp_ai"""
        if not self.engine_ai:
            return pd.DataFrame()
        try:
            query = f"""
            SELECT * FROM "FE_DMV_ALL"
            WHERE timestamp >= NOW() - INTERVAL '{hours_back} hours'
            ORDER BY timestamp DESC, slug
            """
            return pd.read_sql(query, self.engine_ai)
        except Exception as e:
            print(f"Warning: Could not fetch current data: {e}")
            return pd.DataFrame()

    def fetch_dmv_all_historical(self, hours_back: int = 108) -> pd.DataFrame:
        """Fetch historical DMV data from cp_backtest_h"""
        if not self.engine_backtest:
            return pd.DataFrame()
        try:
            query = f"""
            SELECT * FROM "FE_DMV_ALL"
            WHERE timestamp >= NOW() - INTERVAL '{hours_back} hours'
            ORDER BY timestamp DESC, slug
            """
            return pd.read_sql(query, self.engine_backtest)
        except Exception as e:
            print(f"Warning: Could not fetch historical data: {e}")
            return pd.DataFrame()

    def fetch_dmv_scores_current(self, hours_back: int = 108) -> pd.DataFrame:
        """Fetch current scores from cp_ai"""
        if not self.engine_ai:
            return pd.DataFrame()
        try:
            query = f"""
            SELECT slug, "Durability_Score", "Momentum_Score", "Valuation_Score"
            FROM "FE_DMV_SCORES"
            LIMIT 250
            """
            df = pd.read_sql(query, self.engine_ai)
            # Get names from FE_DMV_ALL
            query_names = f"""
            SELECT DISTINCT slug, name FROM "FE_DMV_ALL" LIMIT 250
            """
            df_names = pd.read_sql(query_names, self.engine_ai)
            df = df.merge(df_names, on='slug', how='left')
            return df
        except Exception as e:
            print(f"Warning: Could not fetch scores: {e}")
            return pd.DataFrame()

    def fetch_bitcoin_data(self, hours_back: int = 108, use_backtest: bool = False) -> pd.DataFrame:
        """Fetch Bitcoin benchmark data"""
        engine = self.engine_backtest if use_backtest else self.engine_ai
        if not engine:
            return pd.DataFrame()
        try:
            query = f"""
            SELECT * FROM "FE_DMV_BITCOIN"
            WHERE timestamp >= NOW() - INTERVAL '{hours_back} hours'
            ORDER BY timestamp DESC
            """
            return pd.read_sql(query, engine)
        except Exception as e:
            print(f"Warning: Could not fetch Bitcoin data: {e}")
            return pd.DataFrame()


# ============================================================================
# ANALYTICAL STRATEGIES (15 Total)
# ============================================================================

class MarketAnalyzer:
    """Perform 15 different market analysis strategies"""

    def __init__(self, df_current: pd.DataFrame, df_backtest: pd.DataFrame, timeframe_hours: int):
        """Initialize analyzer with data"""
        self.df_current = df_current
        self.df_backtest = df_backtest
        self.timeframe_hours = timeframe_hours
        self.latest_timestamp = pd.Timestamp.now() - timedelta(hours=1)

        # Extract latest data for this timeframe
        if not df_current.empty:
            self.df_latest = self._get_latest_window(df_current, timeframe_hours)
        else:
            self.df_latest = pd.DataFrame()

    def _get_latest_window(self, df: pd.DataFrame, hours: int) -> pd.DataFrame:
        """Get latest N hours of data"""
        if df.empty:
            return pd.DataFrame()
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        cutoff = pd.Timestamp.now(tz='UTC') - timedelta(hours=hours)
        return df[df['timestamp'] >= cutoff].copy()

    # ========== STRATEGY 1: MULTI-TIMEFRAME RSI CONFLUENCE ==========
    def strategy_1_rsi_confluence(self) -> Dict:
        """
        Identify coins with aligned RSI signals across multiple timeframes.
        Strong confluence when short/medium/long RSI all agree.
        """
        if self.df_latest.empty:
            return {'error': 'No data available'}

        results = []

        for slug in self.df_latest['slug'].unique():
            coin_data = self.df_latest[self.df_latest['slug'] == slug].sort_values('timestamp')
            if len(coin_data) < 2:
                continue

            latest = coin_data.iloc[-1]

            # Count RSI signals - columns like m_mom_rsi_9_signal, etc.
            rsi_columns = [col for col in coin_data.columns if 'm_mom_rsi' in col and 'signal' in col]

            if not rsi_columns:
                continue

            signals = [latest[col] for col in rsi_columns if col in latest and pd.notna(latest[col])]

            if signals:
                bullish_count = sum(1 for s in signals if s > 0)
                bearish_count = sum(1 for s in signals if s < 0)
                confluence_strength = max(bullish_count, bearish_count) / len(signals) if signals else 0
                direction = 'BULLISH' if bullish_count > bearish_count else 'BEARISH' if bearish_count > bullish_count else 'NEUTRAL'

                results.append({
                    'slug': slug,
                    'name': latest.get('name', slug),
                    'direction': direction,
                    'confluence_strength': confluence_strength,
                    'bullish_rsi': bullish_count,
                    'bearish_rsi': bearish_count,
                    'signal_count': len(signals)
                })

        if not results:
            return {
                'strategy': 'Multi-Timeframe RSI Confluence',
                'description': 'RSI signals aligned across 9/18/27/54/108 periods',
                'note': 'No RSI signal columns found in data',
                'top_10': [],
                'bottom_10': [],
                'avg_confluence': 0
            }

        df_results = pd.DataFrame(results).sort_values('confluence_strength', ascending=False)
        return {
            'strategy': 'Multi-Timeframe RSI Confluence',
            'description': 'RSI signals aligned across 9/18/27/54/108 periods',
            'top_10': df_results.head(10).to_dict('records'),
            'bottom_10': df_results.tail(10).to_dict('records'),
            'avg_confluence': float(df_results['confluence_strength'].mean()) if not df_results.empty else 0
        }

    # ========== STRATEGY 2: MACD + STOCHASTIC ALIGNMENT ==========
    def strategy_2_macd_stochastic_alignment(self) -> Dict:
        """
        Detect strong momentum when both MACD and Stochastic indicators agree.
        Higher agreement = stronger signal.
        """
        if self.df_latest.empty:
            return {'error': 'No data available'}

        results = []

        for slug in self.df_latest['slug'].unique():
            coin_data = self.df_latest[self.df_latest['slug'] == slug].sort_values('timestamp')
            if len(coin_data) < 1:
                continue

            latest = coin_data.iloc[-1]

            macd_signal = latest.get('m_macd_signal', 0)
            stoch_signal = latest.get('m_stoch_signal', 0)

            if pd.isna(macd_signal) or pd.isna(stoch_signal):
                continue

            # Alignment: both positive, both negative, or both zero
            alignment_score = 0
            if (macd_signal > 0 and stoch_signal > 0) or (macd_signal < 0 and stoch_signal < 0):
                alignment_score = 1.0
            elif (macd_signal > 0 and stoch_signal == 0) or (macd_signal == 0 and stoch_signal > 0):
                alignment_score = 0.5

            results.append({
                'slug': slug,
                'name': latest.get('name', slug),
                'macd_signal': int(macd_signal),
                'stoch_signal': int(stoch_signal),
                'alignment_score': alignment_score,
                'direction': 'BULLISH' if alignment_score > 0 and (macd_signal + stoch_signal) > 0 else 'BEARISH' if alignment_score > 0 else 'NEUTRAL'
            })

        df_results = pd.DataFrame(results).sort_values('alignment_score', ascending=False)
        return {
            'strategy': 'MACD + Stochastic Alignment',
            'description': 'Momentum strength when both indicators agree',
            'top_10': df_results[df_results['alignment_score'] > 0].head(10).to_dict('records'),
            'bottom_10': df_results[df_results['alignment_score'] == 0].head(10).to_dict('records'),
            'aligned_percentage': float((df_results['alignment_score'] > 0).sum() / len(df_results) * 100) if not df_results.empty else 0
        }

    # ========== STRATEGY 3: MOVING AVERAGE CROSSOVER ==========
    def strategy_3_ma_crossover(self) -> Dict:
        """
        Track moving average crossovers for trend changes.
        SMA9 > SMA18 > SMA108 = strong uptrend
        """
        if self.df_latest.empty:
            return {'error': 'No data available'}

        results = []

        for slug in self.df_latest['slug'].unique():
            coin_data = self.df_latest[self.df_latest['slug'] == slug].sort_values('timestamp')
            if len(coin_data) < 2:
                continue

            latest = coin_data.iloc[-1]
            previous = coin_data.iloc[-2] if len(coin_data) > 1 else None

            # Get moving averages
            sma_fields = ['d_sma_9', 'd_sma_18', 'd_sma_21', 'd_sma_108']
            smas = {field: latest.get(field, np.nan) for field in sma_fields}

            if any(pd.isna(v) for v in smas.values()):
                continue

            # Determine trend
            if smas['d_sma_9'] > smas['d_sma_18'] > smas['d_sma_108']:
                trend = 'STRONG_UPTREND'
                strength = 1.0
            elif smas['d_sma_9'] > smas['d_sma_18']:
                trend = 'UPTREND'
                strength = 0.7
            elif smas['d_sma_9'] < smas['d_sma_18'] < smas['d_sma_108']:
                trend = 'STRONG_DOWNTREND'
                strength = -1.0
            elif smas['d_sma_9'] < smas['d_sma_18']:
                trend = 'DOWNTREND'
                strength = -0.7
            else:
                trend = 'SIDEWAYS'
                strength = 0

            results.append({
                'slug': slug,
                'name': latest.get('name', slug),
                'trend': trend,
                'strength': strength,
                'sma_9': float(smas['d_sma_9']) if not pd.isna(smas['d_sma_9']) else None,
                'sma_18': float(smas['d_sma_18']) if not pd.isna(smas['d_sma_18']) else None,
                'sma_108': float(smas['d_sma_108']) if not pd.isna(smas['d_sma_108']) else None
            })

        if not results:
            return {
                'strategy': 'Moving Average Crossover',
                'description': 'Trend identification using SMA9/18/21/108 crossovers',
                'strong_uptrend': 0,
                'uptrend': 0,
                'downtrend': 0,
                'strong_downtrend': 0,
                'top_10_uptrend': [],
                'top_10_downtrend': []
            }

        df_results = pd.DataFrame(results).sort_values('strength', ascending=False)
        return {
            'strategy': 'Moving Average Crossover',
            'description': 'Trend identification using SMA9/18/21/108 crossovers',
            'strong_uptrend': len(df_results[df_results['trend'] == 'STRONG_UPTREND']),
            'uptrend': len(df_results[df_results['trend'] == 'UPTREND']),
            'downtrend': len(df_results[df_results['trend'] == 'DOWNTREND']),
            'strong_downtrend': len(df_results[df_results['trend'] == 'STRONG_DOWNTREND']),
            'top_10_uptrend': df_results[df_results['strength'] > 0].head(10).to_dict('records'),
            'top_10_downtrend': df_results[df_results['strength'] < 0].tail(10).to_dict('records')
        }

    # ========== STRATEGY 4: MOMENTUM ACCELERATION ==========
    def strategy_4_momentum_acceleration(self) -> Dict:
        """
        Compare momentum scores across timeframes to find accelerating trends.
        Acceleration when recent momentum > historical momentum.
        """
        if self.df_latest.empty or self.df_current.empty:
            return {'error': 'No data available'}

        results = []

        # Split data into periods
        now = pd.Timestamp.now(tz='UTC')
        period_4h = self.df_latest[(self.df_latest['timestamp'] >= now - timedelta(hours=4))]
        period_24h = self.df_latest[(self.df_latest['timestamp'] >= now - timedelta(hours=24))]

        for slug in self.df_latest['slug'].unique():
            try:
                momentum_4h = period_4h[period_4h['slug'] == slug].get('m_mom_rsi_9', pd.Series()).mean()
                momentum_24h = period_24h[period_24h['slug'] == slug].get('m_mom_rsi_18', pd.Series()).mean()

                if pd.isna(momentum_4h) or pd.isna(momentum_24h):
                    continue

                acceleration = momentum_4h - momentum_24h
                name = self.df_latest[self.df_latest['slug'] == slug]['name'].iloc[0] if not self.df_latest[self.df_latest['slug'] == slug].empty else slug

                results.append({
                    'slug': slug,
                    'name': name,
                    'momentum_4h': float(momentum_4h),
                    'momentum_24h': float(momentum_24h),
                    'acceleration': float(acceleration),
                    'direction': 'ACCELERATING_UP' if acceleration > 0 else 'ACCELERATING_DOWN'
                })
            except:
                continue

        if not results:
            return {
                'strategy': 'Momentum Acceleration',
                'description': 'Coins with accelerating momentum trends',
                'accelerating_up': 0,
                'accelerating_down': 0,
                'top_10': [],
                'bottom_10': [],
                'avg_acceleration': 0
            }

        df_results = pd.DataFrame(results).sort_values('acceleration', ascending=False)
        return {
            'strategy': 'Momentum Acceleration',
            'description': 'Coins with accelerating momentum trends',
            'accelerating_up': len(df_results[df_results['acceleration'] > 0]),
            'accelerating_down': len(df_results[df_results['acceleration'] < 0]),
            'top_10': df_results.head(10).to_dict('records'),
            'bottom_10': df_results.tail(10).to_dict('records'),
            'avg_acceleration': float(df_results['acceleration'].mean()) if not df_results.empty else 0
        }

    # ========== STRATEGY 5: RSI DIVERGENCE DETECTION ==========
    def strategy_5_rsi_divergence(self) -> Dict:
        """
        Find price/RSI divergences signaling potential reversals.
        Bullish divergence: price makes lower low, RSI makes higher low.
        Bearish divergence: price makes higher high, RSI makes lower high.
        """
        if self.df_latest.empty or len(self.df_latest) < 3:
            return {'error': 'Insufficient data for divergence detection'}

        results = []

        for slug in self.df_latest['slug'].unique():
            coin_data = self.df_latest[self.df_latest['slug'] == slug].sort_values('timestamp')
            if len(coin_data) < 3:
                continue

            try:
                # Get price and RSI changes
                prices = coin_data['close'].values if 'close' in coin_data.columns else []
                rsi_cols = [col for col in coin_data.columns if 'm_mom_rsi' in col and 'signal' not in col]

                if not prices or len(prices) < 3:
                    continue

                # Simple divergence: compare price trend vs momentum trend
                price_trend = prices[-1] - prices[-2]
                rsi_values = []
                for col in rsi_cols[:3]:  # Use first 3 RSI values
                    if col in coin_data.columns:
                        rsi_values.extend(coin_data[col].values)

                if rsi_values:
                    rsi_trend = rsi_values[-1] - rsi_values[0] if len(rsi_values) > 1 else 0

                    divergence_type = 'NONE'
                    strength = 0

                    # Bullish divergence
                    if price_trend < 0 and rsi_trend > 0:
                        divergence_type = 'BULLISH'
                        strength = 0.7
                    # Bearish divergence
                    elif price_trend > 0 and rsi_trend < 0:
                        divergence_type = 'BEARISH'
                        strength = -0.7

                    latest = coin_data.iloc[-1]
                    results.append({
                        'slug': slug,
                        'name': latest.get('name', slug),
                        'divergence_type': divergence_type,
                        'strength': strength,
                        'price_trend': float(price_trend),
                        'rsi_trend': float(rsi_trend)
                    })
            except:
                continue

        if not results:
            return {
                'strategy': 'RSI Divergence Detection',
                'description': 'Price/RSI divergences signaling potential reversals',
                'bullish_divergences': 0,
                'bearish_divergences': 0,
                'bullish_divergence_coins': [],
                'bearish_divergence_coins': []
            }

        df_results = pd.DataFrame(results)
        bullish_divs = df_results[df_results['divergence_type'] == 'BULLISH']
        bearish_divs = df_results[df_results['divergence_type'] == 'BEARISH']

        return {
            'strategy': 'RSI Divergence Detection',
            'description': 'Price/RSI divergences signaling potential reversals',
            'bullish_divergences': len(bullish_divs),
            'bearish_divergences': len(bearish_divs),
            'bullish_divergence_coins': bullish_divs.head(10).to_dict('records'),
            'bearish_divergence_coins': bearish_divs.head(10).to_dict('records')
        }

    # ========== STRATEGY 6: VOLUME SPIKE DETECTION ==========
    def strategy_6_volume_spike(self) -> Dict:
        """
        Identify unusual volume (>2x average) correlated with price movement.
        Volume spikes indicate increased interest/conviction.
        """
        if self.df_latest.empty or len(self.df_latest) < 5:
            return {'error': 'Insufficient data for volume analysis'}

        results = []

        for slug in self.df_latest['slug'].unique():
            coin_data = self.df_latest[self.df_latest['slug'] == slug].sort_values('timestamp')
            if len(coin_data) < 5:
                continue

            try:
                volumes = coin_data['volume'].values if 'volume' in coin_data.columns else []
                if len(volumes) < 5:
                    continue

                avg_volume = np.mean(volumes[:-1])  # Exclude latest
                latest_volume = volumes[-1]
                volume_ratio = latest_volume / avg_volume if avg_volume > 0 else 0

                # Get latest price movement
                closes = coin_data['close'].values if 'close' in coin_data.columns else []
                if len(closes) > 1:
                    price_change_pct = ((closes[-1] - closes[-2]) / closes[-2] * 100) if closes[-2] > 0 else 0
                else:
                    price_change_pct = 0

                latest = coin_data.iloc[-1]

                # Spike detected if volume > 2x average
                if volume_ratio > 2.0:
                    results.append({
                        'slug': slug,
                        'name': latest.get('name', slug),
                        'volume_ratio': float(volume_ratio),
                        'price_change_pct': float(price_change_pct),
                        'volume_strength': 'STRONG' if volume_ratio > 5 else 'MODERATE',
                        'price_correlation': 'POSITIVE' if price_change_pct > 0 else 'NEGATIVE'
                    })
            except:
                continue

        if not results:
            return {
                'strategy': 'Volume Spike Detection',
                'description': 'Unusual volume (>2x average) with price correlation',
                'spike_count': 0,
                'bullish_spikes': 0,
                'bearish_spikes': 0,
                'top_10_spikes': []
            }

        df_results = pd.DataFrame(results).sort_values('volume_ratio', ascending=False)
        return {
            'strategy': 'Volume Spike Detection',
            'description': 'Unusual volume (>2x average) with price correlation',
            'spike_count': len(df_results),
            'bullish_spikes': len(df_results[df_results['price_correlation'] == 'POSITIVE']),
            'bearish_spikes': len(df_results[df_results['price_correlation'] == 'NEGATIVE']),
            'top_10_spikes': df_results.head(10).to_dict('records')
        }

    # ========== STRATEGY 7: ON-BALANCE VOLUME TRENDS ==========
    def strategy_7_obv_trends(self) -> Dict:
        """
        Track On-Balance Volume momentum for accumulation/distribution patterns.
        Positive OBV trend = accumulation (bullish)
        Negative OBV trend = distribution (bearish)
        """
        if self.df_latest.empty or len(self.df_latest) < 3:
            return {'error': 'Insufficient data for OBV analysis'}

        results = []

        for slug in self.df_latest['slug'].unique():
            coin_data = self.df_latest[self.df_latest['slug'] == slug].sort_values('timestamp')
            if len(coin_data) < 3:
                continue

            try:
                obv_values = coin_data.get('d_obv', pd.Series()).values if 'd_obv' in coin_data.columns else []
                if len(obv_values) < 2:
                    continue

                # Trend: compare latest to average
                obv_latest = obv_values[-1]
                obv_avg = np.mean(obv_values[:-1])
                obv_trend = obv_latest - obv_avg

                # Trend strength (% change)
                obv_trend_pct = (obv_trend / obv_avg * 100) if obv_avg != 0 else 0

                latest = coin_data.iloc[-1]

                results.append({
                    'slug': slug,
                    'name': latest.get('name', slug),
                    'obv_trend': float(obv_trend_pct),
                    'obv_latest': float(obv_latest) if not pd.isna(obv_latest) else 0,
                    'pattern': 'ACCUMULATION' if obv_trend_pct > 0 else 'DISTRIBUTION',
                    'strength': 'STRONG' if abs(obv_trend_pct) > 10 else 'MODERATE'
                })
            except:
                continue

        if not results:
            return {
                'strategy': 'On-Balance Volume Trends',
                'description': 'OBV momentum for accumulation/distribution patterns',
                'accumulation_coins': 0,
                'distribution_coins': 0,
                'top_accumulation': [],
                'top_distribution': [],
                'avg_obv_trend': 0
            }

        df_results = pd.DataFrame(results).sort_values('obv_trend', ascending=False)
        accumulation = df_results[df_results['pattern'] == 'ACCUMULATION']
        distribution = df_results[df_results['pattern'] == 'DISTRIBUTION']

        return {
            'strategy': 'On-Balance Volume Trends',
            'description': 'OBV momentum for accumulation/distribution patterns',
            'accumulation_coins': len(accumulation),
            'distribution_coins': len(distribution),
            'top_accumulation': accumulation.head(10).to_dict('records'),
            'top_distribution': distribution.tail(10).to_dict('records'),
            'avg_obv_trend': float(df_results['obv_trend'].mean()) if not df_results.empty else 0
        }

    # ========== STRATEGY 8: CHAIKIN MONEY FLOW ANALYSIS ==========
    def strategy_8_cmf_analysis(self) -> Dict:
        """
        Detect money flow strength and direction using Chaikin Money Flow.
        Positive CMF = money flowing in (bullish)
        Negative CMF = money flowing out (bearish)
        """
        if self.df_latest.empty:
            return {'error': 'No data available'}

        results = []

        for slug in self.df_latest['slug'].unique():
            coin_data = self.df_latest[self.df_latest['slug'] == slug].sort_values('timestamp')
            if len(coin_data) < 1:
                continue

            try:
                latest = coin_data.iloc[-1]
                cmf_value = latest.get('d_cmf', np.nan)

                if pd.isna(cmf_value):
                    continue

                # CMF strength
                cmf_strength = abs(cmf_value)
                cmf_direction = 'MONEY_IN' if cmf_value > 0 else 'MONEY_OUT' if cmf_value < 0 else 'NEUTRAL'

                results.append({
                    'slug': slug,
                    'name': latest.get('name', slug),
                    'cmf_value': float(cmf_value),
                    'cmf_strength': float(cmf_strength),
                    'direction': cmf_direction,
                    'intensity': 'STRONG' if cmf_strength > 0.1 else 'MODERATE' if cmf_strength > 0.05 else 'WEAK'
                })
            except:
                continue

        if not results:
            return {
                'strategy': 'Chaikin Money Flow Analysis',
                'description': 'Money flow strength and direction detection',
                'money_flowing_in': 0,
                'money_flowing_out': 0,
                'strong_inflow': 0,
                'strong_outflow': 0,
                'top_inflow': [],
                'top_outflow': []
            }

        df_results = pd.DataFrame(results).sort_values('cmf_value', ascending=False)
        money_in = df_results[df_results['direction'] == 'MONEY_IN']
        money_out = df_results[df_results['direction'] == 'MONEY_OUT']

        return {
            'strategy': 'Chaikin Money Flow Analysis',
            'description': 'Money flow strength and direction detection',
            'money_flowing_in': len(money_in),
            'money_flowing_out': len(money_out),
            'strong_inflow': len(df_results[df_results['intensity'] == 'STRONG']),
            'strong_outflow': len(df_results[(df_results['intensity'] == 'STRONG') & (df_results['direction'] == 'MONEY_OUT')]),
            'top_inflow': money_in.head(10).to_dict('records'),
            'top_outflow': money_out.head(10).to_dict('records')
        }

    # ========== STRATEGY 9: HIGH-CONVICTION SIGNALS ==========
    def strategy_9_high_conviction(self) -> Dict:
        """
        Identify coins with strong signal confluence (bullish>=15 or bearish<=-15).
        High confluence indicates strong market agreement.
        """
        if self.df_latest.empty:
            return {'error': 'No data available'}

        results = []

        for slug in self.df_latest['slug'].unique():
            coin_data = self.df_latest[self.df_latest['slug'] == slug]
            if len(coin_data) < 1:
                continue

            try:
                latest = coin_data.iloc[-1]
                bullish = latest.get('bullish', 0)
                bearish = latest.get('bearish', 0)
                neutral = latest.get('neutral', 0)

                total_signals = bullish + abs(bearish) + neutral

                conviction_level = 'LOW'
                conviction_score = 0
                direction = 'NEUTRAL'

                if bullish >= 15:
                    conviction_level = 'HIGH_BULLISH'
                    conviction_score = bullish
                    direction = 'BULLISH'
                elif bearish <= -15:
                    conviction_level = 'HIGH_BEARISH'
                    conviction_score = abs(bearish)
                    direction = 'BEARISH'
                elif bullish > abs(bearish):
                    conviction_level = 'MODERATE_BULLISH'
                    conviction_score = bullish
                    direction = 'BULLISH'
                elif bearish < -abs(bullish):
                    conviction_level = 'MODERATE_BEARISH'
                    conviction_score = abs(bearish)
                    direction = 'BEARISH'

                results.append({
                    'slug': slug,
                    'name': latest.get('name', slug),
                    'bullish_signals': int(bullish),
                    'bearish_signals': int(bearish),
                    'neutral_signals': int(neutral),
                    'conviction_level': conviction_level,
                    'conviction_score': conviction_score,
                    'direction': direction
                })
            except:
                continue

        if not results:
            return {
                'strategy': 'High-Conviction Signals',
                'description': 'Strong signal confluence (bullish>=15 or bearish<=-15)',
                'high_bullish_count': 0,
                'high_bearish_count': 0,
                'high_bullish_coins': [],
                'high_bearish_coins': [],
                'total_high_conviction': 0
            }

        df_results = pd.DataFrame(results).sort_values('conviction_score', ascending=False)
        high_bullish = df_results[df_results['conviction_level'] == 'HIGH_BULLISH']
        high_bearish = df_results[df_results['conviction_level'] == 'HIGH_BEARISH']

        return {
            'strategy': 'High-Conviction Signals',
            'description': 'Strong signal confluence (bullish>=15 or bearish<=-15)',
            'high_bullish_count': len(high_bullish),
            'high_bearish_count': len(high_bearish),
            'high_bullish_coins': high_bullish.head(10).to_dict('records'),
            'high_bearish_coins': high_bearish.head(10).to_dict('records'),
            'total_high_conviction': len(high_bullish) + len(high_bearish)
        }

    # ========== STRATEGY 10: SIGNAL CONSISTENCY SCORE ==========
    def strategy_10_signal_consistency(self) -> Dict:
        """
        Measure signal stability across timeframes.
        Consistency score: how often signals stay the same across periods.
        """
        if self.df_current.empty:
            return {'error': 'No data available'}

        results = []

        # Split into periods
        now = pd.Timestamp.now(tz='UTC')
        df_current = self.df_current.copy()
        df_current['timestamp'] = pd.to_datetime(df_current['timestamp'], utc=True)

        period_1h = df_current[(df_current['timestamp'] >= now - timedelta(hours=1))]
        period_4h = df_current[(df_current['timestamp'] >= now - timedelta(hours=4))]
        period_24h = df_current[(df_current['timestamp'] >= now - timedelta(hours=24))]

        for slug in self.df_current['slug'].unique()[:50]:  # Limit to top 50 for performance
            try:
                consistency_1h_4h = len(period_1h[period_1h['slug'] == slug]) > 0
                consistency_4h_24h = len(period_4h[period_4h['slug'] == slug]) > 0

                consistency_score = sum([consistency_1h_4h, consistency_4h_24h]) / 2

                latest = self.df_current[self.df_current['slug'] == slug].iloc[-1] if len(self.df_current[self.df_current['slug'] == slug]) > 0 else None

                if latest is not None:
                    results.append({
                        'slug': slug,
                        'name': latest.get('name', slug),
                        'consistency_score': float(consistency_score),
                        'stability': 'HIGH' if consistency_score > 0.8 else 'MEDIUM' if consistency_score > 0.5 else 'LOW'
                    })
            except:
                continue

        if not results:
            return {
                'strategy': 'Signal Consistency Score',
                'description': 'Signal stability across multiple timeframes',
                'highly_consistent': 0,
                'moderately_consistent': 0,
                'low_consistency': 0,
                'top_10_consistent': [],
                'avg_consistency': 0
            }

        df_results = pd.DataFrame(results).sort_values('consistency_score', ascending=False)

        return {
            'strategy': 'Signal Consistency Score',
            'description': 'Signal stability across multiple timeframes',
            'highly_consistent': len(df_results[df_results['stability'] == 'HIGH']),
            'moderately_consistent': len(df_results[df_results['stability'] == 'MEDIUM']),
            'low_consistency': len(df_results[df_results['stability'] == 'LOW']),
            'top_10_consistent': df_results.head(10).to_dict('records'),
            'avg_consistency': float(df_results['consistency_score'].mean()) if not df_results.empty else 0
        }

    # ========== STRATEGY 11: DMV COMPOSITE RANKINGS ==========
    def strategy_11_dmv_composite(self, scores_df: pd.DataFrame) -> Dict:
        """
        Rank coins by weighted Durability + Momentum + Valuation scores.
        Overall score = 0.4*Durability + 0.4*Momentum + 0.2*Valuation
        """
        if scores_df.empty:
            return {'error': 'No score data available'}

        try:
            # Get latest scores
            latest_scores = scores_df.drop_duplicates(subset=['slug'], keep='last')

            results = []
            for _, row in latest_scores.iterrows():
                durability = row.get('Durability_Score', 0) or 0
                momentum = row.get('Momentum_Score', 0) or 0
                valuation = row.get('Valuation_Score', 0) or 0

                # Weighted composite
                composite = (0.4 * durability + 0.4 * momentum + 0.2 * valuation)

                results.append({
                    'slug': row['slug'],
                    'name': row.get('name', row['slug']),
                    'durability_score': float(durability),
                    'momentum_score': float(momentum),
                    'valuation_score': float(valuation),
                    'composite_score': float(composite),
                    'rating': 'EXCELLENT' if composite > 80 else 'GOOD' if composite > 60 else 'FAIR' if composite > 40 else 'POOR'
                })

            if not results:
                return {
                    'strategy': 'DMV Composite Rankings',
                    'description': 'Weighted ranking of Durability, Momentum, Valuation (0.4/0.4/0.2)',
                    'excellent_coins': 0,
                    'good_coins': 0,
                    'fair_coins': 0,
                    'poor_coins': 0,
                    'top_10': [],
                    'bottom_10': [],
                    'avg_composite': 0
                }

            df_results = pd.DataFrame(results).sort_values('composite_score', ascending=False)
            excellent = df_results[df_results['rating'] == 'EXCELLENT']
            poor = df_results[df_results['rating'] == 'POOR']

            return {
                'strategy': 'DMV Composite Rankings',
                'description': 'Weighted ranking of Durability, Momentum, Valuation (0.4/0.4/0.2)',
                'excellent_coins': len(excellent),
                'good_coins': len(df_results[df_results['rating'] == 'GOOD']),
                'fair_coins': len(df_results[df_results['rating'] == 'FAIR']),
                'poor_coins': len(poor),
                'top_10': df_results.head(10).to_dict('records'),
                'bottom_10': poor.tail(10).to_dict('records'),
                'avg_composite': float(df_results['composite_score'].mean()) if not df_results.empty else 0
            }
        except Exception as e:
            return {'error': f'Analysis failed: {str(e)}'}

    # ========== STRATEGY 12: VOLATILITY-ADJUSTED RETURNS ==========
    def strategy_12_volatility_adjusted_returns(self) -> Dict:
        """
        Calculate risk-adjusted returns (returns normalized by volatility).
        Sharpe-like metric: identifies best risk-adjusted opportunities.
        """
        if self.df_latest.empty or len(self.df_latest) < 5:
            return {'error': 'Insufficient data for volatility analysis'}

        results = []

        for slug in self.df_latest['slug'].unique():
            coin_data = self.df_latest[self.df_latest['slug'] == slug].sort_values('timestamp')
            if len(coin_data) < 5:
                continue

            try:
                # Get price changes
                closes = coin_data.get('close', pd.Series()).values if 'close' in coin_data.columns else []
                if len(closes) < 2:
                    continue

                price_changes = np.diff(closes) / closes[:-1]

                # Returns and volatility
                returns = np.mean(price_changes)
                volatility = np.std(price_changes)

                # Risk-adjusted return (Sharpe-like, assuming 0 risk-free rate)
                if volatility > 0:
                    risk_adjusted = returns / volatility
                else:
                    risk_adjusted = 0

                latest = coin_data.iloc[-1]

                results.append({
                    'slug': slug,
                    'name': latest.get('name', slug),
                    'returns_pct': float(returns * 100),
                    'volatility_pct': float(volatility * 100),
                    'risk_adjusted_return': float(risk_adjusted),
                    'quality': 'HIGH' if risk_adjusted > 0.5 else 'MEDIUM' if risk_adjusted > 0 else 'LOW'
                })
            except:
                continue

        if not results:
            return {
                'strategy': 'Volatility-Adjusted Returns',
                'description': 'Risk-adjusted returns (returns / volatility ratio)',
                'high_quality_trades': 0,
                'medium_quality_trades': 0,
                'top_10_risk_adjusted': [],
                'worst_10_risk_adjusted': [],
                'avg_risk_adjusted': 0
            }

        df_results = pd.DataFrame(results).sort_values('risk_adjusted_return', ascending=False)

        return {
            'strategy': 'Volatility-Adjusted Returns',
            'description': 'Risk-adjusted returns (returns / volatility ratio)',
            'high_quality_trades': len(df_results[df_results['quality'] == 'HIGH']),
            'medium_quality_trades': len(df_results[df_results['quality'] == 'MEDIUM']),
            'top_10_risk_adjusted': df_results.head(10).to_dict('records'),
            'worst_10_risk_adjusted': df_results.tail(10).to_dict('records'),
            'avg_risk_adjusted': float(df_results['risk_adjusted_return'].mean()) if not df_results.empty else 0
        }

    # ========== STRATEGY 13: RISK/REWARD RATIO ANALYSIS ==========
    def strategy_13_risk_reward_ratios(self) -> Dict:
        """
        Identify best risk/reward opportunities using ratio signals.
        Coins with favorable risk/reward vs Bitcoin benchmark.
        """
        if self.df_latest.empty:
            return {'error': 'No data available'}

        results = []

        for slug in self.df_latest['slug'].unique():
            coin_data = self.df_latest[self.df_latest['slug'] == slug]
            if len(coin_data) < 1:
                continue

            try:
                latest = coin_data.iloc[-1]

                # Look for ratio signal columns
                ratio_cols = [col for col in coin_data.columns if 'ratio' in col.lower() and 'signal' in col.lower()]

                if ratio_cols:
                    ratio_signals = [latest.get(col, 0) for col in ratio_cols if col in latest]
                    if ratio_signals:
                        bullish_ratio = sum(1 for s in ratio_signals if s > 0)
                        bearish_ratio = sum(1 for s in ratio_signals if s < 0)

                        risk_reward_score = bullish_ratio - bearish_ratio

                        results.append({
                            'slug': slug,
                            'name': latest.get('name', slug),
                            'bullish_ratio': bullish_ratio,
                            'bearish_ratio': bearish_ratio,
                            'risk_reward_score': risk_reward_score,
                            'opportunity': 'FAVORABLE' if risk_reward_score > 0 else 'UNFAVORABLE'
                        })
            except:
                continue

        if not results:
            return {
                'strategy': 'Risk/Reward Ratio Analysis',
                'description': 'Best risk/reward opportunities vs Bitcoin benchmark',
                'favorable_opportunities': 0,
                'unfavorable_opportunities': 0,
                'top_10_favorable': [],
                'top_10_unfavorable': []
            }

        df_results = pd.DataFrame(results).sort_values('risk_reward_score', ascending=False)
        favorable = df_results[df_results['opportunity'] == 'FAVORABLE']

        return {
            'strategy': 'Risk/Reward Ratio Analysis',
            'description': 'Best risk/reward opportunities vs Bitcoin benchmark',
            'favorable_opportunities': len(favorable),
            'unfavorable_opportunities': len(df_results[df_results['opportunity'] == 'UNFAVORABLE']),
            'top_10_favorable': favorable.head(10).to_dict('records'),
            'top_10_unfavorable': df_results[df_results['opportunity'] == 'UNFAVORABLE'].head(10).to_dict('records')
        }

    # ========== STRATEGY 14: BITCOIN OUTPERFORMANCE ==========
    def strategy_14_bitcoin_outperformance(self, btc_data: pd.DataFrame) -> Dict:
        """
        Identify coins significantly outperforming or underperforming Bitcoin.
        Relative strength vs BTC benchmark.
        """
        if self.df_latest.empty or btc_data.empty:
            return {'error': 'Insufficient data for comparison'}

        results = []

        try:
            # Get Bitcoin latest performance
            btc_latest = btc_data.sort_values('timestamp').iloc[-1] if len(btc_data) > 0 else None
            if btc_latest is None:
                return {'error': 'No Bitcoin data'}

            btc_momentum = btc_latest.get('m_mom_rsi_9', 50)
            btc_durability = btc_latest.get('d_obv', 0)

            for slug in self.df_latest['slug'].unique():
                if slug == 'bitcoin':
                    continue

                coin_data = self.df_latest[self.df_latest['slug'] == slug]
                if len(coin_data) < 1:
                    continue

                latest = coin_data.iloc[-1]

                coin_momentum = latest.get('m_mom_rsi_9', 50)
                coin_durability = latest.get('d_obv', 0)

                momentum_diff = coin_momentum - btc_momentum

                outperformance = 'OUTPERFORMING' if momentum_diff > 5 else 'UNDERPERFORMING' if momentum_diff < -5 else 'IN_LINE'

                results.append({
                    'slug': slug,
                    'name': latest.get('name', slug),
                    'momentum_vs_btc': float(momentum_diff),
                    'outperformance': outperformance,
                    'strength': 'STRONG' if abs(momentum_diff) > 20 else 'MODERATE'
                })
        except Exception as e:
            return {'error': f'Analysis failed: {str(e)}'}

        if not results:
            return {
                'strategy': 'Bitcoin Outperformance',
                'description': 'Coins significantly outperforming/underperforming Bitcoin',
                'outperforming': 0,
                'underperforming': 0,
                'in_line': 0,
                'top_10_outperformers': [],
                'top_10_underperformers': [],
                'avg_momentum_vs_btc': 0
            }

        df_results = pd.DataFrame(results).sort_values('momentum_vs_btc', ascending=False)
        outperforming = df_results[df_results['outperformance'] == 'OUTPERFORMING']
        underperforming = df_results[df_results['outperformance'] == 'UNDERPERFORMING']

        return {
            'strategy': 'Bitcoin Outperformance',
            'description': 'Coins significantly outperforming/underperforming Bitcoin',
            'outperforming': len(outperforming),
            'underperforming': len(underperforming),
            'in_line': len(df_results[df_results['outperformance'] == 'IN_LINE']),
            'top_10_outperformers': outperforming.head(10).to_dict('records'),
            'top_10_underperformers': underperforming.head(10).to_dict('records'),
            'avg_momentum_vs_btc': float(df_results['momentum_vs_btc'].mean()) if not df_results.empty else 0
        }

    # ========== STRATEGY 15: MARKET LEADERSHIP CHANGES ==========
    def strategy_15_leadership_changes(self) -> Dict:
        """
        Track coins gaining/losing ranking momentum.
        Identify emerging leaders and declining performers.
        """
        if self.df_current.empty or len(self.df_current) < 50:
            return {'error': 'Insufficient data for trend detection'}

        results = []

        try:
            df_current_copy = self.df_current.copy()
            df_current_copy['timestamp'] = pd.to_datetime(df_current_copy['timestamp'], utc=True)

            now = pd.Timestamp.now(tz='UTC')
            recent_24h = df_current_copy[df_current_copy['timestamp'] >= now - timedelta(hours=24)]
            recent_4h = df_current_copy[df_current_copy['timestamp'] >= now - timedelta(hours=4)]

            for slug in df_current_copy['slug'].unique()[:100]:  # Top 100 for performance
                try:
                    # Compare momentum across periods
                    momentum_4h = recent_4h[recent_4h['slug'] == slug].get('m_mom_rsi_9', pd.Series()).mean() if len(recent_4h[recent_4h['slug'] == slug]) > 0 else 50
                    momentum_24h = recent_24h[recent_24h['slug'] == slug].get('m_mom_rsi_18', pd.Series()).mean() if len(recent_24h[recent_24h['slug'] == slug]) > 0 else 50

                    momentum_change = momentum_4h - momentum_24h
                    leadership_status = 'EMERGING' if momentum_change > 5 else 'DECLINING' if momentum_change < -5 else 'STABLE'

                    latest = df_current_copy[df_current_copy['slug'] == slug].iloc[-1] if len(df_current_copy[df_current_copy['slug'] == slug]) > 0 else None
                    if latest is not None:
                        results.append({
                            'slug': slug,
                            'name': latest.get('name', slug),
                            'momentum_change': float(momentum_change),
                            'status': leadership_status,
                            'recent_strength': 'STRONG' if momentum_4h > 60 else 'WEAK' if momentum_4h < 40 else 'NEUTRAL'
                        })
                except:
                    continue

            if not results:
                return {
                    'strategy': 'Market Leadership Changes',
                    'description': 'Coins gaining/losing ranking momentum',
                    'emerging_leaders': 0,
                    'declining_performers': 0,
                    'stable_performers': 0,
                    'top_10_emerging': [],
                    'top_10_declining': [],
                    'avg_momentum_change': 0
                }

            df_results = pd.DataFrame(results).sort_values('momentum_change', ascending=False)
            emerging = df_results[df_results['status'] == 'EMERGING']
            declining = df_results[df_results['status'] == 'DECLINING']

            return {
                'strategy': 'Market Leadership Changes',
                'description': 'Coins gaining/losing ranking momentum',
                'emerging_leaders': len(emerging),
                'declining_performers': len(declining),
                'stable_performers': len(df_results[df_results['status'] == 'STABLE']),
                'top_10_emerging': emerging.head(10).to_dict('records'),
                'top_10_declining': declining.tail(10).to_dict('records'),
                'avg_momentum_change': float(df_results['momentum_change'].mean()) if not df_results.empty else 0
            }
        except Exception as e:
            return {'error': f'Analysis failed: {str(e)}'}


# ============================================================================
# REPORT GENERATION
# ============================================================================

class ReportGenerator:
    """Generate formatted market analysis reports"""

    def __init__(self, timeframe_hours: int, timeframe_name: str):
        self.timeframe_hours = timeframe_hours
        self.timeframe_name = timeframe_name
        self.report = {}

    def add_strategy(self, strategy_name: str, strategy_result: Dict):
        """Add strategy result to report"""
        self.report[strategy_name] = strategy_result

    def generate_summary(self) -> Dict:
        """Generate summary statistics"""
        summary = {
            'timeframe': self.timeframe_name,
            'timeframe_hours': self.timeframe_hours,
            'generated_at': datetime.now().isoformat(),
            'strategies_analyzed': len(self.report),
            'total_coins_analyzed': 250
        }
        return summary

    def to_dict(self) -> Dict:
        """Convert report to dictionary"""
        return {
            'summary': self.generate_summary(),
            'strategies': self.report
        }

    def to_json(self, filepath: str = None):
        """Export report to JSON"""
        report_dict = self.to_dict()
        json_str = json.dumps(report_dict, indent=2, default=str)

        if filepath:
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, 'w') as f:
                f.write(json_str)
            print(f"✓ Report saved to {filepath}")

        return json_str

    def to_csv(self, filepath: str = None):
        """Export top strategies to CSV"""
        data = []

        for strategy_name, strategy_data in self.report.items():
            if isinstance(strategy_data, dict) and 'top_10' in strategy_data:
                for item in strategy_data.get('top_10', []):
                    row = {
                        'timeframe': self.timeframe_name,
                        'strategy': strategy_name,
                        **item
                    }
                    data.append(row)

        if data:
            df = pd.DataFrame(data)
            if filepath:
                Path(filepath).parent.mkdir(parents=True, exist_ok=True)
                df.to_csv(filepath, index=False)
                print(f"✓ CSV saved to {filepath}")
            return df

        return None

    def print_summary(self):
        """Print text summary to console"""
        print(f"\n{'='*80}")
        print(f"MARKET INSIGHTS REPORT - {self.timeframe_name.upper()}")
        print(f"{'='*80}")
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"Timeframe: {self.timeframe_hours}hrs")
        print(f"Coins Analyzed: 250")
        print(f"Strategies: {len(self.report)}\n")

        for idx, (strategy_name, strategy_data) in enumerate(self.report.items(), 1):
            print(f"{idx}. {strategy_name}")
            if isinstance(strategy_data, dict):
                if 'error' in strategy_data:
                    print(f"   ⚠ {strategy_data['error']}")
                else:
                    print(f"   ✓ Analysis Complete")
                    # Print key findings
                    for key, value in strategy_data.items():
                        if key not in ['top_10', 'bottom_10', 'top_10_spikes', 'top_10_consistent', 'top_10_bullish_coins', 'top_10_bearish_coins', 'bullish_divergence_coins', 'bearish_divergence_coins', 'top_10_uptrend', 'top_10_downtrend', 'top_10_outperformers', 'top_10_underperformers', 'top_10_emerging', 'top_10_declining', 'top_10_favorable', 'top_10_unfavorable', 'top_accumulation', 'top_distribution', 'top_inflow', 'top_outflow', 'bullish_spikes', 'high_bullish_coins', 'high_bearish_coins']:
                            if isinstance(value, (int, float)):
                                print(f"     - {key}: {value}")
            print()


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description='Market Insights Report Generator')
    parser.add_argument('--timeframe', type=str, choices=['4h', '24h', '108h', 'all'],
                       default='all', help='Timeframe for analysis')
    parser.add_argument('--export', type=str, choices=['json', 'csv', 'both', 'none'],
                       default='none', help='Export format')
    parser.add_argument('--output-dir', type=str, default='./reports',
                       help='Output directory for reports')

    args = parser.parse_args()

    print("🔍 Market Insights Report Generator")
    print("=" * 80)

    # Initialize database manager
    print("\n📊 Connecting to databases...")
    db_manager = DatabaseManager()

    # Define timeframes
    timeframes = {
        '4h': (4, '4-Hour'),
        '24h': (24, '24-Hour'),
        '108h': (108, '108-Hour')
    }

    if args.timeframe == 'all':
        timeframes_to_run = timeframes.items()
    else:
        timeframes_to_run = [(args.timeframe, timeframes[args.timeframe])]

    all_reports = {}

    for tf_key, (hours, name) in timeframes_to_run:
        print(f"\n{'─'*80}")
        print(f"🕐 Analyzing {name} timeframe ({hours} hours)...")
        print(f"{'─'*80}")

        # Fetch data
        print("  • Fetching current data from cp_ai...")
        df_current = db_manager.fetch_dmv_all_current(hours)
        df_scores = db_manager.fetch_dmv_scores_current(hours)
        df_btc = db_manager.fetch_bitcoin_data(hours, use_backtest=False)

        if df_current.empty:
            print(f"  ⚠ No current data available for {name}")
            continue

        print(f"  • Data loaded: {len(df_current)} records, {df_current['slug'].nunique()} unique coins")

        # Initialize analyzer
        analyzer = MarketAnalyzer(df_current, pd.DataFrame(), hours)

        # Run all 15 strategies
        print(f"\n  📈 Running 15 analytical strategies...")

        report = ReportGenerator(hours, name)

        print("    1. Multi-Timeframe RSI Confluence...", end=" ", flush=True)
        report.add_strategy("1. Multi-Timeframe RSI Confluence", analyzer.strategy_1_rsi_confluence())
        print("✓")

        print("    2. MACD + Stochastic Alignment...", end=" ", flush=True)
        report.add_strategy("2. MACD + Stochastic Alignment", analyzer.strategy_2_macd_stochastic_alignment())
        print("✓")

        print("    3. Moving Average Crossover...", end=" ", flush=True)
        report.add_strategy("3. Moving Average Crossover", analyzer.strategy_3_ma_crossover())
        print("✓")

        print("    4. Momentum Acceleration...", end=" ", flush=True)
        report.add_strategy("4. Momentum Acceleration", analyzer.strategy_4_momentum_acceleration())
        print("✓")

        print("    5. RSI Divergence Detection...", end=" ", flush=True)
        report.add_strategy("5. RSI Divergence Detection", analyzer.strategy_5_rsi_divergence())
        print("✓")

        print("    6. Volume Spike Detection...", end=" ", flush=True)
        report.add_strategy("6. Volume Spike Detection", analyzer.strategy_6_volume_spike())
        print("✓")

        print("    7. On-Balance Volume Trends...", end=" ", flush=True)
        report.add_strategy("7. On-Balance Volume Trends", analyzer.strategy_7_obv_trends())
        print("✓")

        print("    8. Chaikin Money Flow...", end=" ", flush=True)
        report.add_strategy("8. Chaikin Money Flow", analyzer.strategy_8_cmf_analysis())
        print("✓")

        print("    9. High-Conviction Signals...", end=" ", flush=True)
        report.add_strategy("9. High-Conviction Signals", analyzer.strategy_9_high_conviction())
        print("✓")

        print("   10. Signal Consistency Score...", end=" ", flush=True)
        report.add_strategy("10. Signal Consistency Score", analyzer.strategy_10_signal_consistency())
        print("✓")

        print("   11. DMV Composite Rankings...", end=" ", flush=True)
        report.add_strategy("11. DMV Composite Rankings", analyzer.strategy_11_dmv_composite(df_scores))
        print("✓")

        print("   12. Volatility-Adjusted Returns...", end=" ", flush=True)
        report.add_strategy("12. Volatility-Adjusted Returns", analyzer.strategy_12_volatility_adjusted_returns())
        print("✓")

        print("   13. Risk/Reward Ratio Analysis...", end=" ", flush=True)
        report.add_strategy("13. Risk/Reward Ratio Analysis", analyzer.strategy_13_risk_reward_ratios())
        print("✓")

        print("   14. Bitcoin Outperformance...", end=" ", flush=True)
        report.add_strategy("14. Bitcoin Outperformance", analyzer.strategy_14_bitcoin_outperformance(df_btc))
        print("✓")

        print("   15. Market Leadership Changes...", end=" ", flush=True)
        report.add_strategy("15. Market Leadership Changes", analyzer.strategy_15_leadership_changes())
        print("✓")

        # Print summary
        report.print_summary()

        # Store report
        all_reports[tf_key] = report

    # Export reports
    if args.export != 'none' and all_reports:
        print(f"\n{'═'*80}")
        print("📁 Exporting Reports...")
        print(f"{'═'*80}")

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        for tf_key, report in all_reports.items():
            if args.export in ['json', 'both']:
                json_path = output_dir / f"market_insights_{tf_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                report.to_json(str(json_path))

            if args.export in ['csv', 'both']:
                csv_path = output_dir / f"market_insights_{tf_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                report.to_csv(str(csv_path))

    print(f"\n{'═'*80}")
    print("✅ Market Insights Analysis Complete")
    print(f"{'═'*80}\n")


if __name__ == '__main__':
    main()
