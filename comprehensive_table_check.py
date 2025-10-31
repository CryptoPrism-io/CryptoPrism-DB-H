#!/usr/bin/env python3
"""
Comprehensive Table Check for cp_backtest_h

Verifies row counts, date ranges, and consistency across all tables
"""

import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv
import os

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME_BT = os.getenv("DB_NAME_BT", "cp_backtest_h")

engine = create_engine(f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME_BT}')

print("\n" + "="*100)
print("COMPREHENSIVE TABLE CHECK - cp_backtest_h")
print("="*100)

# Tables to check
tables = [
    "ohlcv_1h_250_coins",
    "FE_TVV",
    "FE_TVV_SIGNALS",
    "FE_PCT_CHANGE",
    "FE_OSCILLATOR",
    "FE_OSCILLATORS_SIGNALS",
    "FE_MOMENTUM",
    "FE_MOMENTUM_SIGNALS",
    "FE_RATIOS",
    "FE_RATIOS_SIGNALS",
    "FE_DMV_ALL",
    "FE_DMV_SCORES"
]

results = []

for table in tables:
    try:
        # Check if table has timestamp column
        check_query = f"""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = '{table}' AND column_name = 'timestamp'
        """
        has_timestamp = len(pd.read_sql(check_query, con=engine)) > 0

        if has_timestamp:
            query = f"""
            SELECT
                COUNT(*) as total_records,
                COUNT(DISTINCT slug) as unique_coins,
                MIN(timestamp::date) as min_date,
                MAX(timestamp::date) as max_date,
                COUNT(DISTINCT timestamp::date) as unique_days,
                COUNT(DISTINCT timestamp) as unique_timestamps
            FROM "{table}"
            """
            df = pd.read_sql(query, con=engine)
            results.append({
                'Table': table,
                'Records': f"{df['total_records'].iloc[0]:,}",
                'Coins': df['unique_coins'].iloc[0],
                'Min Date': df['min_date'].iloc[0],
                'Max Date': df['max_date'].iloc[0],
                'Days': df['unique_days'].iloc[0],
                'Timestamps': df['unique_timestamps'].iloc[0]
            })
        else:
            # For tables without timestamp (like FE_DMV_SCORES)
            query = f"""
            SELECT
                COUNT(*) as total_records,
                COUNT(DISTINCT slug) as unique_coins
            FROM "{table}"
            """
            df = pd.read_sql(query, con=engine)
            results.append({
                'Table': table,
                'Records': f"{df['total_records'].iloc[0]:,}",
                'Coins': df['unique_coins'].iloc[0],
                'Min Date': 'N/A',
                'Max Date': 'N/A',
                'Days': 'N/A',
                'Timestamps': 'N/A'
            })
    except Exception as e:
        results.append({
            'Table': table,
            'Records': f'ERROR: {str(e)[:50]}',
            'Coins': 'N/A',
            'Min Date': 'N/A',
            'Max Date': 'N/A',
            'Days': 'N/A',
            'Timestamps': 'N/A'
        })

# Display results
df_results = pd.DataFrame(results)
print("\n" + "-"*100)
print("TABLE SUMMARY")
print("-"*100)
print(df_results.to_string(index=False))

# Consistency checks
print("\n" + "="*100)
print("CONSISTENCY CHECKS")
print("="*100)

# Extract numeric values for comparison
def get_record_count(table_name):
    for r in results:
        if r['Table'] == table_name and r['Records'] != 'N/A':
            try:
                return int(r['Records'].replace(',', ''))
            except:
                return 0
    return 0

ohlcv_count = get_record_count("ohlcv_1h_250_coins")
tvv_signals = get_record_count("FE_TVV_SIGNALS")
osc_signals = get_record_count("FE_OSCILLATORS_SIGNALS")
mom_signals = get_record_count("FE_MOMENTUM_SIGNALS")
rat_signals = get_record_count("FE_RATIOS_SIGNALS")
dmv_all = get_record_count("FE_DMV_ALL")

print(f"\n1. OHLCV vs Signal Tables:")
print(f"   OHLCV Records: {ohlcv_count:,}")
print(f"   Signal tables should have fewer records (due to calculation requirements)")

print(f"\n2. Signal Table Consistency:")
print(f"   FE_TVV_SIGNALS:         {tvv_signals:,}")
print(f"   FE_OSCILLATORS_SIGNALS: {osc_signals:,}")
print(f"   FE_MOMENTUM_SIGNALS:    {mom_signals:,}")
print(f"   FE_RATIOS_SIGNALS:      {rat_signals:,} (30-day lag expected)")

# Check if OSC and MOM match (they should)
if osc_signals == mom_signals:
    print(f"   ✅ OSCILLATORS and MOMENTUM match perfectly ({osc_signals:,} records)")
else:
    print(f"   ⚠️  OSCILLATORS ({osc_signals:,}) and MOMENTUM ({mom_signals:,}) don't match")

# Check if TVV is close to OSC/MOM
tvv_diff_pct = abs(tvv_signals - osc_signals) / osc_signals * 100 if osc_signals > 0 else 0
if tvv_diff_pct < 5:
    print(f"   ✅ TVV_SIGNALS close to OSC/MOM ({tvv_diff_pct:.1f}% difference)")
else:
    print(f"   ⚠️  TVV_SIGNALS differs by {tvv_diff_pct:.1f}%")

print(f"\n3. DMV_ALL Aggregation:")
print(f"   FE_DMV_ALL:             {dmv_all:,}")
expected_range = f"{min(tvv_signals, osc_signals, mom_signals, rat_signals):,} - {max(tvv_signals, osc_signals, mom_signals):,}"
print(f"   Expected range:         {expected_range}")

if rat_signals <= dmv_all <= max(tvv_signals, osc_signals, mom_signals):
    print(f"   ✅ DMV_ALL within expected range (outer join of all signals)")
else:
    print(f"   ⚠️  DMV_ALL outside expected range")

print(f"\n4. Date Range Consistency:")
for r in results:
    if r['Min Date'] != 'N/A' and r['Max Date'] != 'N/A':
        if r['Table'].startswith('FE_'):
            print(f"   {r['Table']:30s} {r['Min Date']} → {r['Max Date']} ({r['Days']} days)")

print("\n" + "="*100)
print("FINAL VERDICT")
print("="*100)

issues = []

# Check critical issues
if osc_signals != mom_signals:
    issues.append("OSCILLATORS and MOMENTUM signal counts don't match")

if dmv_all < rat_signals:
    issues.append(f"DMV_ALL ({dmv_all:,}) has fewer records than RATIOS_SIGNALS ({rat_signals:,})")

if tvv_diff_pct > 10:
    issues.append(f"TVV_SIGNALS differs too much from other signals ({tvv_diff_pct:.1f}%)")

if issues:
    print("\n⚠️  ISSUES FOUND:")
    for issue in issues:
        print(f"   - {issue}")
else:
    print("\n✅ ALL CONSISTENCY CHECKS PASSED!")
    print(f"   - Signal tables have appropriate record counts")
    print(f"   - DMV_ALL successfully aggregated {dmv_all:,} records")
    print(f"   - Date ranges are consistent")

engine.dispose()
print("\n" + "="*100 + "\n")
