"""
============================================
CryptoPrism-DB-H: Database Connection Manager
============================================
Description: Enterprise-grade database connection pooling with SQLAlchemy
Purpose: Provides reusable, optimized database connections for all scripts
Features:
  - Connection pooling with health checks
  - Automatic connection recycling
  - Multi-database support (dbcp, cp_ai, cp_backtest_h)
  - Environment-based configuration
  - Singleton pattern for engine caching

Based on: CryptoPrism-DB-Utils best practices
Adapted for: CryptoPrism-DB-H hourly pipeline
============================================
"""

import os
import logging
from typing import Dict, Optional
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """
    Singleton database connection manager with connection pooling.

    Features:
    - Engine caching per database (reuse connections)
    - Connection pooling with configurable size
    - Health checks via pool_pre_ping
    - Automatic connection recycling
    - Multi-database support

    Usage:
        db_conn = DatabaseConnection()
        engine = db_conn.get_engine('ai')  # Returns cached engine

        # Use engine for queries
        df = pd.read_sql("SELECT * FROM table", con=engine)

        # Cleanup at end of script
        db_conn.close_all_connections()
    """

    _instance = None
    _engines: Dict[str, Engine] = {}

    def __new__(cls):
        """Singleton pattern - only one instance exists."""
        if cls._instance is None:
            cls._instance = super(DatabaseConnection, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize connection manager (only once)."""
        if self._initialized:
            return

        self._initialized = True
        self._load_config()
        logger.info("DatabaseConnection initialized")

    def _load_config(self):
        """Load database configuration from environment variables."""
        required_vars = ['DB_HOST', 'DB_USER', 'DB_PASSWORD']
        missing = [var for var in required_vars if not os.getenv(var)]

        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}"
            )

        self.db_host = os.getenv('DB_HOST')
        self.db_user = os.getenv('DB_USER')
        self.db_password = os.getenv('DB_PASSWORD')
        self.db_port = os.getenv('DB_PORT', '5432')

        # Database names
        self.db_name_prod = os.getenv('DB_NAME_PROD', 'dbcp')
        self.db_name_ai = os.getenv('DB_NAME', 'cp_ai')
        self.db_name_backtest = os.getenv('DB_NAME_BT', 'cp_backtest_h')

        logger.info(f"Database config loaded: {self.db_host}:{self.db_port}")

    def _create_engine(self, database_name: str, pool_size: int = 5) -> Engine:
        """
        Create a SQLAlchemy engine with optimized pooling.

        Args:
            database_name: Name of the PostgreSQL database
            pool_size: Max number of connections in pool (default: 5)

        Returns:
            SQLAlchemy Engine with connection pooling

        Connection Pool Configuration:
        - pool_size: Maximum connections in pool
        - max_overflow: Additional connections beyond pool_size
        - pool_recycle: Recycle connections after N seconds (prevents stale connections)
        - pool_pre_ping: Health check before using connection
        - echo: Set to True for SQL query logging (debug only)
        """
        connection_string = (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{database_name}"
        )

        engine = create_engine(
            connection_string,
            poolclass=QueuePool,
            pool_size=pool_size,          # Max connections in pool
            max_overflow=10,               # Extra connections beyond pool_size
            pool_recycle=3600,             # Recycle after 1 hour
            pool_pre_ping=True,            # Verify connection health
            echo=False,                    # Set True for SQL debug logging
            connect_args={
                'connect_timeout': 10,     # Connection timeout (seconds)
                'options': '-c statement_timeout=300000'  # Query timeout (5 min)
            }
        )

        logger.info(
            f"Created engine for {database_name} "
            f"(pool_size={pool_size}, pool_recycle=3600s)"
        )

        return engine

    def get_engine(self, database: str, pool_size: int = 5) -> Engine:
        """
        Get or create a cached SQLAlchemy engine.

        Args:
            database: Database alias ('prod', 'ai', 'backtest')
            pool_size: Connection pool size (default: 5)

        Returns:
            SQLAlchemy Engine (cached if already created)

        Examples:
            engine_prod = db_conn.get_engine('prod')      # dbcp
            engine_ai = db_conn.get_engine('ai')          # cp_ai
            engine_bt = db_conn.get_engine('backtest')    # cp_backtest_h
        """
        # Map alias to actual database name
        database_map = {
            'prod': self.db_name_prod,
            'ai': self.db_name_ai,
            'backtest': self.db_name_backtest
        }

        if database not in database_map:
            raise ValueError(
                f"Invalid database alias: {database}. "
                f"Valid options: {list(database_map.keys())}"
            )

        db_name = database_map[database]

        # Return cached engine if exists
        if db_name in self._engines:
            logger.debug(f"Reusing cached engine for {db_name}")
            return self._engines[db_name]

        # Create new engine and cache it
        engine = self._create_engine(db_name, pool_size)
        self._engines[db_name] = engine

        return engine

    def test_connection(self, database: str = 'ai') -> bool:
        """
        Test database connection.

        Args:
            database: Database alias to test (default: 'ai')

        Returns:
            True if connection successful, False otherwise
        """
        try:
            engine = self.get_engine(database)
            with engine.connect() as conn:
                result = conn.execute("SELECT 1")
                result.fetchone()
            logger.info(f"Connection test successful for {database}")
            return True
        except Exception as e:
            logger.error(f"Connection test failed for {database}: {e}")
            return False

    def close_connection(self, database: str):
        """
        Close and remove a specific database engine.

        Args:
            database: Database alias to close
        """
        database_map = {
            'prod': self.db_name_prod,
            'ai': self.db_name_ai,
            'backtest': self.db_name_backtest
        }

        db_name = database_map.get(database)
        if db_name and db_name in self._engines:
            self._engines[db_name].dispose()
            del self._engines[db_name]
            logger.info(f"Closed connection for {database}")

    def close_all_connections(self):
        """Close all database connections and clear cache."""
        for db_name, engine in self._engines.items():
            engine.dispose()
            logger.info(f"Closed connection for {db_name}")

        self._engines.clear()
        logger.info("All database connections closed")

    def get_pool_status(self, database: str) -> Dict:
        """
        Get connection pool status for monitoring.

        Args:
            database: Database alias

        Returns:
            Dictionary with pool statistics
        """
        database_map = {
            'prod': self.db_name_prod,
            'ai': self.db_name_ai,
            'backtest': self.db_name_backtest
        }

        db_name = database_map.get(database)
        if not db_name or db_name not in self._engines:
            return {'error': 'Engine not found'}

        engine = self._engines[db_name]
        pool = engine.pool

        return {
            'database': db_name,
            'pool_size': pool.size(),
            'checked_in': pool.checkedin(),
            'checked_out': pool.checkedout(),
            'overflow': pool.overflow(),
            'total_connections': pool.checkedin() + pool.checkedout()
        }


# ============================================
# CONVENIENCE FUNCTIONS
# ============================================

def get_db_engines():
    """
    Get all three database engines at once.

    Returns:
        Tuple of (engine_dbcp, engine_cpai, engine_backtest)

    Example:
        engine_dbcp, engine_cpai, engine_backtest = get_db_engines()
        df = pd.read_sql("SELECT * FROM table", con=engine_cpai)
    """
    db_conn = DatabaseConnection()

    engine_dbcp = db_conn.get_engine('prod')
    engine_cpai = db_conn.get_engine('ai')
    engine_backtest = db_conn.get_engine('backtest')

    return engine_dbcp, engine_cpai, engine_backtest


def cleanup_db_connections():
    """
    Cleanup function to close all connections.

    Usage:
        # At end of script
        cleanup_db_connections()
    """
    db_conn = DatabaseConnection()
    db_conn.close_all_connections()


# ============================================
# EXAMPLE USAGE
# ============================================

if __name__ == "__main__":
    """
    Example usage and testing.
    """
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    print("Testing DatabaseConnection...")

    # Test 1: Singleton pattern
    db1 = DatabaseConnection()
    db2 = DatabaseConnection()
    print(f"Singleton test: {db1 is db2}")  # Should be True

    # Test 2: Get engines
    try:
        engine_ai = db1.get_engine('ai')
        print(f"✅ Got engine for cp_ai: {engine_ai}")

        # Test 3: Connection test
        if db1.test_connection('ai'):
            print("✅ Connection test passed")

        # Test 4: Pool status
        status = db1.get_pool_status('ai')
        print(f"Pool status: {status}")

    except Exception as e:
        print(f"❌ Error: {e}")

    finally:
        # Cleanup
        db1.close_all_connections()
        print("✅ All connections closed")
