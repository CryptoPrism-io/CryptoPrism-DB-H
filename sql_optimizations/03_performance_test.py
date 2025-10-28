#!/usr/bin/env python3
"""
============================================
CryptoPrism-DB-H: Performance Testing
============================================
Description: Benchmark database performance before/after optimizations
Purpose: Measure query execution time improvements from indexes and primary keys
Execution: Run before and after applying optimizations to compare results

Features:
  - Tests 10 common query patterns
  - Measures execution time (milliseconds)
  - Calculates improvement percentages
  - Analyzes query plans (EXPLAIN ANALYZE)
  - Generates comparison report

Usage:
  # Before optimizations
  python sql_optimizations/03_performance_test.py --mode before

  # After optimizations
  python sql_optimizations/03_performance_test.py --mode after

  # Compare results
  python sql_optimizations/03_performance_test.py --mode compare

Safety:
  - Read-only queries (no data modification)
  - Uses EXPLAIN ANALYZE for query plans
  - Timeout protection (30s per query)

Based on: CryptoPrism-DB-Utils performance testing patterns
============================================
"""

import os
import sys
import time
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("performance_test.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================
# ENVIRONMENT SETUP
# ============================================

if not os.getenv("GITHUB_ACTIONS"):
    env_file = ".env"
    if os.path.exists(env_file):
        load_dotenv()
        logger.info("✅ .env file loaded successfully.")
    else:
        logger.error("❌ .env file not found!")
        sys.exit(1)
else:
    logger.info("🔹 Running in GitHub Actions: Using GitHub Secrets.")

# Database configuration
DB_HOST = os.getenv('DB_HOST')
DB_NAME = os.getenv('DB_NAME', 'cp_ai')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_PORT = os.getenv('DB_PORT', '5432')

# Results directory
RESULTS_DIR = Path(__file__).parent / "performance_results"
RESULTS_DIR.mkdir(exist_ok=True)

# ============================================
# TEST QUERIES
# ============================================

TEST_QUERIES = {
    "1. Coin Lookup (Latest)": """
        SELECT * FROM "FE_DMV_ALL"
        WHERE slug = 'bitcoin'
        ORDER BY timestamp DESC
        LIMIT 10;
    """,

    "2. Time Range Query": """
        SELECT *
        FROM "FE_DMV_ALL"
        WHERE timestamp >= NOW() - INTERVAL '24 hours'
        ORDER BY timestamp DESC;
    """,

    "3. Time Range with Grouping": """
        SELECT slug,
               AVG(durability_score) as avg_durability,
               AVG(momentum_score) as avg_momentum,
               COUNT(*) as data_points
        FROM "FE_DMV_SCORES"
        WHERE timestamp >= NOW() - INTERVAL '24 hours'
        GROUP BY slug
        ORDER BY avg_momentum DESC
        LIMIT 50;
    """,

    "4. JOIN Operation": """
        SELECT
            o.slug,
            o.close,
            d.durability_score,
            d.momentum_score
        FROM "ohlcv_1h_250_coins" o
        JOIN "FE_DMV_SCORES" d
            ON o.slug = d.slug
            AND o.timestamp = d.timestamp
        WHERE o.timestamp >= NOW() - INTERVAL '12 hours'
        LIMIT 100;
    """,

    "5. Signal Filtering": """
        SELECT *
        FROM "FE_DMV_ALL"
        WHERE tvv_signal = 1
          AND oscillator_signal = 1
          AND momentum_signal = 1
          AND ratio_signal = 1
          AND timestamp >= NOW() - INTERVAL '6 hours'
        ORDER BY timestamp DESC;
    """,

    "6. High Durability Coins": """
        SELECT slug, name, durability_score, timestamp
        FROM "FE_DMV_SCORES"
        WHERE durability_score >= 0.7
          AND timestamp >= NOW() - INTERVAL '24 hours'
        ORDER BY durability_score DESC
        LIMIT 20;
    """,

    "7. High Momentum Coins": """
        SELECT slug, name, momentum_score, timestamp
        FROM "FE_DMV_SCORES"
        WHERE momentum_score >= 0.7
          AND timestamp >= NOW() - INTERVAL '24 hours'
        ORDER BY momentum_score DESC
        LIMIT 20;
    """,

    "8. OHLCV Price Data": """
        SELECT slug, timestamp, open, high, low, close, volume
        FROM "ohlcv_1h_250_coins"
        WHERE slug IN ('bitcoin', 'ethereum', 'binancecoin', 'cardano', 'solana')
          AND timestamp >= NOW() - INTERVAL '48 hours'
        ORDER BY slug, timestamp DESC;
    """,

    "9. Recent Data Freshness": """
        SELECT slug, MAX(timestamp) as latest_update
        FROM "FE_DMV_ALL"
        GROUP BY slug
        ORDER BY latest_update DESC
        LIMIT 50;
    """,

    "10. Aggregated Signals": """
        SELECT
            slug,
            name,
            COUNT(*) as signal_count,
            SUM(CASE WHEN tvv_signal = 1 THEN 1 ELSE 0 END) as tvv_positives,
            SUM(CASE WHEN momentum_signal = 1 THEN 1 ELSE 0 END) as mom_positives,
            SUM(CASE WHEN oscillator_signal = 1 THEN 1 ELSE 0 END) as osc_positives
        FROM "FE_DMV_ALL"
        WHERE timestamp >= NOW() - INTERVAL '24 hours'
        GROUP BY slug, name
        HAVING COUNT(*) >= 10
        ORDER BY (SUM(CASE WHEN tvv_signal = 1 THEN 1 ELSE 0 END) +
                  SUM(CASE WHEN momentum_signal = 1 THEN 1 ELSE 0 END) +
                  SUM(CASE WHEN oscillator_signal = 1 THEN 1 ELSE 0 END)) DESC
        LIMIT 30;
    """
}

# ============================================
# DATABASE CONNECTION
# ============================================

def create_db_engine():
    """Create SQLAlchemy engine."""
    try:
        connection_string = (
            f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}'
            f'@{DB_HOST}:{DB_PORT}/{DB_NAME}'
        )

        engine = create_engine(
            connection_string,
            pool_pre_ping=True,
            connect_args={
                'connect_timeout': 10,
                'options': '-c statement_timeout=30000'  # 30s timeout
            }
        )

        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        logger.info("✅ Database connection successful")
        return engine

    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        sys.exit(1)


# ============================================
# PERFORMANCE TESTING
# ============================================

def run_query_benchmark(engine, query_name: str, query_sql: str, use_explain: bool = True):
    """
    Benchmark a single query.

    Args:
        engine: SQLAlchemy engine
        query_name: Human-readable query name
        query_sql: SQL query to test
        use_explain: Whether to use EXPLAIN ANALYZE

    Returns:
        Dictionary with timing and query plan info
    """
    result = {
        'query_name': query_name,
        'success': False,
        'execution_time_ms': None,
        'rows_returned': 0,
        'query_plan': None,
        'error': None
    }

    try:
        with engine.connect() as conn:
            # Measure actual execution time
            start_time = time.time()
            query_result = conn.execute(text(query_sql))
            rows = query_result.fetchall()
            execution_time = (time.time() - start_time) * 1000  # Convert to ms

            result['success'] = True
            result['execution_time_ms'] = round(execution_time, 2)
            result['rows_returned'] = len(rows)

            # Get query plan if requested
            if use_explain:
                explain_query = f"EXPLAIN ANALYZE {query_sql}"
                plan_result = conn.execute(text(explain_query))
                plan_lines = [row[0] for row in plan_result.fetchall()]
                result['query_plan'] = '\n'.join(plan_lines)

                # Extract planning and execution times from EXPLAIN ANALYZE
                for line in plan_lines:
                    if 'Planning Time:' in line:
                        result['planning_time_ms'] = float(line.split(':')[1].strip().split(' ')[0])
                    if 'Execution Time:' in line:
                        result['explain_execution_time_ms'] = float(line.split(':')[1].strip().split(' ')[0])

        logger.info(f"✅ {query_name}: {result['execution_time_ms']:.2f}ms ({result['rows_returned']} rows)")

    except Exception as e:
        result['error'] = str(e)
        logger.error(f"❌ {query_name}: {e}")

    return result


def run_full_benchmark(mode: str):
    """
    Run full benchmark suite.

    Args:
        mode: 'before' or 'after'
    """
    logger.info("=" * 70)
    logger.info(f"Performance Test: {mode.upper()} optimizations")
    logger.info("=" * 70)
    logger.info(f"Database: {DB_NAME}")
    logger.info(f"Host: {DB_HOST}:{DB_PORT}")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 70)

    engine = create_db_engine()
    results = []

    for idx, (query_name, query_sql) in enumerate(TEST_QUERIES.items(), 1):
        logger.info(f"\n[{idx}/{len(TEST_QUERIES)}] Testing: {query_name}")
        logger.info("-" * 70)

        result = run_query_benchmark(engine, query_name, query_sql, use_explain=True)
        results.append(result)

        # Add delay between queries to avoid overwhelming database
        time.sleep(0.5)

    engine.dispose()

    # Save results
    output_file = RESULTS_DIR / f"results_{mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump({
            'mode': mode,
            'timestamp': datetime.now().isoformat(),
            'database': DB_NAME,
            'results': results
        }, f, indent=2)

    logger.info("\n" + "=" * 70)
    logger.info(f"✅ Benchmark complete: {output_file}")
    logger.info("=" * 70)

    # Print summary
    print_summary(results)


def print_summary(results):
    """Print benchmark summary."""
    logger.info("\n📊 BENCHMARK SUMMARY")
    logger.info("=" * 70)

    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]

    logger.info(f"Total Queries: {len(results)}")
    logger.info(f"Successful: {len(successful)}")
    logger.info(f"Failed: {len(failed)}")

    if successful:
        times = [r['execution_time_ms'] for r in successful]
        logger.info(f"\nExecution Times:")
        logger.info(f"  Min: {min(times):.2f}ms")
        logger.info(f"  Max: {max(times):.2f}ms")
        logger.info(f"  Avg: {sum(times)/len(times):.2f}ms")
        logger.info(f"  Total: {sum(times):.2f}ms")

    logger.info("\nTop 5 Slowest Queries:")
    sorted_results = sorted(successful, key=lambda x: x['execution_time_ms'], reverse=True)
    for i, r in enumerate(sorted_results[:5], 1):
        logger.info(f"  {i}. {r['query_name']}: {r['execution_time_ms']:.2f}ms")


# ============================================
# COMPARISON
# ============================================

def compare_results():
    """Compare before/after results."""
    logger.info("=" * 70)
    logger.info("📊 PERFORMANCE COMPARISON")
    logger.info("=" * 70)

    # Find latest before and after files
    before_files = sorted(RESULTS_DIR.glob("results_before_*.json"))
    after_files = sorted(RESULTS_DIR.glob("results_after_*.json"))

    if not before_files or not after_files:
        logger.error("❌ Missing before or after results. Run benchmarks first.")
        return

    before_file = before_files[-1]
    after_file = after_files[-1]

    logger.info(f"Before: {before_file.name}")
    logger.info(f"After:  {after_file.name}")
    logger.info("=" * 70)

    # Load results
    with open(before_file) as f:
        before_data = json.load(f)

    with open(after_file) as f:
        after_data = json.load(f)

    # Compare
    print("\n{:<50} {:>12} {:>12} {:>15}".format(
        "Query", "Before (ms)", "After (ms)", "Improvement"
    ))
    print("-" * 95)

    total_before = 0
    total_after = 0

    for before_result in before_data['results']:
        if not before_result['success']:
            continue

        query_name = before_result['query_name']

        # Find matching after result
        after_result = next(
            (r for r in after_data['results'] if r['query_name'] == query_name),
            None
        )

        if not after_result or not after_result['success']:
            continue

        before_time = before_result['execution_time_ms']
        after_time = after_result['execution_time_ms']

        total_before += before_time
        total_after += after_time

        # Calculate improvement
        if before_time > 0:
            improvement_pct = ((before_time - after_time) / before_time) * 100
            improvement_factor = before_time / after_time
        else:
            improvement_pct = 0
            improvement_factor = 1

        print("{:<50} {:>12.2f} {:>12.2f} {:>10.1f}% ({:.1f}x)".format(
            query_name[:48],
            before_time,
            after_time,
            improvement_pct,
            improvement_factor
        ))

    # Total summary
    print("-" * 95)
    total_improvement = ((total_before - total_after) / total_before) * 100 if total_before > 0 else 0
    total_factor = total_before / total_after if total_after > 0 else 1

    print("{:<50} {:>12.2f} {:>12.2f} {:>10.1f}% ({:.1f}x)".format(
        "TOTAL",
        total_before,
        total_after,
        total_improvement,
        total_factor
    ))

    print("\n" + "=" * 70)
    print(f"🎉 Overall Performance Improvement: {total_improvement:.1f}% ({total_factor:.1f}x faster)")
    print("=" * 70)


# ============================================
# MAIN
# ============================================

def main():
    parser = argparse.ArgumentParser(description="Performance benchmark for database optimizations")
    parser.add_argument(
        '--mode',
        choices=['before', 'after', 'compare'],
        required=True,
        help='Test mode: before, after, or compare'
    )

    args = parser.parse_args()

    if args.mode == 'compare':
        compare_results()
    else:
        run_full_benchmark(args.mode)


if __name__ == "__main__":
    main()
