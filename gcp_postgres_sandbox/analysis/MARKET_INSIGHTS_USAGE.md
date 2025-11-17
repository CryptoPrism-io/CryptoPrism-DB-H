# Market Insights Report Generator

## Overview

The **Market Insights Report Generator** (`market_insights_report.py`) is a comprehensive cryptocurrency market analysis tool that analyzes 250 cryptocurrencies across **15 different analytical strategies**. It generates detailed market intelligence reports for 3 critical timeframes: **4-hour, 24-hour, and 108-hour windows**.

All analysis uses REAL data from your CryptoPrism-DB database with no synthetic data.

## Installation & Setup

### Requirements
- Python 3.8+
- Database connection credentials (DB_HOST, DB_USER, DB_PASSWORD, etc.)
- Required packages: pandas, numpy, sqlalchemy, psycopg2

### Database Requirements
The script requires these tables in `cp_ai` database:
- `FE_DMV_ALL` - Complete signal data with all indicators
- `FE_DMV_SCORES` - Durability, Momentum, Valuation composite scores
- `FE_DMV_BITCOIN` - Bitcoin benchmark data

## Quick Start

### Run Full Analysis (All Timeframes + Exports)
```bash
python gcp_postgres_sandbox/analysis/market_insights_report.py \
  --timeframe all \
  --export both \
  --output-dir ./reports
```

### Run Single Timeframe
```bash
# 4-hour analysis only
python gcp_postgres_sandbox/analysis/market_insights_report.py --timeframe 4h

# 24-hour analysis only
python gcp_postgres_sandbox/analysis/market_insights_report.py --timeframe 24h

# 108-hour analysis only
python gcp_postgres_sandbox/analysis/market_insights_report.py --timeframe 108h
```

### Export Options
```bash
# JSON only
python gcp_postgres_sandbox/analysis/market_insights_report.py --timeframe all --export json

# CSV only
python gcp_postgres_sandbox/analysis/market_insights_report.py --timeframe all --export csv

# Both JSON and CSV
python gcp_postgres_sandbox/analysis/market_insights_report.py --timeframe all --export both

# No export (console output only)
python gcp_postgres_sandbox/analysis/market_insights_report.py --timeframe all --export none
```

### Custom Output Directory
```bash
python gcp_postgres_sandbox/analysis/market_insights_report.py \
  --timeframe all \
  --export both \
  --output-dir /path/to/custom/directory
```

## 15 Analytical Strategies

### Strategy 1: Multi-Timeframe RSI Confluence
**Category:** Momentum & Trend Analysis

Identifies coins with aligned RSI signals across multiple timeframes (9, 18, 27, 54, 108 periods). Strong confluence indicates momentum agreement across short, medium, and long-term perspectives.

**Key Metrics:**
- `confluence_strength`: 0-1 scale indicating signal alignment
- `direction`: BULLISH, BEARISH, or NEUTRAL
- `bullish_rsi` / `bearish_rsi`: Count of aligned signals

**Use Case:** Find coins with consistent momentum signals across all timeframes for high-confidence trades.

---

### Strategy 2: MACD + Stochastic Alignment
**Category:** Momentum & Trend Analysis

Detects strong momentum when both MACD and Stochastic oscillators agree on direction. Higher alignment score = stronger momentum signal.

**Key Metrics:**
- `alignment_score`: 0-1 scale of indicator agreement
- `macd_signal` / `stoch_signal`: Individual indicator signals
- `aligned_percentage`: % of coins with aligned signals

**Use Case:** Identify momentum breakouts validated by multiple oscillators.

---

### Strategy 3: Moving Average Crossover
**Category:** Momentum & Trend Analysis

Tracks SMA crossovers (9/18/21/108) to identify trend direction and strength. Classic technical analysis pattern.

**Key Metrics:**
- `trend`: STRONG_UPTREND, UPTREND, DOWNTREND, STRONG_DOWNTREND, SIDEWAYS
- `strength`: -1.0 to +1.0 scale
- SMA levels for reference

**Use Case:** Identify trend changes and establish trend-following positions.

---

### Strategy 4: Momentum Acceleration
**Category:** Momentum & Trend Analysis

Compares momentum across timeframes (4h vs 24h) to find coins with accelerating momentum. Positive acceleration = momentum increasing.

**Key Metrics:**
- `acceleration`: Momentum 4h minus Momentum 24h
- `direction`: ACCELERATING_UP or ACCELERATING_DOWN
- `momentum_4h` / `momentum_24h`: Raw momentum values

**Use Case:** Early detection of trend reversals and momentum shifts.

---

### Strategy 5: RSI Divergence Detection
**Category:** Momentum & Trend Analysis

Identifies price/RSI divergences signaling potential reversals:
- **Bullish divergence:** Price makes lower low but RSI makes higher low → upside reversal
- **Bearish divergence:** Price makes higher high but RSI makes lower high → downside reversal

**Key Metrics:**
- `divergence_type`: BULLISH, BEARISH, or NONE
- `price_trend` / `rsi_trend`: Direction of each indicator
- `strength`: Divergence strength

**Use Case:** Trade mean-reversion setups at divergence points.

---

### Strategy 6: Volume Spike Detection
**Category:** Volume & Liquidity Analysis

Identifies unusual volume activity (>2x historical average) correlated with price movement. Volume spikes confirm conviction.

**Key Metrics:**
- `volume_ratio`: Current volume / average volume
- `price_correlation`: POSITIVE or NEGATIVE
- `volume_strength`: STRONG (>5x) or MODERATE (2-5x)

**Use Case:** Find breakouts confirmed by volume surge.

---

### Strategy 7: On-Balance Volume Trends
**Category:** Volume & Liquidity Analysis

Tracks OBV momentum to detect accumulation/distribution patterns:
- **Positive OBV trend:** Accumulation - money flowing in
- **Negative OBV trend:** Distribution - money flowing out

**Key Metrics:**
- `pattern`: ACCUMULATION or DISTRIBUTION
- `obv_trend`: Trend percentage
- `strength`: STRONG (>10% change) or MODERATE

**Use Case:** Identify insider buying/selling activity before price moves.

---

### Strategy 8: Chaikin Money Flow Analysis
**Category:** Volume & Liquidity Analysis

Measures money flow strength and direction:
- **Positive CMF:** Money flowing into asset (bullish)
- **Negative CMF:** Money flowing out (bearish)

**Key Metrics:**
- `cmf_value`: -1.0 to +1.0 flow direction
- `direction`: MONEY_IN or MONEY_OUT
- `intensity`: STRONG, MODERATE, or WEAK

**Use Case:** Validate price moves with money flow confirmation.

---

### Strategy 9: High-Conviction Signals
**Category:** Signal & Sentiment Analysis

Identifies coins with strong signal confluence:
- **HIGH_BULLISH:** ≥15 bullish signals
- **HIGH_BEARISH:** ≤-15 bearish signals

**Key Metrics:**
- `bullish_signals` / `bearish_signals`: Count of directional signals
- `conviction_level`: Strength of signal agreement
- `total_high_conviction`: Count of high-conviction coins

**Use Case:** Find consensus trades with strongest market agreement.

---

### Strategy 10: Signal Consistency Score
**Category:** Signal & Sentiment Analysis

Measures signal stability across timeframes. Consistent signals across 1h/4h/24h indicate stable trend.

**Key Metrics:**
- `consistency_score`: 0-1 scale of stability
- `stability`: HIGH (>0.8), MEDIUM (0.5-0.8), or LOW (<0.5)
- Counts by stability level

**Use Case:** Find reliable trends less prone to sudden reversals.

---

### Strategy 11: DMV Composite Rankings
**Category:** Signal & Sentiment Analysis

Ranks coins by weighted composite score of three dimensions:
- **Durability (40%):** Trend & volume strength
- **Momentum (40%):** Price momentum indicators
- **Valuation (20%):** Risk/reward assessment

**Key Metrics:**
- `composite_score`: Weighted 0-100 scale
- `rating`: EXCELLENT (>80), GOOD (60-80), FAIR (40-60), POOR (<40)
- Individual D/M/V scores

**Use Case:** Holistic coin quality assessment using balanced metrics.

---

### Strategy 12: Volatility-Adjusted Returns
**Category:** Risk & Volatility Analysis

Calculates Sharpe-like ratio (returns / volatility) for risk-adjusted opportunity identification. Higher = better risk-adjusted returns.

**Key Metrics:**
- `returns_pct`: Expected return %
- `volatility_pct`: Volatility %
- `risk_adjusted_return`: Risk-adjusted score
- `quality`: HIGH (>0.5), MEDIUM (0-0.5), LOW (<0)

**Use Case:** Find best opportunities relative to risk taken.

---

### Strategy 13: Risk/Reward Ratio Analysis
**Category:** Risk & Volatility Analysis

Identifies coins with favorable risk/reward vs Bitcoin benchmark using ratio signals.

**Key Metrics:**
- `risk_reward_score`: Net ratio signal count
- `opportunity`: FAVORABLE or UNFAVORABLE
- `bullish_ratio` / `bearish_ratio`: Individual ratio signals

**Use Case:** Allocate capital to coins offering best downside protection.

---

### Strategy 14: Bitcoin Outperformance
**Category:** Relative Performance

Identifies coins significantly outperforming or underperforming Bitcoin benchmark.

**Key Metrics:**
- `momentum_vs_btc`: Momentum difference from Bitcoin
- `outperformance`: OUTPERFORMING (>5 points), UNDERPERFORMING (<-5), or IN_LINE
- `strength`: STRONG (>20 point difference) or MODERATE

**Use Case:** Identify altseason plays and laggards.

---

### Strategy 15: Market Leadership Changes
**Category:** Relative Performance

Tracks coins gaining/losing ranking momentum to identify emerging leaders and declining performers.

**Key Metrics:**
- `momentum_change`: 4h momentum minus 24h momentum
- `status`: EMERGING, DECLINING, or STABLE
- `recent_strength`: STRONG (>60), WEAK (<40), or NEUTRAL

**Use Case:** Early detection of leadership shifts in crypto market.

---

## Output Format

### Console Output
The script prints analysis summary for each timeframe including strategy execution status and key metrics.

### JSON Export
Detailed report with all strategy results, top/bottom performers, and statistical summaries.

**File Format:** `market_insights_{timeframe}_{timestamp}.json`

```json
{
  "summary": {
    "timeframe": "4-Hour",
    "timeframe_hours": 4,
    "generated_at": "2025-11-14T00:44:28.123456",
    "strategies_analyzed": 15,
    "total_coins_analyzed": 250
  },
  "strategies": {
    "1. Multi-Timeframe RSI Confluence": {
      "strategy": "Multi-Timeframe RSI Confluence",
      "description": "RSI signals aligned across 9/18/27/54/108 periods",
      "top_10": [...],
      "bottom_10": [...],
      "avg_confluence": 0.75
    },
    ...
  }
}
```

### CSV Export
Top 10 performers from each strategy in CSV format for spreadsheet analysis.

**File Format:** `market_insights_{timeframe}_{timestamp}.csv`

**Columns:**
- `timeframe`: 4-Hour, 24-Hour, or 108-Hour
- `strategy`: Strategy name
- `slug`: Coin identifier
- `name`: Coin full name
- `{strategy_specific_columns}`: Metrics for each strategy

---

## Report Interpretation Guide

### High-Conviction Trading Signals
Look for coins appearing in multiple top-10 lists:
- Strategy 9: High-Conviction Signals
- Strategy 11: DMV Composite Rankings (GOOD or better rating)
- Strategy 3: Moving Average Crossover (UPTREND or better)

### Momentum Plays
Use Strategies 1, 2, 4, 5 in combination:
- All show bullish confluence = strong momentum
- Strategy 5 (RSI divergence) = reversal opportunity
- Strategy 4 (momentum acceleration) = trend extension

### Volume Analysis
Validate with Strategies 6, 7, 8:
- Volume spike + OBV accumulation = accumulation phase
- All three bearish = strong selling pressure

### Risk Management
Use Strategies 12, 13, 14:
- Strategy 12: Avoid high volatility coins
- Strategy 13: Ensure favorable risk/reward
- Strategy 14: Don't fight Bitcoin strength

### Market Timing
Combine Strategies 3, 10, 15:
- Moving average = primary trend
- Consistency score = trend reliability
- Leadership changes = regime shifts

---

## Performance Benchmarks

The script analyzes 250 coins across 15 strategies:

| Timeframe | Execution Time | Data Points | Typical Signals |
|-----------|-----------------|------------|-----------------|
| 4-hour    | ~5 seconds      | 796        | 23 bullish, 132 bearish |
| 24-hour   | ~5 seconds      | 4,776      | 23 bullish, 132 bearish |
| 108-hour  | ~6 seconds      | 19,902     | 23 bullish, 132 bearish |
| All three | ~20 seconds     | 25,474     | Complete analysis |

---

## Troubleshooting

### "No data available for X-Hour"
- Ensure database has recent data (within the last 108 hours)
- Check database connections are active
- Verify FE_DMV_ALL table is populated

### Empty results for specific strategies
- Some strategies may return no results if data doesn't meet threshold
- Example: Volume Spike Detection only returns coins with >2x volume
- This is normal behavior - indicates no signals for that pattern

### Connection Errors
```bash
# Verify environment variables are loaded
set -a && source .env && set +a

# Test connection
python -c "from gcp_postgres_sandbox.utils import get_db_engines; get_db_engines()"
```

### CSV Export Issues
- Ensure output directory exists and is writable
- Use `--output-dir ./reports` or full path like `/tmp/reports`
- CSV only exports top-10 performers (not all strategies)

---

## Advanced Usage

### Integration with Monitoring Systems
JSON output can be parsed for automated alerts:

```python
import json

with open('market_insights_4h_latest.json') as f:
    report = json.load(f)

# Alert if high bullish conviction
bullish = report['strategies']['9. High-Conviction Signals']['high_bullish_count']
if bullish > 20:
    print(f"Alert: {bullish} coins showing high bullish conviction!")
```

### Scheduled Analysis
Use system scheduler (cron/Task Scheduler) to run hourly:

```bash
# Linux/Mac: Add to crontab
0 * * * * cd /path/to/repo && bash -c '. .env && python gcp_postgres_sandbox/analysis/market_insights_report.py --timeframe all --export both --output-dir ./reports'
```

### Custom Analysis
Modify the script to:
- Add new strategies (extend `MarketAnalyzer` class)
- Change weighting in DMV Composite (line 833)
- Adjust signal thresholds (various strategy parameters)
- Add database filtering (e.g., top 50 coins only)

---

## Data Sources & Indicators

The analysis uses these raw data fields from your database:

**Price Data:**
- `close` - OHLCV close price
- `volume` - Trading volume
- `open`, `high`, `low` - Price levels

**Technical Indicators (pre-calculated in database):**
- **Momentum:** RSI (9/18/27/54/108), MACD, Stochastic
- **Volume:** OBV, CMF, Volume ratios
- **Trend:** SMAs (9/18/21/108), EMA (9/18/21/108)
- **Risk:** Volatility, Bollinger Bands, Price changes

**Composite Scores (pre-calculated):**
- **Durability Score:** Volume + trend strength
- **Momentum Score:** RSI + MACD + Stochastic alignment
- **Valuation Score:** Risk/reward vs Bitcoin

---

## Important Notes

⚠️ **No Synthetic Data**: All analysis uses REAL cryptocurrency data from your database. If insufficient real data exists, strategies will report zero results.

⚠️ **Not Investment Advice**: This tool is for educational and analytical purposes. Always conduct your own due diligence before trading.

⚠️ **Past Performance**: Historical analysis does not guarantee future results.

---

## Support & Customization

For questions or custom analysis needs, refer to the inline code documentation in `market_insights_report.py`:

- Each strategy has detailed docstrings
- Code comments explain calculation methods
- Error handling reports missing data gracefully

---

Generated with 🤖 Claude Code
Last Updated: November 14, 2025
