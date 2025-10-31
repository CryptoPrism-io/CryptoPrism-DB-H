# ============================================
# CryptoPrism-DB-H: DMV Core Historical Backfill (Script 3b)
# ============================================
# Description: Aggregates all HISTORICAL signals from cp_backtest_h into DMV_ALL table
# Input Database: cp_backtest_h (reads ALL historical signal data)
# Input Tables: FE_OSCILLATORS_SIGNALS, FE_MOMENTUM_SIGNALS, FE_RATIOS_SIGNALS, FE_TVV_SIGNALS
# Output Tables: FE_DMV_ALL, FE_DMV_SCORES (appended to cp_backtest_h)
# Frequency: Run ONCE for historical backfill
# Key Difference from backfill_dmv_core.py: Reads from cp_backtest_h instead of cp_ai

import time
import pandas as pd
import numpy as np
import warnings
import logging
import os
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Configuration
warnings.filterwarnings('ignore')
start_time = time.time()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("app.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ============================================
# Environment Variables Loading
# ============================================
# Load .env file ONLY if running locally (not in GitHub Actions)
if not os.getenv("GITHUB_ACTIONS"):
    env_file = ".env"
    if os.path.exists(env_file):
        load_dotenv()
        logger.info("✅ .env file loaded successfully.")
    else:
        logger.error("❌ .env file is missing! Please create one using .env.example as template.")
else:
    logger.info("🔹 Running in GitHub Actions: Using GitHub Secrets.")

# Fetch credentials (Works for both local and GitHub Actions)
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "cp_ai")  # AI database (hourly data)
DB_NAME_BT = os.getenv("DB_NAME_BT", "cp_backtest_h")  # Backtest database (hourly)

# ============================================
# Diagnostic Logging: Environment Variable Status
# ============================================
logger.info("🔍 DIAGNOSTIC: Environment Variable Check")
logger.info(f"   GITHUB_ACTIONS = {os.getenv('GITHUB_ACTIONS', '[NOT SET]')}")
logger.info(f"   DB_HOST exists: {bool(DB_HOST)}")
logger.info(f"   DB_USER exists: {bool(DB_USER)}")
logger.info(f"   DB_PASSWORD exists: {bool(DB_PASSWORD)}")
logger.info(f"   DB_PORT exists: {bool(DB_PORT)}")
logger.info(f"   DB_HOST value: {DB_HOST if DB_HOST else '[EMPTY]'}")
logger.info(f"   DB_USER value: {DB_USER if DB_USER else '[EMPTY]'}")
logger.info(f"   DB_PORT value: {DB_PORT if DB_PORT else '[EMPTY]'}")
logger.info(f"   DB_NAME value: {DB_NAME}")
logger.info(f"   DB_NAME_BT value: {DB_NAME_BT}")

# Validate required environment variables
missing_vars = [var for var in ["DB_HOST", "DB_USER", "DB_PASSWORD"] if not globals()[var]]
if missing_vars:
    logger.error(f"❌ Missing environment variables: {', '.join(missing_vars)}")
    raise SystemExit("❌ Terminating: Missing required credentials.")

# Log configuration (DO NOT log DB_PASSWORD for security)
logger.info(f"✅ Database Configuration Loaded: DB_HOST={DB_HOST}, DB_PORT={DB_PORT}")

# ============================================
# Database Engine Creation
# ============================================
logger.info("🔌 Creating database connections...")

# Engine for AI database (cp_ai) - for signal aggregation
engine_cpai = create_engine(f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}')
logger.info(f"✅ Connected to {DB_NAME} database")

# Engine for backtest database (cp_backtest_h) - for historical hourly data
engine_backtest = create_engine(f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME_BT}')
logger.info(f"✅ Connected to {DB_NAME_BT} database")




# ============================================
# Data Loading: Signal Tables FROM BACKTEST DATABASE
# ============================================
logger.info("📊 Loading HISTORICAL signal tables from cp_backtest_h...")
logger.info("🔍 KEY: Reading from cp_backtest_h (not cp_ai) for historical backfill")

# List of table names to query
table_queries = {
    "ratios_bin": "SELECT * FROM \"FE_RATIOS_SIGNALS\"",
    "df_oscillator_bin": "SELECT * FROM \"FE_OSCILLATORS_SIGNALS\"",
    "df_momentum": "SELECT * FROM \"FE_MOMENTUM_SIGNALS\"",
    "tvv_signals": "SELECT * FROM \"FE_TVV_SIGNALS\""
}

# Dictionary to store the results
data_frames = {}

# @title CRITICAL: Read from cp_backtest_h (NOT cp_ai) for historical backfill
# Execute queries and load data into DataFrames FROM BACKTEST DATABASE
with engine_backtest.connect() as connection:  # CHANGED: engine_backtest instead of engine_cpai
    for df_name, query in table_queries.items():
        data_frames[df_name] = pd.read_sql_query(query, connection)
        logger.info(f"✅ Loaded {df_name}: {len(data_frames[df_name])} records")

# Extract each DataFrame by name for further processing
ratios_bin = data_frames["ratios_bin"]
df_oscillator_bin = data_frames["df_oscillator_bin"]
df_momentum = data_frames["df_momentum"]
tvv_signals = data_frames["tvv_signals"]








# DMV DATA PREPARATION
# List of DataFrames to join
dfs_to_join = [ratios_bin, df_oscillator_bin, df_momentum, tvv_signals]

# Perform the join, handling duplicate column names
DMV = dfs_to_join[0]
for df in dfs_to_join[1:]:
    # Get overlapping columns (keep slug and timestamp for merge)
    overlapping_cols = DMV.columns.intersection(df.columns).difference(['slug', 'timestamp'])
    # Drop overlapping columns from the right DataFrame (except 'slug' and 'timestamp')
    df = df.drop(overlapping_cols, axis=1)
    # CRITICAL FIX: Merge on BOTH slug AND timestamp to avoid cartesian product
    DMV = pd.merge(DMV, df, on=['slug', 'timestamp'], how='outer')

# Extract and sort columns in DMV by placing 'id', 'slug', 'name', and 'timestamp' first, followed by other columns in alphabetical order
first_four_cols = DMV[['id', 'slug', 'name', 'timestamp']]
remaining_cols = DMV.drop(['id', 'slug', 'name', 'timestamp'], axis=1)
remaining_cols_sorted = remaining_cols.sort_index(axis=1)
DMV_sorted = pd.concat([first_four_cols, remaining_cols_sorted], axis=1)


## bullish and bearish counts


df=DMV_sorted
# Create new columns 'bullish', 'bearish', and 'neutral' initialized to 0
df['bullish'] = 0
df['bearish'] = 0
df['neutral'] = 0

# Iterate through rows and columns (excluding first four columns: 'id', 'slug', 'name', 'timestamp')
for index, row in df.iloc[:, 4:].iterrows():  # Start from the 5th column (index 4)
    for col_name, value in row.items():
        if value == 1:
            df.loc[index, 'bullish'] += value
        elif value == -1:
            df.loc[index, 'bearish'] += value
        elif value == 0:
            df.loc[index, 'neutral'] += value
            
DMV_sorted=df


# ============================================
# DMV_ALL: Write to Database
# ============================================
logger.info(f"💾 Writing FE_DMV_ALL to {DB_NAME} database...")
DMV_sorted.to_sql('FE_DMV_ALL', con=engine_cpai, if_exists='replace', index=False)
logger.info(f"✅ FE_DMV_ALL uploaded successfully: {len(DMV_sorted)} records")

# Create specific DataFrames for Durability, Momentum, and Valuation
Durability = DMV_sorted[['slug'] + [col for col in DMV_sorted.columns if col.startswith('d_')]]
Momentum = DMV_sorted[['slug'] + [col for col in DMV_sorted.columns if col.startswith('m_')]]
Valuation = DMV_sorted[['slug'] + [col for col in DMV_sorted.columns if col.startswith('v_')]]

# Calculate Scores for Durability, Momentum, and Valuation
Durability['Durability_Score'] = (Durability.drop('slug', axis=1).sum(axis=1) / (Durability.shape[1] - 1)) * 100
Momentum['Momentum_Score'] = (Momentum.drop('slug', axis=1).sum(axis=1) / (Momentum.shape[1] - 1)) * 100
Valuation['Valuation_Score'] = (Valuation.drop('slug', axis=1).sum(axis=1) / (Valuation.shape[1] - 1)) * 100

# Create DMV Scores DataFrame with 'slug' and the calculated scores
dmv_scores = pd.DataFrame({
    'slug': Durability['slug'],
    'Durability_Score': Durability['Durability_Score'],
    'Momentum_Score': Momentum['Momentum_Score'],
    'Valuation_Score': Valuation['Valuation_Score']
})

# ============================================
# DMV_SCORES: Write to Database
# ============================================
logger.info(f"💾 Writing FE_DMV_SCORES to {DB_NAME} database...")
dmv_scores.to_sql('FE_DMV_SCORES', con=engine_cpai, if_exists='replace', index=False)
logger.info(f"✅ FE_DMV_SCORES uploaded successfully: {len(dmv_scores)} records")

# ============================================
# Backtest Database: Historical Data Storage
# ============================================
logger.info(f"💾 Writing historical data to {DB_NAME_BT} database...")

# Append aggregated data to backtest database for historical analysis
DMV_sorted.to_sql('FE_DMV_ALL', con=engine_backtest, if_exists='append', index=False)
logger.info(f"✅ FE_DMV_ALL appended to {DB_NAME_BT}")

dmv_scores.to_sql('FE_DMV_SCORES', con=engine_backtest, if_exists='append', index=False)
logger.info(f"✅ FE_DMV_SCORES appended to {DB_NAME_BT}")

# ============================================
# Cleanup & Summary
# ============================================
# Dispose database connections
engine_cpai.dispose()
engine_backtest.dispose()
logger.info("✅ Database connections closed")

# Calculate execution time
end_time = time.time()
elapsed_time_seconds = end_time - start_time
elapsed_time_minutes = elapsed_time_seconds / 60

logger.info(f"⏱️  Total execution time: {elapsed_time_minutes:.2f} minutes")
logger.info("✅ DMV Core Aggregation completed successfully!")

# Final summary
logger.info("📊 Summary:")
logger.info(f"   Total signals aggregated: {len(DMV_sorted)}")
logger.info(f"   Bullish signals average: {DMV_sorted['bullish'].mean():.2f}")
logger.info(f"   Bearish signals average: {DMV_sorted['bearish'].mean():.2f}")
logger.info(f"   Neutral signals average: {DMV_sorted['neutral'].mean():.2f}")


"""# end of script

"""
