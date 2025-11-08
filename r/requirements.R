# ============================================
# CryptoPrism-DB-H: R Requirements
# ============================================
# Description: R package dependencies for hourly OHLCV data collection
# R Version: 4.0+

# List of required packages
required_packages <- c(
  "crypto2",      # CoinMarketCap API data fetching
  "dplyr",        # Data manipulation
  "DBI",          # Database interface
  "RPostgres",    # PostgreSQL connectivity
  "dotenv"        # Environment variable management
)

# ============================================
# Installation Function
# ============================================
install_if_missing <- function(packages) {
  for (pkg in packages) {
    if (!require(pkg, character.only = TRUE, quietly = TRUE)) {
      cat(paste("Installing package:", pkg, "\n"))
      install.packages(pkg, dependencies = TRUE, repos = "https://cloud.r-project.org/")
    } else {
      cat(paste("✅ Package already installed:", pkg, "\n"))
    }
  }
}

# ============================================
# Auto-install (uncomment to run)
# ============================================
# install_if_missing(required_packages)

# ============================================
# Manual Installation Instructions
# ============================================
# Run in R console:
#   source("requirements.R")
#   install_if_missing(required_packages)
#
# Or install individually:
#   install.packages(c("crypto2", "dplyr", "DBI", "RPostgres", "dotenv"))
#
# For GitHub Actions (already configured in r_cron.yml):
#   Rscript -e 'install.packages(c("crypto2", "dplyr", "DBI", "RPostgres", "dotenv"))'
# ============================================

cat("\n📦 Required R Packages for CryptoPrism-DB-H:\n")
cat(paste("  -", required_packages, collapse = "\n"))
cat("\n\n💡 To install, run: install_if_missing(required_packages)\n")
