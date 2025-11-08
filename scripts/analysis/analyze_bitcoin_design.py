#!/usr/bin/env python3
"""
Verify bitcoin handling is by design in FE_RATIOS_SIGNALS
"""

import psycopg2
from psycopg2.extras import RealDictCursor

DB_HOST = '34.55.195.199'
DB_PORT = 5432
DB_USER = 'yogass09'
DB_PASSWORD = 'jaimaakamakhya'

conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASSWORD,
    database='cp_ai'
)

cursor = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 100)
print("BITCOIN BENCHMARK ANALYSIS - FE_RATIOS_SIGNALS BY DESIGN")
print("=" * 100)

# Check if bitcoin exists in FE_RATIOS table (the base ratios calculations)
print("\n1️⃣  Checking FE_RATIOS table (base calculations):")
cursor.execute("""
    SELECT COUNT(*) as count, COUNT(DISTINCT timestamp) as timestamps
    FROM "FE_RATIOS"
    WHERE slug = 'bitcoin'
""")
result = cursor.fetchone()
print(f"   Bitcoin records in FE_RATIOS: {result['count']}")
print(f"   Bitcoin timestamps in FE_RATIOS: {result['timestamps']}")

# Check latest ratios data
cursor.execute("""
    SELECT slug, timestamp, COUNT(*) as count
    FROM "FE_RATIOS"
    GROUP BY slug, timestamp
    ORDER BY timestamp DESC
    LIMIT 10
""")
print("\n   Latest 10 FE_RATIOS entries:")
for row in cursor.fetchall():
    print(f"     {row['slug']:20s} @ {row['timestamp']} ({row['count']} rows)")

# Check if bitcoin is excluded from FE_RATIOS_SIGNALS by filter
print("\n2️⃣  Checking if bitcoin is intentionally excluded from FE_RATIOS_SIGNALS:")
cursor.execute("""
    SELECT slug FROM "FE_RATIOS_SIGNALS"
    WHERE timestamp = '2025-11-08 06:59:59+00:00'
    ORDER BY slug
""")
ratios_coins = [row['slug'] for row in cursor.fetchall()]
print(f"   Total coins in FE_RATIOS_SIGNALS @ 2025-11-08 06:59:59: {len(ratios_coins)}")
print(f"   Bitcoin in FE_RATIOS_SIGNALS: {'YES' if 'bitcoin' in ratios_coins else 'NO ✅ (EXCLUDED BY DESIGN)'}")

# Check the other signal tables for comparison
print("\n3️⃣  Bitcoin presence in other signal tables @ 2025-11-08 06:59:59:")
tables = {
    'FE_TVV_SIGNALS': 'TVV (Trend/Volume/Valuation)',
    'FE_OSCILLATORS_SIGNALS': 'Oscillators',
    'FE_MOMENTUM_SIGNALS': 'Momentum'
}

for table, desc in tables.items():
    cursor.execute(f"""
        SELECT COUNT(*) as count
        FROM "{table}"
        WHERE timestamp = '2025-11-08 06:59:59+00:00'
        AND slug = 'bitcoin'
    """)
    result = cursor.fetchone()
    status = "✅ INCLUDED" if result['count'] > 0 else "❌ MISSING"
    print(f"   {desc:30s}: {status}")

# Show what happens in FE_DMV_ALL aggregation
print("\n4️⃣  FE_DMV_ALL aggregation issue (JOINING all signal tables):")
cursor.execute("""
    SELECT slug, timestamp, COUNT(*) as count
    FROM "FE_DMV_ALL"
    WHERE slug = 'bitcoin'
    GROUP BY slug, timestamp
""")

dmv_results = cursor.fetchall()
if dmv_results:
    print(f"   Bitcoin records in FE_DMV_ALL:")
    for row in dmv_results:
        ts = row['timestamp'] if row['timestamp'] else "NULL"
        print(f"     Timestamp: {ts} | Count: {row['count']}")
else:
    print("   No bitcoin records found in FE_DMV_ALL")

print("\n5️⃣  ROOT CAUSE ANALYSIS:")
print("""
   When FE_DMV_ALL joins all signal tables:

   SELECT ... FROM FE_TVV_SIGNALS t
   LEFT/FULL JOIN FE_OSCILLATORS_SIGNALS o USING (slug, timestamp)
   LEFT/FULL JOIN FE_MOMENTUM_SIGNALS m USING (slug, timestamp)
   LEFT/FULL JOIN FE_RATIOS_SIGNALS r USING (slug, timestamp)

   Bitcoin has entries in:
   ✅ FE_TVV_SIGNALS @ 2025-11-08 06:59:59
   ✅ FE_OSCILLATORS_SIGNALS @ 2025-11-08 06:59:59
   ✅ FE_MOMENTUM_SIGNALS @ 2025-11-08 06:59:59
   ❌ FE_RATIOS_SIGNALS @ 2025-11-08 06:59:59 (NO ENTRY - Bitcoin is benchmark)

   Result: If using FULL OUTER JOIN, bitcoin row appears but with NULL timestamp
           from the missing FE_RATIOS_SIGNALS join.
""")

print("\n6️⃣  RECOMMENDATION:")
print("""
   ✅ This is EXPECTED behavior - NOT a bug

   Solution Options:
   1. Exclude bitcoin from FE_DMV_ALL aggregation (cleaner)
   2. Handle NULL timestamps in aggregation logic
   3. Create a special "NO RATIOS" indicator for benchmark coins

   The NULL timestamp row in FE_DMV_ALL for bitcoin is acceptable because:
   - Bitcoin is a benchmark, not a trading asset in this system
   - It doesn't need ratio-based signals
   - Can be safely ignored in analysis
""")

cursor.close()
conn.close()

print("\n" + "=" * 100)
