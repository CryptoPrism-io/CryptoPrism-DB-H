# CryptoPrism-DB-H: Backfill Action Plan

**Date:** 2025-10-28
**Status:** In Progress - Data Fetched, Processing Pending

---

## Problem Identified

### Database State (Before)
- **cp_ai**: Only 5 days of OHLCV data (Oct 23-28), FE tables had single timestamp (Sept 10)
- **cp_backtest_h**: Historical data up to Sept 10, 2025 (stale - 48 days old)
- **Gap**: Sept 10 → Oct 28 missing from cp_backtest_h

### Root Cause
- GitHub Actions secrets likely pointing to wrong database (`cp_backtest` instead of `cp_backtest_h`)
- Hourly pipeline stopped updating cp_backtest_h after Sept 10

---

## Solution Progress

### ✅ Phase 1: Data Fetching (COMPLETED)

**Script Created:** `gcp_ohlcv_1h_historical.R`

**Execution Results:**
```
✅ Fetched: 234,489 hourly OHLCV records
✅ Date Range: Sept 10 - Oct 28, 2025 (1,163 unique timestamps)
✅ Coins: 200 unique cryptocurrencies
✅ Database: cp_ai
✅ Total Records: 259,889 (added 234,489 to existing 25,400)
```

**File Location:** `gcp_postgres_sandbox/data_ingestion/gcp_ohlcv_1h_historical.R`

---

## Phase 2: Technical Analysis Processing (PENDING)

### Critical Issue Discovered

The existing technical analysis scripts have this logic:
```python
# Line 464-465 in gcp_dmv_tvv_pct_1h.py
pct_change = df.loc[df.groupby('slug')['timestamp'].idxmax()]
```

**Problem:** This keeps ONLY the latest timestamp per coin (correct for real-time mode, wrong for historical backfill)

**Solution Required:** Process ALL timestamps, not just latest

### Required Script Modifications

#### 1. gcp_dmv_tvv_pct_1h.py
**Modification:**
```python
# BEFORE (line 464-465):
pct_change = df.loc[df.groupby('slug')['timestamp'].idxmax()]

# AFTER (remove this line completely or comment out):
# pct_change = df.loc[df.groupby('slug')['timestamp'].idxmax()]
# Keep ALL rows instead of filtering to latest
pct_change = df.copy()
```

**Location:** `gcp_postgres_sandbox/technical_analysis/gcp_dmv_tvv_pct_1h.py`

#### 2. gcp_dmv_osc_mom_rat_1h.py
**Check for similar filtering logic** - likely around signal generation sections

**Location:** `gcp_postgres_sandbox/technical_analysis/gcp_dmv_osc_mom_rat_1h.py`

#### 3. gcp_dmv_core_1h.py
**Check aggregation logic** - ensure it processes all timestamps

**Location:** `gcp_postgres_sandbox/technical_analysis/gcp_dmv_core_1h.py`

---

## Execution Plan

### Step 1: Modify Scripts (Quick Approach)
```bash
# For each of the 3 scripts:
# 1. Find lines that filter to latest timestamp only
# 2. Comment out or remove those filters
# 3. Ensure ALL timestamps are processed
```

### Step 2: Run Processing Scripts (Sequential Order Required)
```bash
# IMPORTANT: Must run in this exact order

# Step 1: TVV & PCT Analysis
python gcp_postgres_sandbox/technical_analysis/gcp_dmv_tvv_pct_1h.py
# Expected: Processes all 1,163 timestamps, writes to cp_backtest_h (append mode)

# Step 2: OSC, MOM, RAT Analysis
python gcp_postgres_sandbox/technical_analysis/gcp_dmv_osc_mom_rat_1h.py
# Expected: Processes all 1,163 timestamps, writes to cp_backtest_h (append mode)

# Step 3: DMV Core Aggregation (MUST RUN LAST)
python gcp_postgres_sandbox/technical_analysis/gcp_dmv_core_1h.py
# Expected: Aggregates signals, writes FE_DMV_ALL and FE_DMV_SCORES
```

### Step 3: Validation
```bash
# Run gap checker on cp_backtest_h
python gcp_postgres_sandbox/quality_assurance/check_timestamp_gaps_corrected.py

# Expected Result:
# - No gaps > 1.5 hours
# - Data range: Feb 13, 2025 → Oct 28, 2025
# - Continuous hourly data
```

---

## Alternative: Create Historical Versions

If modifying existing scripts is risky, create new historical versions:

### Files to Create:
1. `gcp_dmv_tvv_pct_1h_historical.py` (copy + modify)
2. `gcp_dmv_osc_mom_rat_1h_historical.py` (copy + modify)
3. `gcp_dmv_core_1h_historical.py` (copy + modify)

**Modifications:**
- Remove timestamp filtering (keep all timestamps)
- Ensure append mode to cp_backtest_h
- Add logging for date range being processed

---

## Post-Processing Tasks

### Fix GitHub Actions
1. Go to: Repository → Settings → Environments → production
2. Verify `DB_NAME_BT` secret is set to `cp_backtest_h` (not `cp_backtest`)
3. Test next automated hourly run

### Resume Normal Operations
1. Monitor GitHub Actions hourly runs
2. Verify data continues to flow to cp_backtest_h
3. Check logs for any failures

---

## Files Created During This Session

### Scripts Created:
1. ✅ `gcp_ohlcv_1h_historical.R` - Historical data fetcher
2. ✅ `audit_cp_ai_timestamps.py` - Data availability auditor
3. ✅ `check_timestamp_gaps_corrected.py` - Gap validator (corrected for :59:59 pattern)
4. ✅ `check_recent_30days_integrity.py` - Recent data checker
5. ✅ `check_db_data_summary.py` - Quick database summary
6. ✅ `.env` - Fixed DB_NAME_BT to cp_backtest_h

### Documentation:
1. ✅ This file: `ACTION_PLAN_BACKFILL.md`

---

## Key Insights

### Data Pattern Discovery
- **Timestamps:** Data arrives at :59:59 of each hour (not :00:00)
- **Pattern:** 00:59:59, 01:59:59, 02:59:59... (end of hour, not beginning)
- **Implication:** Gap detection scripts must account for this pattern

### Database Architecture
- **cp_ai:** "Current mode" - keeps ~5 days rolling window, overwrites FE tables
- **cp_backtest_h:** "Historical mode" - append-only, accumulates all data
- **cp_backtest:** Wrong database - had recent data but shouldn't be used

---

## Success Criteria

✅ **Completed:**
- [x] Historical OHLCV data fetched (Sept 10 - Oct 28)
- [x] Data loaded into cp_ai (259,889 records total)
- [x] Audit confirms data availability

⏳ **Pending:**
- [ ] Technical analysis scripts modified/run
- [ ] cp_backtest_h populated with Sept 10 - Oct 28 signals
- [ ] Validation confirms no gaps
- [ ] GitHub Actions secrets corrected
- [ ] Normal hourly operations resumed

---

## Estimated Time Remaining

**Modifications:** 15-30 minutes
**Script Execution:** 10-20 minutes (depends on volume)
**Validation:** 5 minutes
**Total:** ~30-55 minutes

---

## Contact & References

**Repository:** CryptoPrism-DB-H
**Database:** GCP PostgreSQL (34.55.195.199)
**Affected Databases:** cp_ai, cp_backtest_h
**Date Range:** Sept 10, 2025 → Oct 28, 2025 (49 days, 1,163 hours)

---

**Last Updated:** 2025-10-28 16:25 UTC
**Status:** Ready for Phase 2 execution
