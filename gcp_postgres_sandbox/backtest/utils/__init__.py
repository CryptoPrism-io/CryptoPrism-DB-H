"""
Backtesting utilities package
"""

from .database_utils import (
    safe_query,
    execute_statement,
    create_table_if_not_exists,
    table_exists,
    get_record_count,
    truncate_table,
    drop_table
)

# Import from parent utils module
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'utils'))

try:
    from db_connection import get_db_engines
except ImportError:
    # Fallback: create a simple version if db_connection is not available
    def get_db_engines():
        raise ImportError("db_connection module not found. Please check gcp_postgres_sandbox/utils/db_connection.py")

__all__ = [
    'safe_query',
    'execute_statement',
    'create_table_if_not_exists',
    'table_exists',
    'get_record_count',
    'truncate_table',
    'drop_table',
    'get_db_engines'
]
