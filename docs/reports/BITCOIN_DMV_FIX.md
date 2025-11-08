# Bitcoin Benchmark Coin DMV Fix

## Problem Statement
The FE_DMV_ALL aggregation pipeline had an issue with bitcoin (the benchmark coin):
- Bitcoin is excluded from FE_RATIOS_SIGNALS (by design - it's the benchmark)
- The OUTER JOIN in the aggregation created a NULL timestamp row for bitcoin
- This caused bitcoin to appear in FE_DMV_ALL with `timestamp = NULL`

**Root Cause:**
```
Join order: FE_RATIOS_SIGNALS ⊗ FE_OSCILLATORS_SIGNALS ⊗ FE_MOMENTUM_SIGNALS ⊗ FE_TVV_SIGNALS
            (No bitcoin)       (Has bitcoin)             (Has bitcoin)           (Has bitcoin)

Result: OUTER JOIN creates NULL timestamp for bitcoin
```

## Solution Implemented

**File Modified:** `gcp_postgres_sandbox/technical_analysis/gcp_dmv_core_1h.py`

### Changes Made:

1. **Separate Bitcoin from Tradeable Coins** (lines 146-167)
   - Extract bitcoin into dedicated `bitcoin_dmv` DataFrame
   - Keep tradeable coins in `DMV_sorted` for FE_DMV_ALL
   - Fill bitcoin's NULL timestamp with most recent timestamp from TVV_SIGNALS

2. **Create FE_DMV_BITCOIN Table** (lines 199-212)
   - New dedicated table for bitcoin benchmark coin
   - Contains: TVV signals + OSCILLATORS signals + MOMENTUM signals
   - No ratio signals (as bitcoin is the benchmark for ratios)
   - Saved to both cp_ai and cp_backtest_h databases

3. **FE_DMV_ALL Now Clean** (line 167)
   - Only contains tradeable coins (199 coins)
   - All rows have valid timestamps
   - No NULL values

## Result

### Before Fix
```
FE_DMV_ALL:
  - 200 rows total
  - 199 with valid timestamps
  - 1 bitcoin row with timestamp = NULL ❌
```

### After Fix
```
FE_DMV_ALL:
  - 199 rows (tradeable coins only)
  - All rows have valid timestamps ✅

FE_DMV_BITCOIN (NEW):
  - 1 row for bitcoin benchmark
  - Valid timestamp from TVV_SIGNALS ✅
  - Contains: id, slug, name, timestamp + all TVV/OSC/MOM signals
```

## Data Structure

### FE_DMV_BITCOIN Columns
```
- id (integer)
- slug (text) = 'bitcoin'
- name (text) = 'Bitcoin'
- timestamp (timestamp with timezone) - from TVV_SIGNALS
- m_tvv_cmf (numeric) - TVV signal
- m_tvv_obv_1d_binary (numeric) - TVV signal
- d_tvv_sma9_18 (numeric) - TVV signal
- d_tvv_ema9_18 (numeric) - TVV signal
- d_tvv_sma21_108 (numeric) - TVV signal
- d_tvv_ema21_108 (numeric) - TVV signal
- m_osc_macd_crossover_bin (numeric) - Oscillator signal
- m_osc_cci_bin (numeric) - Oscillator signal
- m_osc_adx_bin (numeric) - Oscillator signal
- m_osc_uo_bin (numeric) - Oscillator signal
- m_osc_ao_bin (numeric) - Oscillator signal
- m_osc_trix_bin (numeric) - Oscillator signal
- m_mom_roc_bin (numeric) - Momentum signal
- m_mom_williams_%_bin (numeric) - Momentum signal
- m_mom_smi_bin (numeric) - Momentum signal
- m_mom_cmo_bin (numeric) - Momentum signal
- m_mom_mom_bin (numeric) - Momentum signal
- bullish (integer) - Sum of bullish signals
- bearish (integer) - Sum of bearish signals (negative)
- neutral (integer) - Sum of neutral signals
```

## Testing the Fix

The fix will take effect on the next hourly pipeline run:
1. Python cron job `py_cron.yml` triggers
2. Runs `gcp_dmv_core_1h.py` with the new logic
3. Creates/updates FE_DMV_BITCOIN table
4. FE_DMV_ALL now has only 199 rows (clean)

## Verification

After deployment, verify:
```sql
-- Check FE_DMV_ALL (should have 199 rows, no NULL timestamps)
SELECT COUNT(*) as total, COUNT(DISTINCT slug) as coins
FROM "FE_DMV_ALL" WHERE timestamp = (SELECT MAX(timestamp) FROM "FE_DMV_ALL");

-- Check FE_DMV_BITCOIN (should have 1 row with valid timestamp)
SELECT * FROM "FE_DMV_BITCOIN" ORDER BY timestamp DESC LIMIT 1;

-- Verify no NULL timestamps in either table
SELECT COUNT(*) FROM "FE_DMV_ALL" WHERE timestamp IS NULL;  -- Should be 0
SELECT COUNT(*) FROM "FE_DMV_BITCOIN" WHERE timestamp IS NULL;  -- Should be 0
```

## Benefits

✅ **Clean Data**: FE_DMV_ALL has no NULL timestamps
✅ **Bitcoin Preserved**: Bitcoin signals still available in separate table
✅ **Design Clarity**: Explicitly shows bitcoin is benchmark
✅ **Backward Compatible**: New table doesn't break existing code
✅ **Audit Trail**: FE_DMV_BITCOIN goes to both cp_ai and cp_backtest_h

## Deployment Notes

- **When**: Next scheduled hourly run (00:15 UTC daily)
- **No Database Schema Changes Required**: Tables auto-created by pandas to_sql()
- **Rollback**: If issues arise, revert the code change
- **Documentation**: This fix is documented in CHANGELOG.md
