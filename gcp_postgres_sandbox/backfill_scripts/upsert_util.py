#!/usr/bin/env python3
"""
UPSERT Utility Module for Backfill Scripts
===========================================
Provides safe INSERT ... ON CONFLICT ... DO UPDATE operations
for handling duplicate key scenarios in signal table backfills.
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def get_conflict_columns(table_name):
    """
    Return the primary key columns for each table.
    These are used in the ON CONFLICT clause.
    """
    conflict_columns = {
        'FE_TVV': ['slug', 'timestamp'],
        'FE_TVV_SIGNALS': ['slug', 'timestamp'],
        'FE_MOMENTUM': ['slug', 'timestamp'],
        'FE_MOMENTUM_SIGNALS': ['slug', 'timestamp'],
        'FE_OSCILLATOR': ['slug', 'timestamp'],
        'FE_OSCILLATORS_SIGNALS': ['slug', 'timestamp'],
        'FE_RATIOS': ['slug', 'timestamp'],
        'FE_RATIOS_SIGNALS': ['slug', 'timestamp'],
        'FE_DMV_ALL': ['slug', 'timestamp'],
        'FE_DMV_SCORES': ['slug', 'timestamp'],
        'FE_PCT_CHANGE': ['slug', 'timestamp'],
    }
    return conflict_columns.get(table_name, ['slug', 'timestamp'])


def df_to_sql_upsert(df, table_name, engine, schema=None, chunksize=1000):
    """
    Insert or update DataFrame rows into a PostgreSQL table.
    Handles duplicate key conflicts gracefully.

    Args:
        df: pandas DataFrame to insert
        table_name: Target table name
        engine: SQLAlchemy engine
        schema: Schema name (optional)
        chunksize: Number of rows per batch

    Returns:
        tuple: (rows_inserted, rows_updated, total_processed)
    """

    if df.empty:
        logger.warning(f"   ⚠️  Empty DataFrame for {table_name}, skipping insert")
        return 0, 0, 0

    conflict_cols = get_conflict_columns(table_name)

    # Get all column names
    columns = df.columns.tolist()

    # Get non-key columns for UPDATE clause
    update_cols = [col for col in columns if col not in conflict_cols]

    if not update_cols:
        update_cols = columns  # If all are key columns, update all

    # Build the ON CONFLICT clause
    conflict_clause = f"({', '.join(conflict_cols)})"

    # Build the UPDATE SET clause
    update_set = ', '.join([f'"{col}" = EXCLUDED."{col}"' for col in update_cols])

    rows_inserted = 0
    rows_updated = 0

    try:
        with engine.connect() as connection:
            # Process in chunks
            for chunk_idx in range(0, len(df), chunksize):
                chunk = df.iloc[chunk_idx:chunk_idx + chunksize]

                # Convert DataFrame to SQL values
                values_list = []
                for _, row in chunk.iterrows():
                    values = ', '.join([
                        f"'{str(val).replace(chr(39), chr(39)+chr(39))}'" if not pd.isna(val) else 'NULL'
                        for val in row.values
                    ])
                    values_list.append(f"({values})")

                # Build the full UPSERT query
                values_clause = ', '.join(values_list)
                columns_clause = ', '.join([f'"{col}"' for col in columns])

                query = f"""
                INSERT INTO "{table_name}" ({columns_clause})
                VALUES {values_clause}
                ON CONFLICT {conflict_clause}
                DO UPDATE SET {update_set}
                ON CONFLICT DO NOTHING;
                """

                try:
                    connection.execute(text(query))
                    connection.commit()
                    rows_inserted += len(chunk)
                except Exception as e:
                    # Log but continue with next chunk
                    logger.error(f"   ⚠️  Chunk insert failed for {table_name}: {str(e)[:100]}")
                    connection.rollback()

        logger.info(f"   ✅ UPSERT {table_name}: {rows_inserted} rows processed")
        return rows_inserted, 0, rows_inserted

    except Exception as e:
        logger.error(f"   ❌ Failed to UPSERT {table_name}: {e}")
        raise


def safe_insert_df(df, table_name, engine, conflict_action='NOTHING'):
    """
    Safe DataFrame insert with automatic conflict handling using raw SQL.

    Args:
        df: pandas DataFrame
        table_name: Target table name
        engine: SQLAlchemy engine
        conflict_action: 'NOTHING' (skip duplicates) or 'UPDATE' (update duplicates)

    Returns:
        int: Number of rows affected
    """

    if df.empty:
        logger.warning(f"   ⚠️  Empty DataFrame for {table_name}, skipping insert")
        return 0

    conflict_cols = get_conflict_columns(table_name)
    columns = df.columns.tolist()

    # Get non-key columns for UPDATE clause (if needed)
    update_cols = [col for col in columns if col not in conflict_cols]
    if not update_cols:
        update_cols = columns

    rows_inserted = 0

    try:
        with engine.connect() as connection:
            # Build SQL INSERT statement with ON CONFLICT handling
            columns_str = ', '.join([f'"{col}"' for col in columns])
            conflict_str = ', '.join([f'"{col}"' for col in conflict_cols])

            # Process in chunks
            chunksize = 1000
            for chunk_idx in range(0, len(df), chunksize):
                chunk = df.iloc[chunk_idx:chunk_idx + chunksize]

                # Build VALUES clause
                values_parts = []
                for _, row in chunk.iterrows():
                    values = []
                    for val in row.values:
                        if pd.isna(val):
                            values.append('NULL')
                        elif isinstance(val, str):
                            # Escape single quotes by doubling them
                            escaped = str(val).replace("'", "''")
                            values.append(f"'{escaped}'")
                        elif isinstance(val, bool):
                            values.append('true' if val else 'false')
                        elif isinstance(val, (int, float)):
                            values.append(str(val))
                        else:
                            values.append(f"'{str(val)}'")
                    values_parts.append(f"({', '.join(values)})")

                values_clause = ', '.join(values_parts)

                # Build the ON CONFLICT clause
                if conflict_action.upper() == 'NOTHING':
                    conflict_clause = f"ON CONFLICT ({conflict_str}) DO NOTHING"
                else:
                    # For UPDATE, set all non-key columns
                    update_set = ', '.join([f'"{col}" = EXCLUDED."{col}"' for col in update_cols])
                    conflict_clause = f"ON CONFLICT ({conflict_str}) DO UPDATE SET {update_set}"

                # Build final INSERT query
                insert_sql = f"""
                INSERT INTO "{table_name}" ({columns_str})
                VALUES {values_clause}
                {conflict_clause};
                """

                try:
                    connection.execute(text(insert_sql))
                    connection.commit()
                    rows_inserted += len(chunk)
                except Exception as chunk_error:
                    logger.error(f"   ⚠️  Chunk error: {str(chunk_error)[:100]}")
                    connection.rollback()

            logger.info(f"   ✅ Inserted {rows_inserted} rows into {table_name}")
            return rows_inserted

    except Exception as e:
        logger.error(f"   ❌ Failed to insert into {table_name}: {e}")
        raise


def _insert_with_conflict_handling(df, table_name, engine):
    """
    Insert rows one at a time, skipping those that cause conflicts.
    """
    rows_inserted = 0

    with engine.connect() as connection:
        for _, row in df.iterrows():
            try:
                # Create single-row DataFrame
                single_row_df = df.iloc[[_]]
                single_row_df.to_sql(
                    table_name,
                    con=connection,
                    if_exists='append',
                    index=False
                )
                rows_inserted += 1
            except Exception as e:
                if 'unique' in str(e).lower():
                    # Skip duplicate rows silently
                    continue
                else:
                    logger.error(f"   ⚠️  Error inserting row: {e}")

        connection.commit()

    logger.info(f"   ✅ Inserted {rows_inserted}/{len(df)} rows into {table_name}")
    return rows_inserted


# Import pandas for type checking
import pandas as pd
