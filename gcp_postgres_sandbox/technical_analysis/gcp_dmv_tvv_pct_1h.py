# ============================================
# CryptoPrism-DB-H: TVV & PCT Analysis (Hourly)
# ============================================
# Description: Calculates Volume/Value analysis and Risk metrics on hourly data
# Input Tables: ohlcv_1h_250_coins (from cp_ai), crypto_listings_latest_1000 (from dbcp)
# Output Tables: FE_TVV, FE_TVV_SIGNALS, FE_PCT_CHANGE
# Frequency: Runs hourly via GitHub Actions

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

# Database names
DB_NAME_PROD = os.getenv("DB_NAME_PROD", "dbcp")  # Production database
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
logger.info(f"   DB_NAME_PROD value: {DB_NAME_PROD}")
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

# Engine for production database (dbcp) - for crypto_listings_latest_1000
engine_dbcp = create_engine(f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME_PROD}')
logger.info(f"✅ Connected to {DB_NAME_PROD} database")

# Engine for AI database (cp_ai) - for hourly OHLCV data
engine_cpai = create_engine(f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}')
logger.info(f"✅ Connected to {DB_NAME} database")

# Engine for backtest database (cp_backtest_h) - for historical hourly data
engine_backtest = create_engine(f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME_BT}')
logger.info(f"✅ Connected to {DB_NAME_BT} database")

# ============================================
# Data Loading
# ============================================
logger.info("📊 Loading cryptocurrency data...")

# Load crypto listings from production database
with engine_dbcp.connect() as connection:
    query = "SELECT * FROM crypto_listings_latest_1000"
    top_1000_cmc_rank = pd.read_sql_query(query, connection)
    logger.info(f"✅ Loaded {len(top_1000_cmc_rank)} listings from {DB_NAME_PROD}")

engine_dbcp.dispose()

# Load hourly OHLCV data from AI database
with engine_cpai.connect() as connection:
    query = 'SELECT * FROM "ohlcv_1h_250_coins"'
    all_coins_ohlcv_filtered = pd.read_sql_query(query, connection)
    logger.info(f"✅ Loaded {len(all_coins_ohlcv_filtered)} hourly OHLCV records from {DB_NAME}")

# Data validation
logger.info(f"   Total unique coins: {all_coins_ohlcv_filtered['slug'].nunique()}")
logger.info(f"   Date range: {all_coins_ohlcv_filtered['timestamp'].min()} to {all_coins_ohlcv_filtered['timestamp'].max()}")

# @title  Enhancing Function Definition Through Grouping and Indexing Techniques
df=all_coins_ohlcv_filtered
df.set_index('symbol', inplace=True)
# Ensure the timestamp column is in datetime format
df['timestamp'] = pd.to_datetime(df['timestamp'])

# Sort the DataFrame by 'slug' and 'timestamp' columns
df.sort_values(by=['slug', 'timestamp'], inplace=True)

# Perform time-series calculations within each group (each cryptocurrency)
grouped = df.groupby('slug')

"""# TVV"""

# @title  Enhancing Function Definition Through Grouping and Indexing Techniques
df=all_coins_ohlcv_filtered
# Ensure the timestamp column is in datetime format
df['timestamp'] = pd.to_datetime(df['timestamp'])

# Sort the DataFrame by 'slug' and 'timestamp' columns
df.sort_values(by=['slug', 'timestamp'], inplace=True)

# Perform time-series calculations within each group (each cryptocurrency)
grouped = df.groupby('slug')

#df = df.drop(df.columns[12:20], axis=1)

df.info()

# @title On-Balance Volume (OBV)

# Assuming df is your DataFrame and it is already sorted by 'slug' and 'timestamp'

def calculate_obv(group):
    # Initialize OBV list
    obv = [0]  # Start with zero for the first row
    for i in range(1, len(group)):
        if group['close'].iloc[i] > group['close'].iloc[i - 1]:
            obv.append(obv[-1] + group['volume'].iloc[i])
        elif group['close'].iloc[i] < group['close'].iloc[i - 1]:
            obv.append(obv[-1] - group['volume'].iloc[i])
        else:
            obv.append(obv[-1])
    return pd.Series(obv, index=group.index)

# Ensure the DataFrame has unique indices and reset if necessary
df = df.reset_index(drop=True)

# Group by 'slug' and apply OBV calculation
df['obv'] = df.groupby('slug').apply(calculate_obv).reset_index(level=0, drop=True)

# Recalculate the grouped DataFrame after adding the 'obv' column
grouped = df.groupby('slug')
df['m_tvv_obv_1d'] = grouped['obv'].pct_change()

df.tail()

df.describe()

# @title Moving Averages (SMA and EMA)

# Calculate the Simple Moving Average (SMA) for 9 and 18 periods
df['SMA9'] = grouped['close'].transform(lambda x: x.rolling(window=9).mean())
df['SMA18'] = grouped['close'].transform(lambda x: x.rolling(window=18).mean())

# Calculate the Exponential Moving Average (EMA) for 9 and 18 periods
df['EMA9'] = grouped['close'].transform(lambda x: x.ewm(span=9, adjust=False).mean())
df['EMA18'] = grouped['close'].transform(lambda x: x.ewm(span=18, adjust=False).mean())

# Calculate the Simple Moving Average (SMA) for 21 periods
df['SMA21'] = df.groupby('slug')['close'].transform(lambda x: x.rolling(window=21).mean())
df['SMA108'] = df.groupby('slug')['close'].transform(lambda x: x.rolling(window=108).mean())

# Calculate EMA (21-period)
df['EMA21'] = df.groupby('slug')['close'].transform(lambda x: x.ewm(span=21, adjust=False).mean())
# Calculate EMA (108-period)
df['EMA108'] = df.groupby('slug')['close'].transform(lambda x: x.ewm(span=108, adjust=False).mean())

df.info()

# @title Average True Range (ATR)
def calculate_atr(group, window=14):
    # Calculate True Range
    group['prev_close'] = group['close'].shift(1)
    group['tr1'] = group['high'] - group['low']
    group['tr2'] = abs(group['high'] - group['prev_close'])
    group['tr3'] = abs(group['low'] - group['prev_close'])
    group['TR'] = group[['tr1', 'tr2', 'tr3']].max(axis=1)

    # Calculate ATR
    group['ATR'] = group['TR'].rolling(window=window).mean()

    return group

# Apply the function to each cryptocurrency
df = df.groupby('slug').apply(calculate_atr).reset_index(level=0, drop=True)

df.info()

# @title Ketler and Donchain

def calculate_keltner_channels(group, window_ema=21, window_atr=14):
    # Calculate EMA
    group['EMA21'] = group['close'].ewm(span=window_ema, adjust=False).mean()

    # Calculate ATR
    group = calculate_atr(group, window=window_atr) # calculate_atr is now defined before being called

    # Calculate Keltner Channels
    group['Keltner_Upper'] = group['EMA21'] + (group['ATR'] * 1.5)
    group['Keltner_Lower'] = group['EMA21'] - (group['ATR'] * 1.5)

    return group

# Apply the function to each cryptocurrency
df = df.groupby('slug').apply(calculate_keltner_channels).reset_index(level=0, drop=True)

def calculate_donchian_channels(group, window=20):
    # Calculate Donchian Channels
    group['Donchian_Upper'] = group['high'].rolling(window=window).max()
    group['Donchian_Lower'] = group['low'].rolling(window=window).min()

    return group

# Reset the index before applying the function (if needed)
df = df.reset_index(drop=True) # drop=True to avoid old index being added as a column

# Apply the function to each cryptocurrency
df = df.groupby('slug').apply(calculate_donchian_channels).reset_index(level=0, drop=True)

df.info()

# @title Vwap / ADL / CMF
def calculate_vwap(group):
    # Calculate typical price for each period
    group['typical_price'] = (group['high'] + group['low'] + group['close']) / 3

    # Calculate the cumulative sum of typical price * volume
    group['cum_price_volume'] = (group['typical_price'] * group['volume']).cumsum()

    # Calculate the cumulative sum of volume
    group['cum_volume'] = group['volume'].cumsum()

    # Calculate VWAP
    group['VWAP'] = group['cum_price_volume'] / group['cum_volume']

    return group

# Reset the index before applying the function (if needed)
df = df.reset_index(drop=True) # drop=True to avoid old index being added as a column


# Group by 'slug' to calculate VWAP for each cryptocurrency
df = df.groupby('slug').apply(calculate_vwap).reset_index(level=0, drop=True)

import pandas as pd

# Correct ADL Calculation
df['ADL'] = ((df['close'] - df['low'] - (df['high'] - df['close'])) / (df['high'] - df['low'])) * df['volume']

def calculate_cmf(group, period):
    # Ensure 'slug' is not an index
    group = group.reset_index(drop=True)

    # Correct ADL Calculation
    group['ADL'] = ((group['close'] - group['low'] - (group['high'] - group['close'])) / (group['high'] - group['low'])) * group['volume']

    # Calculate cumulative ADL and volume
    group['cum_adl'] = group['ADL'].cumsum()
    group['cum_volume'] = group['volume'].cumsum()

    # Calculate CMF, handling potential division by zero
    epsilon = 1e-10  # Small constant to avoid division by zero
    group['CMF'] = group['cum_adl'].rolling(window=period).sum() / (group['cum_volume'].rolling(window=period).sum() + epsilon)

    return group

# Define the period for CMF calculation
period = 21

# Reset the index before applying the function (if needed)
df = df.reset_index(drop=True)  # drop=True to avoid old index being added as a column

# Group by 'slug' to calculate CMF for each cryptocurrency
df = df.groupby('slug').apply(calculate_cmf, period=period).reset_index(level=0, drop=True)

# prompt: create a new df called a ... take df and filter for only latest timestamp.. no need to group bby slug

# Get the latest timestamp
latest_timestamp = df['timestamp'].max()

# Filter the DataFrame for the latest timestamp
a = df[df['timestamp'] == latest_timestamp]

a.info()

# ============================================
# TVV Analysis: Data Preparation
# ============================================
logger.info("🔧 Preparing TVV analysis data...")

columns_to_drop = ['ref_cur_id', 'ref_cur_name', 'time_open',
                   'time_close', 'time_high', 'time_low']

# Drop the specified columns
df = df.drop(columns=columns_to_drop, errors='ignore')

tvv = df

# Keep only latest timestamp for each slug
tvv = tvv.loc[tvv['timestamp'].idxmax()]

logger.info(f"✅ TVV analysis prepared: {len(tvv)} records")

# Write FE_TVV to database
logger.info(f"💾 Writing FE_TVV to {DB_NAME} database...")
tvv.to_sql('FE_TVV', con=engine_cpai, if_exists='replace', index=False)
logger.info("✅ FE_TVV table uploaded successfully!")

# @title TVV Binary Signals
columns_to_drop = ['name', 'ref_cur_id', 'ref_cur_name', 'time_open',
                   'time_close', 'time_high', 'time_low', 'open', 'high', 'low',
                   'close', 'volume', 'market_cap']

# Drop the specified columns
df_bin = df.drop(columns=columns_to_drop, errors='ignore')

df_bin['m_tvv_obv_1d_binary'] = df_bin['m_tvv_obv_1d'].apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))

# prompt: SMA9, SMA18, EMA9, EMA18, SMA21, SMA108, EMA21, EMA108
# mujhe crossover calculate karne hai so 9 ka 18 ke sath and 21 ka 108 ke sath hoga jab 9 18 se jyada hai toh 1 jab 9 18 se kaam hai tab -1 same jab 21 jyada hai 108 se tab 1 and jab 21 kaam hai 108 se tab -1
# mera naming conventing hai d_tvv_sma...

# Calculate crossovers for SMA9 and SMA18
df_bin['d_tvv_sma9_18'] = (df_bin['SMA9'] > df_bin['SMA18']).astype(int) * 2 - 1

# Calculate crossovers for EMA9 and EMA18
df_bin['d_tvv_ema9_18'] = (df_bin['EMA9'] > df_bin['EMA18']).astype(int) * 2 - 1

# Calculate crossovers for SMA21 and SMA108
df_bin['d_tvv_sma21_108'] = (df_bin['SMA21'] > df_bin['SMA108']).astype(int) * 2 - 1

# Calculate crossovers for EMA21 and EMA108
df_bin['d_tvv_ema21_108'] = (df_bin['EMA21'] > df_bin['EMA108']).astype(int) * 2 - 1

# Assuming 'CMF' column exists in df_bin
threshold = 0  # Adjust this threshold as needed
# Derive bullish/bearish signals based on CMF crossing the threshold
df_bin['m_tvv_cmf'] = 0  # Initialize the new column with zeros
df_bin.loc[df_bin['CMF'] > threshold, 'm_tvv_cmf'] = 1  # Bullish signal
df_bin.loc[df_bin['CMF'] < threshold, 'm_tvv_cmf'] = -1 # Bearish signal

df_bin.info()

# ============================================
# TVV Binary Signals: Final Preparation
# ============================================
logger.info("🔧 Preparing TVV binary signals...")

columns_to_keep = ['m_tvv_cmf', 'id', 'timestamp', 'm_tvv_obv_1d_binary', 'd_tvv_sma9_18',
                   'd_tvv_ema9_18', 'd_tvv_sma21_108', 'd_tvv_ema21_108', 'slug']

df_bin = df_bin[columns_to_keep]

tvv_signals = df_bin

# Get the latest timestamp
latest_timestamp = df['timestamp'].max()

# Filter for latest timestamp
tvv_signals = tvv_signals[tvv_signals['timestamp'] == latest_timestamp]

# Replace infinite values with NaN
tvv_signals = tvv_signals.replace([np.inf, -np.inf], np.nan)

logger.info(f"✅ TVV signals prepared: {len(tvv_signals)} records")

# Write FE_TVV_SIGNALS to database
logger.info(f"💾 Writing FE_TVV_SIGNALS to {DB_NAME} database...")
tvv_signals.to_sql('FE_TVV_SIGNALS', con=engine_cpai, if_exists='replace', index=False)
logger.info("✅ FE_TVV_SIGNALS table uploaded successfully!")



"""# PCT_CHANGE"""

# @title  Enhancing Function Definition Through Grouping and Indexing Techniques

df=all_coins_ohlcv_filtered
# Ensure the timestamp column is in datetime format
df['timestamp'] = pd.to_datetime(df['timestamp'])

# Sort the DataFrame by 'slug' and 'timestamp' columns
df.sort_values(by=['slug', 'timestamp'], inplace=True)

# Perform time-series calculations within each group (each cryptocurrency)
grouped = df.groupby('slug')

df.info()

# @title  VaR & CVaR
import pandas as pd
# Calculate percentage change for each cryptocurrency
df['m_pct_1d'] = grouped['close'].pct_change()
# Calculate cumulative returns for each cryptocurrency
df['d_pct_cum_ret'] = (1 + df['m_pct_1d']).groupby(df['slug']).cumprod() - 1

# Define the confidence level, e.g., 95%
confidence_level = 0.95

# Calculate Historical VaR for each cryptocurrency
VaR_df = df.groupby('slug').apply(lambda x: x['m_pct_1d'].quantile(1 - confidence_level))
VaR_df = VaR_df.reset_index(name='d_pct_var')

# Calculate CVaR for each cryptocurrency
CVaR_df = df.groupby('slug').apply(lambda x: x['m_pct_1d'][x['m_pct_1d'] <= x['m_pct_1d'].quantile(1 - confidence_level)].mean())
CVaR_df = CVaR_df.reset_index(name='d_pct_cvar')

# Merge VaR and CVaR back into the original DataFrame
df = df.merge(VaR_df, on='slug', how='left')
df = df.merge(CVaR_df, on='slug', how='left')

df.info()

import pandas as pd
import numpy as np

# Assuming your DataFrame is named 'df'

# Ensure 'timestamp' is in datetime format and 'volume' is numeric
df['timestamp'] = pd.to_datetime(df['timestamp'])
df['volume'] = pd.to_numeric(df['volume'])

# Sort by 'timestamp' in ascending order
df.sort_values(by='timestamp', ascending=True, inplace=True)

# Calculate daily volume percentage (VolD%)
df['d_pct_vol_1d'] = df.groupby('slug')['volume'].pct_change()

"""
# Calculate the latest weekly volume percentage (VolW%)
def latest_weekly_vol_percentage(group):
    if len(group) < 7:
        return np.nan
    return (group['volume'].iloc[-1] - group['volume'].iloc[-7]) / group['volume'].iloc[-7] * 100

df['d_pct_vol_1w'] = df.groupby('slug').apply(latest_weekly_vol_percentage).reset_index(level=0, drop=True)

# Calculate the latest monthly volume percentage (VolM%)
def latest_monthly_vol_percentage(group):
    if len(group) < 30:
        return np.nan
    return (group['volume'].iloc[-1] - group['volume'].iloc[-30]) / group['volume'].iloc[-30] * 100

df['d_pct_vol_1m'] = df.groupby('slug').apply(latest_monthly_vol_percentage).reset_index(level=0, drop=True)
"""

df.info()

# @title Keeping Only Latest Date for Each Slug
# Group by 'slug' and get the row with the maximum timestamp
pct_change = df.loc[df.groupby('slug')['timestamp'].idxmax()]

pct_change.info()

import numpy as np
# Drop columns with infinite values
pct_change = pct_change.replace([np.inf, -np.inf], np.nan)

# Drop columns 4 to 10
pct_change = pct_change.drop(pct_change.columns[4:10], axis=1)



pct_change.info()

# ============================================
# PCT_CHANGE: Write to Database
# ============================================
logger.info(f"💾 Writing FE_PCT_CHANGE to {DB_NAME} database...")
pct_change.to_sql('FE_PCT_CHANGE', con=engine_cpai, if_exists='replace', index=False)
logger.info("✅ FE_PCT_CHANGE table uploaded successfully!")

# ============================================
# Backtest Database: Historical Data Storage
# ============================================
logger.info(f"💾 Writing historical data to {DB_NAME_BT} database...")

# Upsert data to backtest database for historical analysis (replace to avoid duplicate key errors)
tvv.to_sql('FE_TVV', con=engine_backtest, if_exists='replace', index=False)
logger.info(f"✅ FE_TVV written to {DB_NAME_BT}")

tvv_signals.to_sql('FE_TVV_SIGNALS', con=engine_backtest, if_exists='replace', index=False)
logger.info(f"✅ FE_TVV_SIGNALS written to {DB_NAME_BT}")

pct_change.to_sql('FE_PCT_CHANGE', con=engine_backtest, if_exists='replace', index=False)
logger.info(f"✅ FE_PCT_CHANGE written to {DB_NAME_BT}")

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
logger.info("✅ TVV & PCT Analysis completed successfully!")

# Final summary
logger.info("📊 Summary:")
logger.info(f"   TVV records: {len(tvv)}")
logger.info(f"   TVV signals: {len(tvv_signals)}")
logger.info(f"   PCT changes: {len(pct_change)}")

