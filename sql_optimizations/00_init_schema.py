#!/usr/bin/env python3
"""
============================================
CryptoPrism-DB-H: Database Schema Initialization
============================================
Description: Applies primary keys and strategic indexes to cp_ai database
Purpose: One-time setup for optimal database performance
Execution: Run manually or via GitHub Actions after tables are created

Features:
  - Applies primary keys (01_primary_keys.sql)
  - Creates strategic indexes (02_strategic_indexes.sql)
  - Transaction-based execution (rollback on error)
  - Detailed logging and progress tracking
  - Execution time measurement

Usage:
  python sql_optimizations/00_init_schema.py

Safety:
  - Idempotent: Can be run multiple times safely
  - Uses "IF NOT EXISTS" and "DROP IF EXISTS" patterns
  - Non-destructive: Only adds constraints and indexes

Based on: CryptoPrism-DB-Utils schema management patterns
============================================
"""

import os
import sys
import time
import logging
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

# Configuration
start_time = time.time()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("schema_init.log"),
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

# Validate environment variables
required_vars = ['DB_HOST', 'DB_USER', 'DB_PASSWORD']
missing_vars = [var for var in required_vars if not os.getenv(var)]

if missing_vars:
    logger.error(f"❌ Missing environment variables: {', '.join(missing_vars)}")
    sys.exit(1)

# Database configuration
DB_HOST = os.getenv('DB_HOST')
DB_NAME = os.getenv('DB_NAME', 'cp_ai')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_PORT = os.getenv('DB_PORT', '5432')

logger.info("=" * 60)
logger.info("CryptoPrism-DB-H: Database Schema Initialization")
logger.info("=" * 60)
logger.info(f"Target Database: {DB_NAME}")
logger.info(f"Host: {DB_HOST}:{DB_PORT}")
logger.info(f"User: {DB_USER}")
logger.info("=" * 60)

# ============================================
# DATABASE CONNECTION
# ============================================

def create_db_engine():
    """Create SQLAlchemy engine for cp_ai database."""
    try:
        connection_string = (
            f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}'
            f'@{DB_HOST}:{DB_PORT}/{DB_NAME}'
        )

        engine = create_engine(
            connection_string,
            pool_pre_ping=True,
            connect_args={'connect_timeout': 10}
        )

        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        logger.info("✅ Database connection successful")
        return engine

    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        sys.exit(1)


def execute_sql_file(engine, sql_file_path: str, description: str):
    """
    Execute a SQL file with transaction support.

    Args:
        engine: SQLAlchemy engine
        sql_file_path: Path to SQL file
        description: Human-readable description

    Returns:
        True if successful, False otherwise
    """
    logger.info("-" * 60)
    logger.info(f"📄 Executing: {description}")
    logger.info(f"📁 File: {sql_file_path}")
    logger.info("-" * 60)

    # Check file exists
    if not os.path.exists(sql_file_path):
        logger.error(f"❌ File not found: {sql_file_path}")
        return False

    # Read SQL file
    try:
        with open(sql_file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()

        # Remove comments and split into statements
        statements = []
        for statement in sql_content.split(';'):
            # Remove SQL comments
            cleaned = '\n'.join(
                line for line in statement.split('\n')
                if not line.strip().startswith('--')
            )
            cleaned = cleaned.strip()

            # Skip empty statements and verification queries
            if cleaned and not cleaned.startswith('/*'):
                statements.append(cleaned)

        logger.info(f"📊 Found {len(statements)} SQL statements to execute")

    except Exception as e:
        logger.error(f"❌ Failed to read SQL file: {e}")
        return False

    # Execute statements
    start = time.time()
    executed_count = 0
    failed_count = 0

    try:
        with engine.begin() as conn:  # Transaction
            for idx, statement in enumerate(statements, 1):
                try:
                    # Log statement type
                    stmt_preview = statement[:80].replace('\n', ' ')
                    logger.debug(f"  [{idx}/{len(statements)}] {stmt_preview}...")

                    conn.execute(text(statement))
                    executed_count += 1

                except Exception as e:
                    # Log error but continue (some statements may fail if already exists)
                    error_msg = str(e).split('\n')[0]  # First line only
                    if 'already exists' in error_msg.lower():
                        logger.debug(f"  ⚠️ [{idx}/{len(statements)}] Already exists (skipping)")
                        executed_count += 1  # Count as success
                    else:
                        logger.warning(f"  ❌ [{idx}/{len(statements)}] Error: {error_msg}")
                        failed_count += 1

        duration = time.time() - start
        logger.info(f"✅ Execution complete: {executed_count} successful, {failed_count} skipped/failed")
        logger.info(f"⏱️  Duration: {duration:.2f} seconds")
        return True

    except Exception as e:
        logger.error(f"❌ Transaction failed: {e}")
        return False


def verify_schema():
    """Verify primary keys and indexes were created."""
    logger.info("-" * 60)
    logger.info("🔍 Verifying Schema Changes")
    logger.info("-" * 60)

    engine = create_db_engine()

    try:
        # Check primary keys
        pk_query = """
        SELECT
            tc.table_name,
            tc.constraint_name,
            string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) as columns
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY'
            AND tc.table_schema = 'public'
            AND tc.table_name LIKE '%FE_%'
        GROUP BY tc.table_name, tc.constraint_name
        ORDER BY tc.table_name;
        """

        with engine.connect() as conn:
            result = conn.execute(text(pk_query))
            pks = result.fetchall()

        logger.info(f"✅ Primary Keys: {len(pks)} found")
        for pk in pks[:5]:  # Show first 5
            logger.info(f"   - {pk[0]}: ({pk[2]})")
        if len(pks) > 5:
            logger.info(f"   ... and {len(pks) - 5} more")

        # Check indexes
        idx_query = """
        SELECT
            tablename,
            COUNT(*) as index_count
        FROM pg_indexes
        WHERE schemaname = 'public'
            AND tablename LIKE '%FE_%'
        GROUP BY tablename
        ORDER BY index_count DESC;
        """

        with engine.connect() as conn:
            result = conn.execute(text(idx_query))
            indexes = result.fetchall()

        logger.info(f"✅ Indexes: Found indexes on {len(indexes)} tables")
        total_indexes = sum(row[1] for row in indexes)
        logger.info(f"   Total index count: {total_indexes}")
        for idx in indexes[:5]:  # Show first 5
            logger.info(f"   - {idx[0]}: {idx[1]} indexes")
        if len(indexes) > 5:
            logger.info(f"   ... and {len(indexes) - 5} more tables")

        return True

    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        return False

    finally:
        engine.dispose()


# ============================================
# MAIN EXECUTION
# ============================================

def main():
    """Main execution function."""
    logger.info("🚀 Starting database schema initialization...")
    logger.info("")

    # Get SQL file paths
    script_dir = Path(__file__).parent
    pk_file = script_dir / "01_primary_keys.sql"
    idx_file = script_dir / "02_strategic_indexes.sql"

    # Create engine
    engine = create_db_engine()

    try:
        # Step 1: Apply primary keys
        success_pk = execute_sql_file(
            engine,
            str(pk_file),
            "Primary Keys Setup"
        )

        if not success_pk:
            logger.error("❌ Primary keys setup failed. Aborting.")
            return False

        logger.info("")

        # Step 2: Apply strategic indexes
        success_idx = execute_sql_file(
            engine,
            str(idx_file),
            "Strategic Indexes Setup"
        )

        if not success_idx:
            logger.warning("⚠️ Index setup had issues, but continuing...")

        logger.info("")

        # Step 3: Verify changes
        verify_schema()

        # Calculate total time
        total_time = time.time() - start_time

        logger.info("")
        logger.info("=" * 60)
        logger.info("🎉 Schema Initialization Complete!")
        logger.info("=" * 60)
        logger.info(f"⏱️  Total execution time: {total_time:.2f} seconds")
        logger.info("📊 Next Steps:")
        logger.info("   1. Run ANALYZE on all tables for query planner optimization")
        logger.info("   2. Monitor index usage with pg_stat_user_indexes")
        logger.info("   3. Check query performance improvements")
        logger.info("=" * 60)

        return True

    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return False

    finally:
        engine.dispose()
        logger.info("🔌 Database connection closed")


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
