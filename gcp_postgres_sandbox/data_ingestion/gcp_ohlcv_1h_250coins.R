# ============================================
# CryptoPrism-DB-H: Hourly OHLCV ETL Script
# ============================================
# Description: Fetches hourly OHLCV data for top 250 cryptocurrencies
# Data Source: crypto2 R package (CoinMarketCap)
# Output Tables: ohlcv_1h_250_coins, crypto_listings_latest
# Frequency: Runs hourly via GitHub Actions

# Load required libraries
library(crypto2)
library(dplyr)
library(DBI)
library(RPostgres)

# Conditional dotenv loading (only for local development)
if (!Sys.getenv("GITHUB_ACTIONS") == "true") {
  # Check if dotenv is installed
  if (!require("dotenv", quietly = TRUE)) {
    install.packages("dotenv")
    library(dotenv)
  } else {
    library(dotenv)
  }

  # Load .env file from project root
  env_path <- ".env"
  if (file.exists(env_path)) {
    dotenv::load_dot_env(file = env_path)
    print(paste("✅ Loaded .env from:", normalizePath(env_path)))
  } else {
    print(paste("⚠️ .env file not found at:", normalizePath(env_path)))
    print("⚠️ Please create .env file using .env.example as template")
  }
} else {
  print("🔹 Running in GitHub Actions: Using GitHub Secrets.")
}

# ============================================
# Configuration: Environment Variables
# ============================================
CONFIG <- list(
  db_host = Sys.getenv("DB_HOST"),
  db_name = Sys.getenv("DB_NAME", "cp_ai"),  # Default to cp_ai for hourly data
  db_user = Sys.getenv("DB_USER"),
  db_password = Sys.getenv("DB_PASSWORD"),
  db_port = as.integer(Sys.getenv("DB_PORT", "5432"))
)

# ============================================
# Diagnostic Logging: Environment Variable Status
# ============================================
print("🔍 DIAGNOSTIC: Environment Variable Check")
print(paste("   GITHUB_ACTIONS =", Sys.getenv("GITHUB_ACTIONS")))
print(paste("   DB_HOST exists:", Sys.getenv("DB_HOST") != ""))
print(paste("   DB_USER exists:", Sys.getenv("DB_USER") != ""))
print(paste("   DB_PASSWORD exists:", Sys.getenv("DB_PASSWORD") != ""))
print(paste("   DB_NAME exists:", Sys.getenv("DB_NAME") != ""))
print(paste("   DB_PORT exists:", Sys.getenv("DB_PORT") != ""))
print(paste("   DB_HOST value:", ifelse(Sys.getenv("DB_HOST") != "", Sys.getenv("DB_HOST"), "[EMPTY]")))
print(paste("   DB_USER value:", ifelse(Sys.getenv("DB_USER") != "", Sys.getenv("DB_USER"), "[EMPTY]")))
print(paste("   DB_NAME value:", ifelse(Sys.getenv("DB_NAME") != "", Sys.getenv("DB_NAME"), "[EMPTY - will use default]")))
print(paste("   DB_PORT value:", ifelse(Sys.getenv("DB_PORT") != "", Sys.getenv("DB_PORT"), "[EMPTY - will use default]")))

# Validate required environment variables
required_vars <- c("db_host", "db_user", "db_password")
missing_vars <- c()

for (var in required_vars) {
  if (is.null(CONFIG[[var]]) || CONFIG[[var]] == "" || is.na(CONFIG[[var]])) {
    missing_vars <- c(missing_vars, var)
  }
}

if (length(missing_vars) > 0) {
  stop(paste("❌ Missing environment variables:", paste(missing_vars, collapse = ", "),
             "\nPlease check your .env file or GitHub Secrets configuration."))
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
# Data Collection: Hourly OHLCV Data
# ============================================
print("📊 Fetching hourly OHLCV data (last 5 days)...")

all_coins <- crypto_history(
  coin_list = crypto.listings.latest,
  convert = "USD",
  limit = 200,
  start_date = Sys.Date()-5,
  end_date = Sys.Date()+1,
  sleep = 0,
  interval = "hourly"
)

# Select and organize columns
all_coins <- all_coins[, c("id", "slug", "name", "symbol", "timestamp",
                           "open", "high", "low", "close", "volume", "market_cap")]

print(paste("✅ Fetched", nrow(all_coins), "hourly OHLCV records"))
print(paste("   Time range:", min(all_coins$timestamp), "to", max(all_coins$timestamp)))

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
# Data Write: Upload to Database
# ============================================
print("💾 Writing data to database...")

# Write OHLCV data (overwrites existing table)
dbWriteTable(con, "ohlcv_1h_250_coins", all_coins, overwrite = TRUE, row.names = FALSE)
print("✅ Uploaded ohlcv_1h_250_coins table")

# Write listings data (overwrites existing table)
dbWriteTable(con, "crypto_listings_latest", crypto.listings.latest, overwrite = TRUE, row.names = FALSE)
print("✅ Uploaded crypto_listings_latest table")

# ============================================
# Cleanup: Close Connection
# ============================================
dbDisconnect(con)
print("✅ Database connection closed")
print("✅ ETL process completed successfully!")

# Print summary statistics
print("📊 Summary:")
print(paste("   Total coins processed:", length(unique(all_coins$slug))))
print(paste("   Total OHLCV records:", nrow(all_coins)))
print(paste("   Total listings:", nrow(crypto.listings.latest)))
