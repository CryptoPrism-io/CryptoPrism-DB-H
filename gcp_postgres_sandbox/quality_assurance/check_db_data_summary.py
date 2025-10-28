# Quick check: Does cp_backtest_h have ANY data?

import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv
import os

load_dotenv()

db_host = os.getenv("DB_HOST")
db_name_bt = os.getenv("DB_NAME_BT", "cp_backtest_h")
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_port = os.getenv("DB_PORT", "5432")

engine = create_engine(
    f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name_bt}",
    pool_pre_ping=True
)

print(f"Checking database: {db_name_bt}\n")

tables = ["FE_TVV_SIGNALS", "FE_OSCILLATORS_SIGNALS", "FE_MOMENTUM_SIGNALS", "FE_RATIOS_SIGNALS"]

for table in tables:
    try:
        query = f"""
        SELECT
            COUNT(*) as total_records,
            MIN(timestamp) as oldest,
            MAX(timestamp) as newest,
            COUNT(DISTINCT slug) as unique_coins
        FROM "{table}"
        """
        df = pd.read_sql(query, con=engine)

        if not df.empty:
            row = df.iloc[0]
            print(f"{table}:")
            print(f"   Total Records: {row['total_records']:,}")
            print(f"   Oldest: {row['oldest']}")
            print(f"   Newest: {row['newest']}")
            print(f"   Unique Coins: {row['unique_coins']}")
            print()
    except Exception as e:
        print(f"{table}: ERROR - {e}\n")

engine.dispose()
