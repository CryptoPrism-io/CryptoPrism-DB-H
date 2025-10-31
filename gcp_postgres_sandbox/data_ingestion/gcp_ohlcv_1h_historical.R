# ============================================
# CryptoPrism-DB-H: Historical OHLCV Data Fetcher
# ============================================
# Description: Fetches historical hourly OHLCV data for specific date range
# Data Source: crypto2 R package (CoinMarketCap)
# Output Tables: ohlcv_1h_250_coins (APPEND mode)
# Usage: Modify START_DATE and END_DATE below

# Load required libraries
library(crypto2)
library(dplyr)
library(DBI)
library(RPostgres)

# Conditional dotenv loading (only for local development)
if (!Sys.getenv("GITHUB_ACTIONS") == "true") {
  if (!require("dotenv", quietly = TRUE)) {
    install.packages("dotenv")
    library(dotenv)
  } else {
    library(dotenv)
  }

  env_path <- ".env"
  if (file.exists(env_path)) {
    dotenv::load_dot_env(file = env_path)
    print(paste("✅ Loaded .env from:", normalizePath(env_path)))
  } else {
    print(paste("⚠️ .env file not found at:", normalizePath(env_path)))
    stop("⚠️ Please create .env file using .env.example as template")
  }
} else {
  print("🔹 Running in GitHub Actions: Using GitHub Secrets.")
}

# ============================================
# Configuration: Date Range for Historical Fetch
# ============================================
START_DATE <- as.Date("2025-09-10")
END_DATE <- as.Date("2025-10-30")  # Updated to include latest data

print("📅 Historical Data Fetch Configuration:")
print(paste("   START_DATE:", START_DATE))
print(paste("   END_DATE:", END_DATE))
print(paste("   Days to fetch:", as.numeric(END_DATE - START_DATE) + 1))

# ============================================
# Configuration: Environment Variables
# ============================================
CONFIG <- list(
  db_host = Sys.getenv("DB_HOST"),
  db_name = Sys.getenv("DB_NAME_AI", "cp_ai"),  # Default to cp_ai
  db_user = Sys.getenv("DB_USER"),
  db_password = Sys.getenv("DB_PASSWORD"),
  db_port = as.integer(Sys.getenv("DB_PORT", "5432"))
)

# Validate required environment variables
required_vars <- c("db_host", "db_user", "db_password")
missing_vars <- c()

for (var in required_vars) {
  if (is.null(CONFIG[[var]]) || CONFIG[[var]] == "" || is.na(CONFIG[[var]])) {
    missing_vars <- c(missing_vars, var)
  }
}

if (length(missing_vars) > 0) {
  stop(paste("❌ Missing environment variables:", paste(missing_vars, collapse = ", ")))
}

# Log configuration (DO NOT log password)
print("✅ Database Configuration Loaded:")
print(paste("   DB_HOST =", CONFIG$db_host))
print(paste("   DB_NAME =", CONFIG$db_name))
print(paste("   DB_PORT =", CONFIG$db_port))

# ============================================
# Data Collection: Cryptocurrency Listings
# ============================================
print("📡 Fetching cryptocurrency listings...")

crypto.listings.latest <- crypto_listings(
  which = "latest",
  convert = "USD",
  limit = 5000,
  start_date = Sys.Date()-1,
  end_date = Sys.Date()+1,
  interval = "daily",
  quote = TRUE,
  sort = "cmc_rank",
  sort_dir = "asc",
  sleep = 0,
  wait = 0,
  finalWait = FALSE
)

# Filter for top 250 cryptocurrencies by CMC rank
crypto.listings.latest <- crypto.listings.latest %>%
  filter(cmc_rank > 0 & cmc_rank < 250) %>%
  arrange(cmc_rank)

print(paste("✅ Fetched", nrow(crypto.listings.latest), "cryptocurrency listings"))

# ============================================
# Data Collection: Historical Hourly OHLCV Data
# ============================================
print(paste("📊 Fetching hourly OHLCV data from", START_DATE, "to", END_DATE, "..."))
print("⏳ This may take several minutes depending on the date range...")

all_coins <- crypto_history(
  coin_list = crypto.listings.latest,
  convert = "USD",
  limit = 200,
  start_date = START_DATE,
  end_date = END_DATE,
  sleep = 0,
  interval = "hourly"
)

# Select and organize columns
all_coins <- all_coins[, c("id", "slug", "name", "symbol", "timestamp",
                           "open", "high", "low", "close", "volume", "market_cap")]

print(paste("✅ Fetched", nrow(all_coins), "hourly OHLCV records"))
print(paste("   Time range:", min(all_coins$timestamp), "to", max(all_coins$timestamp)))
print(paste("   Unique coins:", length(unique(all_coins$slug))))
print(paste("   Unique timestamps:", length(unique(all_coins$timestamp))))

# ============================================
# Database Connection
# ============================================
print("🔌 Connecting to PostgreSQL database...")

con <- dbConnect(
  RPostgres::Postgres(),
  host = CONFIG$db_host,
  dbname = CONFIG$db_name,
  user = CONFIG$db_user,
  password = CONFIG$db_password,
  port = CONFIG$db_port
)

# Validate connection
if (!dbIsValid(con)) {
  stop("❌ Database connection failed. Please check your credentials.")
}

print("✅ Database connection successful")

# ============================================
# Data Write: Upload to Database (APPEND MODE)
# ============================================
print("💾 Writing data to database in APPEND mode...")
print("⚠️ NOTE: Using APPEND mode to preserve existing data")

# Check if table exists and show current record count
if (dbExistsTable(con, "ohlcv_1h_250_coins")) {
  current_count <- dbGetQuery(con, "SELECT COUNT(*) as count FROM ohlcv_1h_250_coins")$count
  print(paste("   Current records in table:", current_count))
} else {
  print("   Table does not exist - will be created")
}

# Write OHLCV data (APPEND mode - does not overwrite)
dbWriteTable(con, "ohlcv_1h_250_coins", all_coins, append = TRUE, row.names = FALSE)
print("✅ Appended data to ohlcv_1h_250_coins table")

# Check new record count
new_count <- dbGetQuery(con, "SELECT COUNT(*) as count FROM ohlcv_1h_250_coins")$count
print(paste("   New total records in table:", new_count))
print(paste("   Records added:", new_count - ifelse(exists("current_count"), current_count, 0)))

# ============================================
# Cleanup: Close Connection
# ============================================
dbDisconnect(con)
print("✅ Database connection closed")
print("✅ Historical data fetch completed successfully!")

# Print summary statistics
print("📊 Summary:")
print(paste("   Date range:", START_DATE, "to", END_DATE))
print(paste("   Total coins processed:", length(unique(all_coins$slug))))
print(paste("   Total OHLCV records fetched:", nrow(all_coins)))
print(paste("   Database:", CONFIG$db_name))
print(paste("   Mode: APPEND (existing data preserved)"))
