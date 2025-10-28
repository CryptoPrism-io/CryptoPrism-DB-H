#ENTRY AND EXIT 

import pandas as pd

# Example: Financial time series data
data = pd.DataFrame({
    'Date': ['2024-12-16', '2024-12-17', '2024-12-18'],
    'High': [150.0, 155.0, 152.0],
    'Low': [145.0, 149.0, 148.0],
    'Close': [148.0, 153.0, 150.0]
})

# Convert Date column to datetime format
data['Date'] = pd.to_datetime(data['Date'])

# Function to calculate pivot points with S3 and R3
def calculate_pivots(df):
    df['Pivot'] = (df['High'] + df['Low'] + df['Close']) / 3
    df['R1'] = 2 * df['Pivot'] - df['Low']
    df['S1'] = 2 * df['Pivot'] - df['High']
    df['R2'] = df['Pivot'] + (df['High'] - df['Low'])
    df['S2'] = df['Pivot'] - (df['High'] - df['Low'])
    df['R3'] = df['High'] + 2 * (df['Pivot'] - df['Low'])
    df['S3'] = df['Low'] - 2 * (df['High'] - df['Pivot'])
    return df

# Apply the function to the dataset
pivots = calculate_pivots(data)

# Display the resulting dataframe with pivot points
print(pivots)


#PSAR 

import pandas as pd

def calculate_psar(df, af_start=0.02, af_step=0.02, af_max=0.2):
    # Initialize columns for PSAR
    df['PSAR'] = None
    df['Trend'] = None
    df['EP'] = None
    df['AF'] = None
    
    # Initialize variables
    trend = "UP"  # Start with an uptrend
    af = af_start
    ep = df['High'][0]  # First EP is the first high
    psar = df['Low'][0]  # First PSAR is the first low
    
    for i in range(1, len(df)):
        prev_psar = psar
        prev_trend = trend
        
        if prev_trend == "UP":
            # Update PSAR for uptrend
            psar = prev_psar + af * (ep - prev_psar)
            
            # Ensure PSAR does not exceed previous two lows
            psar = min(psar, df['Low'][i-1], df['Low'][i-2] if i > 1 else df['Low'][i-1])
            
            # Check for trend switch
            if df['Low'][i] < psar:
                trend = "DOWN"
                psar = ep  # Switch PSAR to EP
                ep = df['Low'][i]  # Update EP to current low
                af = af_start  # Reset AF
            else:
                # Update EP and AF for uptrend
                if df['High'][i] > ep:
                    ep = df['High'][i]
                    af = min(af + af_step, af_max)
        
        elif prev_trend == "DOWN":
            # Update PSAR for downtrend
            psar = prev_psar - af * (prev_psar - ep)
            
            # Ensure PSAR does not exceed previous two highs
            psar = max(psar, df['High'][i-1], df['High'][i-2] if i > 1 else df['High'][i-1])
            
            # Check for trend switch
            if df['High'][i] > psar:
                trend = "UP"
                psar = ep  # Switch PSAR to EP
                ep = df['High'][i]  # Update EP to current high
                af = af_start  # Reset AF
            else:
                # Update EP and AF for downtrend
                if df['Low'][i] < ep:
                    ep = df['Low'][i]
                    af = min(af + af_step, af_max)
        
        # Store values in the dataframe
        df.loc[i, 'PSAR'] = psar
        df.loc[i, 'Trend'] = trend
        df.loc[i, 'EP'] = ep
        df.loc[i, 'AF'] = af
    
    return df

# Example DataFrame
data = pd.DataFrame({
    'Date': ['2024-12-16', '2024-12-17', '2024-12-18', '2024-12-19', '2024-12-20'],
    'High': [150.0, 155.0, 152.0, 156.0, 157.0],
    'Low': [145.0, 149.0, 148.0, 151.0, 152.0],
    'Close': [148.0, 153.0, 150.0, 155.0, 156.0]
})

# Calculate PSAR
data = calculate_psar(data)

# Display the DataFrame with PSAR
print(data)


## fibonachi levels

import sqlite3
import pandas as pd

def fetch_ohlc_data(db_path, symbol, periods=108):
    """Fetch the last 'periods' rows of OHLC data for a specific symbol."""
    conn = sqlite3.connect(db_path)
    query = f"""
        SELECT * FROM ohlc
        WHERE symbol = '{symbol}'
        ORDER BY date DESC
        LIMIT {periods}
    """
    data = pd.read_sql(query, conn)
    conn.close()
    return data.sort_values('date')  # Ensure chronological order

def define_trend(data):
    """Determine the trend of the last 54 periods."""
    last_54 = data[-54:]
    trend_start = last_54['low'].min()
    trend_end = last_54['high'].max()
    is_uptrend = trend_start < trend_end
    return trend_start, trend_end, "uptrend" if is_uptrend else "downtrend"

def calculate_fibonacci_levels(trend_start, trend_end, trend_type):
    """Calculate Fibonacci levels based on the trend."""
    is_long = trend_type == "uptrend"

    levels = {
        'retracement_0': trend_start if is_long else trend_end,
        'retracement_23_6': trend_end - (trend_end - trend_start) * 0.236 if is_long else trend_start + (trend_end - trend_start) * 0.236,
        'retracement_38_2': trend_end - (trend_end - trend_start) * 0.382 if is_long else trend_start + (trend_end - trend_start) * 0.382,
        'retracement_50': (trend_end + trend_start) / 2,
        'retracement_61_8': trend_end - (trend_end - trend_start) * 0.618 if is_long else trend_start + (trend_end - trend_start) * 0.618,
        'retracement_78_6': trend_end - (trend_end - trend_start) * 0.786 if is_long else trend_start + (trend_end - trend_start) * 0.786,
        'extension_100': trend_end if is_long else trend_start,
        'extension_161_8': trend_end + (trend_end - trend_start) * 0.618 if is_long else trend_start - (trend_end - trend_start) * 0.618,
        'extension_261_8': trend_end + (trend_end - trend_start) * 1.618 if is_long else trend_start - (trend_end - trend_start) * 1.618,
    }
    return levels

def save_fibonacci_to_db(db_path, symbol, slug, trend_type, trend_start, trend_end, levels):
    """Save Fibonacci levels along with trend details to the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create table if not exists
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fibonacci_levels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            slug TEXT,
            trend_type TEXT,
            trend_start REAL,
            trend_end REAL,
            retracement_0 REAL,
            retracement_23_6 REAL,
            retracement_38_2 REAL,
            retracement_50 REAL,
            retracement_61_8 REAL,
            retracement_78_6 REAL,
            extension_100 REAL,
            extension_161_8 REAL,
            extension_261_8 REAL
        )
    ''')

    # Insert data
    cursor.execute('''
        INSERT INTO fibonacci_levels (
            symbol, slug, trend_type, trend_start, trend_end,
            retracement_0, retracement_23_6, retracement_38_2,
            retracement_50, retracement_61_8, retracement_78_6,
            extension_100, extension_161_8, extension_261_8
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        symbol, slug, trend_type, trend_start, trend_end,
        levels['retracement_0'], levels['retracement_23_6'], levels['retracement_38_2'],
        levels['retracement_50'], levels['retracement_61_8'], levels['retracement_78_6'],
        levels['extension_100'], levels['extension_161_8'], levels['extension_261_8']
    ))

    conn.commit()
    conn.close()

# Example usage
db_path = "market_data.db"  # Path to your database
symbol = "AAPL"            # Replace with your desired symbol
slug = "daily_aapl"        # Identifier for the data source

# Step 1: Fetch the last 108 periods
ohlc_data = fetch_ohlc_data(db_path, symbol)

# Step 2: Define the trend based on the last 54 periods
trend_start, trend_end, trend_type = define_trend(ohlc_data)

# Step 3: Calculate Fibonacci levels for the trend
fib_levels = calculate_fibonacci_levels(trend_start, trend_end, trend_type)

# Step 4: Save to the database
save_fibonacci_to_db(db_path, symbol, slug, trend_type, trend_start, trend_end, fib_levels)

print("Fibonacci levels saved successfully!")

