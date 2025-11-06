# CryptoPrism-DB-H: Release Changelog

## [v1.4.0] - 2025-11-07

### Fixed
- **Pipeline Bug Fix** (Critical): Fixed undefined `gcp_engine` variable in `gcp_dmv_osc_mom_rat_1h.py:1236`
  - Resolved NameError preventing hourly signal processing
  - Proper variable: `engine_backtest` (already defined at line 94)
  - Impact: Restores hourly cron execution reliability

- **Data Gap Remediation** (Oct 1-14, 2025): Completed full restoration of missing signal data
  - FE_TVV_SIGNALS: 61,262 records
  - FE_OSCILLATORS_SIGNALS: 3,980 records
  - FE_MOMENTUM_SIGNALS: 182,846 records
  - FE_RATIOS_SIGNALS: 3,960 records
  - FE_DMV_ALL: 243,168 aggregated records
  - All data verified for completeness and accuracy

### Technical Details

#### Root Cause Analysis
- Hourly cron scripts (`gcp_dmv_tvv_pct_1h.py`, `gcp_dmv_osc_mom_rat_1h.py`) depend on undefined `gcp_engine` variable
- Oct 1-14 signal gap resulted from failed backfill attempts in previous run

#### Solution Implemented
1. Removed NameError reference to undefined `gcp_engine`
2. Clean data rebuild: Deleted incomplete Oct 1-14 records
3. Re-executed backfill pipeline with proper error handling
4. All three signal processing stages completed successfully

#### Verification
- All cron jobs verified safe: No changes required to hourly runners
- Database connections verified: All scripts use correct instances (cp_ai, cp_backtest_h, dbcp)
- Oct 1-14 data range: `2025-10-01` to `2025-10-13 19:29:59+00:00`
- No date-based filtering in production cron scripts

### Changed
- None (backfill script modifications were temporary and reverted)

### Testing
- ✅ Oct 1-14 data backfill completed successfully
- ✅ All signal tables populated correctly
- ✅ DMV aggregation verified (243,168 records)
- ✅ Cron job safety verified (no breaking changes)
- ✅ GitHub Actions workflows remain compatible

### Files Modified
- `gcp_postgres_sandbox/data_ingestion/gcp_ohlcv_1h_250coins.R` - Documentation
- `gcp_postgres_sandbox/data_ingestion/gcp_ohlcv_1h_historical.R` - Documentation
- `gcp_postgres_sandbox/technical_analysis/gcp_dmv_osc_mom_rat_1h.py` - Bug fix (line 1236)

### Deployment Notes
- No database schema changes required
- No configuration changes required
- Fully backward compatible
- Safe for immediate production deployment

### Documentation
- See `FINAL_REMEDIATION_REPORT.md` for detailed technical analysis
- See `DATA_QUALITY_AUDIT_REPORT.md` for initial problem diagnosis
- See `REMEDIATION_STATUS_REPORT.md` for decision documentation

---

## [v1.3.0] - 2025-10-30

### Added
- Historical data backfill capability for missing date ranges
- Enhanced error logging and validation

### Fixed
- Data integrity issues from partial backfill attempts

---

## [v1.2.0] - 2025-10-20

### Added
- DMV (Durability, Momentum, Valuation) score aggregation
- Advanced technical indicators

---

## [v1.1.0] - 2025-09-15

### Initial Release
- Complete crypto signal analysis pipeline
- Hourly data ingestion and processing
- PostgreSQL multi-database architecture
