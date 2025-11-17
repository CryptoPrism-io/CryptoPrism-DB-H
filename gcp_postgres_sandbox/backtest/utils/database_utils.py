"""
Database Utilities for Backtesting Framework
============================================

Helper functions for safe database operations, querying, and table management.
"""

import pandas as pd
import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

logger = logging.getLogger(__name__)


def safe_query(engine, query: str, params: Optional[Dict] = None) -> pd.DataFrame:
    """
    Execute SQL query safely and return DataFrame.

    Args:
        engine: SQLAlchemy engine
        query: SQL query string
        params: Query parameters (optional)

    Returns:
        pd.DataFrame with query results
    """
    try:
        if params:
            query_text = text(query)
            return pd.read_sql(query_text, engine, params=params)
        else:
            return pd.read_sql(query, engine)
    except Exception as e:
        logger.error(f"Query failed: {e}")
        logger.error(f"Query: {query}")
        raise


def execute_statement(engine, statement: str) -> bool:
    """
    Execute SQL statement (INSERT, UPDATE, DELETE, CREATE, etc).

    Args:
        engine: SQLAlchemy engine
        statement: SQL statement

    Returns:
        True if successful
    """
    try:
        with engine.connect() as conn:
            conn.execute(text(statement))
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Statement execution failed: {e}")
        logger.error(f"Statement: {statement}")
        raise


def create_table_if_not_exists(engine, table_name: str, ddl: str) -> bool:
    """
    Create table if it doesn't exist using provided DDL.

    Args:
        engine: SQLAlchemy engine
        table_name: Name of table
        ddl: CREATE TABLE statement (can include multiple statements separated by ;)

    Returns:
        True if successful
    """
    try:
        logger.info(f"Creating/verifying table: {table_name}")

        with engine.connect() as conn:
            for statement in ddl.split(';'):
                if statement.strip():
                    conn.execute(text(statement))
            conn.commit()

        logger.info(f"✓ Table {table_name} ready")
        return True
    except Exception as e:
        logger.error(f"Create table failed: {e}")
        raise


def table_exists(engine, table_name: str) -> bool:
    """
    Check if table exists in database.

    Args:
        engine: SQLAlchemy engine
        table_name: Table name

    Returns:
        True if table exists
    """
    try:
        query = f"""
        SELECT COUNT(*) as count
        FROM information_schema.tables
        WHERE table_name = '{table_name}'
        """
        result = safe_query(engine, query)
        return result.iloc[0]['count'] > 0
    except:
        return False


def get_record_count(engine, table_name: str) -> int:
    """Get row count for a table"""
    try:
        query = f"SELECT COUNT(*) as count FROM {table_name}"
        result = safe_query(engine, query)
        return result.iloc[0]['count']
    except:
        return 0


def truncate_table(engine, table_name: str) -> bool:
    """Delete all records from table (keeps structure)"""
    try:
        statement = f"TRUNCATE TABLE {table_name}"
        return execute_statement(engine, statement)
    except Exception as e:
        logger.error(f"Truncate failed: {e}")
        return False


def drop_table(engine, table_name: str, if_exists: bool = True) -> bool:
    """Drop table"""
    try:
        if if_exists:
            statement = f"DROP TABLE IF EXISTS {table_name}"
        else:
            statement = f"DROP TABLE {table_name}"
        return execute_statement(engine, statement)
    except Exception as e:
        logger.error(f"Drop table failed: {e}")
        return False
