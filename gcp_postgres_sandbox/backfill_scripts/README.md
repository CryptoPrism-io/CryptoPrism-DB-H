# Backfill Scripts for cp_backtest_h

## Purpose
These scripts process historical OHLCV data and populate cp_backtest_h database with missing hourly data.

## Key Difference from Regular Scripts
- **Regular scripts** (in `technical_analysis/`): Filter to LATEST timestamp only (for real-time updates)
- **Backfill scripts** (this folder): Process ALL timestamps (for historical backfill)

## Files

### 1. backfill_dmv_tvv_pct.py
**Modified:** Removed line that filters to latest timestamp only
```python
# ORIGINAL (regular script):
pct_change = df.loc[df.groupby('slug')['timestamp'].idxmax()]  # Only latest

# BACKFILL (this version):
pct_change = df.copy()  # All timestamps
```

**Input:** `cp_ai.ohlcv_1h_250_coins`
**Output:** Appends to `cp_backtest_h`: FE_TVV, FE_TVV_SIGNALS, FE_PCT_CHANGE

### 2. backfill_dmv_osc_mom_rat.py
**Modified:** No changes needed (no timestamp filtering in original)
**Input:** `cp_ai.ohlcv_1h_250_coins`
**Output:** Appends to `cp_backtest_h`: FE_OSCILLATORS_SIGNALS, FE_MOMENTUM_SIGNALS, FE_RATIOS_SIGNALS

### 3. backfill_dmv_core.py
**Modified:** No changes needed (no timestamp filtering in original)
**Input:** All FE_*_SIGNALS tables from `cp_backtest_h`
**Output:** Appends to `cp_backtest_h`: FE_DMV_ALL, FE_DMV_SCORES

## Execution Order (CRITICAL!)

Scripts **MUST** run in this exact sequence:

```bash
# Step 1: Fetch historical data into cp_ai
Rscript ../data_ingestion/gcp_ohlcv_1h_historical.R
# Fetches Sept 10 - Oct 30 data into cp_ai

# Step 2: TVV & PCT Analysis
python backfill_dmv_tvv_pct.py
# Processes ALL timestamps, appends to cp_backtest_h

# Step 3: OSC, MOM, RAT Analysis
python backfill_dmv_osc_mom_rat.py
# Requires step 2 to complete first

# Step 4: DMV Core Aggregation (MUST RUN LAST)
python backfill_dmv_core.py
# Aggregates all signals from steps 2-3
```

## Current Gap to Fill

**cp_backtest_h status:**
- Existing data: Feb 13, 2025 → Sept 10, 2025
- Missing data: Sept 10, 2025 → Oct 30, 2025
- Gap: ~50 days, ~1,200 hours

## Expected Results

After running all 3 backfill scripts:

**cp_backtest_h will have:**
- Continuous hourly data: Feb 13 → Oct 30, 2025
- All FE tables populated
- FE_DMV_ALL and FE_DMV_SCORES tables created (currently don't exist)

## Validation

After execution, run:
```bash
python ../quality_assurance/check_timestamp_gaps_corrected.py
```

Expected output:
- No gaps > 1.5 hours
- Continuous data Feb 13 → Oct 30
- All tables have matching date ranges

## Notes

- cp_ai data is temporary (gets overwritten by hourly pipeline)
- cp_backtest_h data is permanent (append-only)
- These backfill scripts should only be run once for the gap period
- After backfill, normal hourly pipeline resumes regular updates

---

**Created:** 2025-10-30
**Purpose:** One-time backfill of Sept 10 - Oct 30 gap
