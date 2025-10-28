# CryptoPrism-DB-H

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![R](https://img.shields.io/badge/R-4.0%2B-blue.svg)](https://www.r-project.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-13%2B-blue.svg)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-brightgreen.svg)]()

[![R Data Collection](https://github.com/CryptoPrism-io/CryptoPrism-DB-H/actions/workflows/r_cron.yml/badge.svg)](https://github.com/CryptoPrism-io/CryptoPrism-DB-H/actions/workflows/r_cron.yml)
[![Python Analysis](https://github.com/CryptoPrism-io/CryptoPrism-DB-H/actions/workflows/py_cron.yml/badge.svg)](https://github.com/CryptoPrism-io/CryptoPrism-DB-H/actions/workflows/py_cron.yml)

**Hourly Cryptocurrency Technical Analysis Pipeline**

CryptoPrism-DB-H is an automated hourly data processing system for cryptocurrency technical analysis. It collects OHLCV data every hour and performs comprehensive DMV (Durability-Momentum-Valuation) analysis on the top 250 cryptocurrencies.

---

## 📊 Project Overview

### What is CryptoPrism-DB-H?

CryptoPrism-DB-H is the **hourly companion** to CryptoPrism-DB, designed for short-term trading signals and rapid market analysis. While the original CryptoPrism-DB focuses on daily analysis over 110 days, this system provides real-time hourly insights over a 5-day rolling window.

### Key Features

✅ **Hourly Data Collection**: Top 250 cryptocurrencies updated every hour
✅ **5-Day Rolling Window**: Optimal for short-term technical analysis
✅ **DMV Framework**: Comprehensive Durability, Momentum, Valuation metrics
✅ **Multi-Database Architecture**: Separate DBs for production, current, and historical data
✅ **Automated Pipeline**: GitHub Actions for zero-maintenance execution
✅ **Historical Backtesting**: Automatic storage in `cp_backtest_h` database
✅ **Production Ready**: Environment-based secrets management

---

## 🏗️ Architecture

### System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    GitHub Actions Scheduler                      │
│  ┌──────────────────────┐    ┌──────────────────────────────┐ │
│  │   r_cron.yml         │    │   py_cron.yml                 │ │
│  │   Runs: :01 hourly   │    │   Runs: :05 hourly           │ │
│  └──────────┬───────────┘    └───────────┬──────────────────┘ │
└─────────────┼─────────────────────────────┼────────────────────┘
              │                             │
              ▼                             ▼
┌─────────────────────────┐   ┌────────────────────────────────┐
│  Data Ingestion Layer   │   │  Technical Analysis Layer      │
│                         │   │                                │
│  gcp_ohlcv_1h_250coins  │   │  ┌──────────────────────────┐ │
│  .R                     │───┼─▶│ gcp_dmv_tvv_pct_1h.py    │ │
│                         │   │  └────────┬─────────────────┘ │
│  - Fetches top 250 coins│   │           │                   │
│  - 5 days hourly OHLCV  │   │  ┌────────▼─────────────────┐ │
│  - Stores in cp_ai DB   │   │  │ gcp_dmv_osc_mom_rat_1h.py│ │
└─────────────────────────┘   │  └────────┬─────────────────┘ │
                              │           │                   │
                              │  ┌────────▼─────────────────┐ │
                              │  │ gcp_dmv_core_1h.py       │ │
                              │  │ (Aggregator - RUNS LAST) │ │
                              │  └──────────────────────────┘ │
                              └────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                  PostgreSQL Databases (GCP)                      │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐   │
│  │   dbcp       │  │   cp_ai      │  │  cp_backtest_h     │   │
│  │ (Production) │  │  (Hourly)    │  │  (Historical)      │   │
│  ├──────────────┤  ├──────────────┤  ├────────────────────┤   │
│  │ • Listings   │  │ • OHLCV 1h   │  │ • Historical FE_*  │   │
│  │ • Top 1000   │  │ • FE_TVV     │  │ • Backtest data    │   │
│  │              │  │ • FE_OSC     │  │ • Append-only      │   │
│  │              │  │ • FE_MOM     │  │                    │   │
│  │              │  │ • FE_RAT     │  │                    │   │
│  │              │  │ • FE_DMV_ALL │  │                    │   │
│  └──────────────┘  └──────────────┘  └────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
┌──────────────────────┐
│ CoinMarketCap API    │
│ (via crypto2 R pkg)  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ OHLCV Data           │
│ 250 coins x 5 days   │
│ Hourly frequency     │
└──────────┬───────────┘
           │
           ├──► TVV Analysis (Volume/Value/Risk)
           │
           ├──► OSC Analysis (Oscillators)
           │
           ├──► MOM Analysis (Momentum)
           │
           └──► RAT Analysis (Ratios)
                      │
                      ▼
           ┌──────────────────────┐
           │  DMV Core Aggregator │
           │  Joins all signals   │
           └──────────┬───────────┘
                      │
                      ├──► FE_DMV_ALL (All signals)
                      │
                      └──► FE_DMV_SCORES (D/M/V scores)
```

---

## 📈 CryptoPrism-DB vs CryptoPrism-DB-H

| Feature | CryptoPrism-DB | CryptoPrism-DB-H |
|---------|----------------|------------------|
| **Frequency** | Daily | **Hourly** |
| **Data Scope** | 1000 coins, 110 days | **250 coins, 5 days** |
| **Update Schedule** | Once daily | **Every hour** |
| **Use Case** | Long-term trends | **Short-term trading** |
| **Databases** | dbcp, cp_ai, cp_backtest | dbcp, cp_ai, **cp_backtest_h** |
| **Execution Time** | ~15 min/day | **~10 min/hour** |
| **Focus** | Strategic positioning | **Tactical entries/exits** |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- R 4.0+
- PostgreSQL database access
- Git

### Installation

1. **Clone the repository**:
```bash
git clone https://github.com/yourusername/CryptoPrism-DB-H.git
cd CryptoPrism-DB-H
```

2. **Set up environment variables**:
```bash
# Copy the example file
cp .env.example .env

# Edit .env with your credentials
# Required variables:
# - DB_HOST
# - DB_USER
# - DB_PASSWORD
# - DB_NAME (cp_ai)
# - DB_NAME_PROD (dbcp)
# - DB_NAME_BT (cp_backtest_h)
# - DB_PORT (5432)
```

3. **Install Python dependencies**:
```bash
pip install -r requirements.txt
```

4. **Install R dependencies**:
```bash
Rscript -e 'source("requirements.R"); install_if_missing(required_packages)'
```

### Local Execution

**Run data collection**:
```bash
Rscript gcp_postgres_sandbox/data_ingestion/gcp_ohlcv_1h_250coins.R
```

**Run technical analysis**:
```bash
# Step 1: TVV & PCT Analysis
python gcp_postgres_sandbox/technical_analysis/gcp_dmv_tvv_pct_1h.py

# Step 2: OSC, MOM, RAT Analysis
python gcp_postgres_sandbox/technical_analysis/gcp_dmv_osc_mom_rat_1h.py

# Step 3: DMV Core Aggregation (MUST run last)
python gcp_postgres_sandbox/technical_analysis/gcp_dmv_core_1h.py
```

---

## 📁 Project Structure

```
CryptoPrism-DB-H/
├── .github/workflows/           # GitHub Actions automation
│   ├── r_cron.yml              # Hourly R script (runs at :01)
│   ├── py_cron.yml             # Hourly Python scripts (runs at :05)
│   └── test_py.yml             # Optional testing workflow
│
├── gcp_postgres_sandbox/        # Main codebase (modular structure)
│   ├── data_ingestion/         # Data collection scripts
│   │   └── gcp_ohlcv_1h_250coins.R
│   │
│   ├── technical_analysis/     # Analysis modules
│   │   ├── gcp_dmv_tvv_pct_1h.py
│   │   ├── gcp_dmv_osc_mom_rat_1h.py
│   │   └── gcp_dmv_core_1h.py
│   │
│   ├── trading_signals/        # Signal generation
│   │   └── entry_exit_signals_1h.py
│   │
│   └── quality_assurance/      # QA automation (future)
│
├── .env.example                 # Environment template
├── .gitignore                   # Security protection
├── requirements.txt             # Python dependencies
├── requirements.R               # R dependencies
├── CHANGELOG.md                 # Version history
├── CLAUDE.md                    # Project memory & instructions
├── README.md                    # This file
└── LICENSE                      # License information
```

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the root directory:

```env
# Database Configuration
DB_HOST=your_postgresql_host
DB_NAME=cp_ai
DB_NAME_PROD=dbcp
DB_NAME_BT=cp_backtest_h
DB_USER=your_username
DB_PASSWORD=your_password
DB_PORT=5432
```

### GitHub Actions Setup

1. **Create Production Environment**:
   - Go to: Repository → Settings → Environments
   - Click "New environment"
   - Name: `production`

2. **Add Environment Secrets**:
   - `DB_HOST`
   - `DB_NAME`
   - `DB_NAME_PROD`
   - `DB_NAME_BT`
   - `DB_USER`
   - `DB_PASSWORD`
   - `DB_PORT`

3. **Verify Workflow Files**:
   - Both `r_cron.yml` and `py_cron.yml` must have `environment: production`

---

## 🤖 GitHub Actions

### Automated Schedules

**Data Collection** (`r_cron.yml`):
- **Schedule**: Every hour at :01 (e.g., 1:01, 2:01, 3:01...)
- **Script**: `gcp_ohlcv_1h_250coins.R`
- **Duration**: ~5-10 minutes
- **Output**: OHLCV data for 250 coins

**Technical Analysis** (`py_cron.yml`):
- **Schedule**: Every hour at :05 (e.g., 1:05, 2:05, 3:05...)
- **Scripts**: 3 Python scripts in sequence
- **Duration**: ~5-8 minutes
- **Output**: DMV signals and scores

### Manual Execution

1. Navigate to: **Actions** tab
2. Select workflow: `Rscript_1h` or `pyScript_1h`
3. Click **Run workflow**
4. Monitor execution in real-time

---

## 📊 Database Tables

### Input Tables (cp_ai)
- `ohlcv_1h_250_coins` - Raw OHLCV data
- `crypto_listings_latest` - Coin metadata

### Feature Engineering Tables (cp_ai)
- `FE_TVV` - Trading Volume/Value features
- `FE_TVV_SIGNALS` - Binary volume signals
- `FE_PCT_CHANGE` - Risk/volatility metrics
- `FE_OSCILLATOR` - Raw oscillator values (RSI, Stoch, etc.)
- `FE_OSCILLATORS_SIGNALS` - Binary oscillator signals
- `FE_MOMENTUM` - Raw momentum values (MACD, etc.)
- `FE_MOMENTUM_SIGNALS` - Binary momentum signals
- `FE_RATIOS` - Raw ratio values (risk/reward)
- `FE_RATIOS_SIGNALS` - Binary ratio signals

### Aggregated Tables (cp_ai)
- `FE_DMV_ALL` - All signals joined by coin
- `FE_DMV_SCORES` - Durability, Momentum, Valuation scores

### Historical Tables (cp_backtest_h)
- All FE_* tables (append-only for backtesting)

---

## 🔍 Usage Examples

### Query Latest DMV Scores

```sql
-- Get top 10 coins by Durability score
SELECT
    slug,
    name,
    durability_score,
    momentum_score,
    valuation_score,
    timestamp
FROM "FE_DMV_SCORES"
ORDER BY durability_score DESC
LIMIT 10;
```

### Check Recent Signals

```sql
-- Get coins with all positive signals
SELECT
    slug,
    name,
    tvv_signal,
    momentum_signal,
    oscillator_signal,
    ratio_signal,
    timestamp
FROM "FE_DMV_ALL"
WHERE tvv_signal = 1
  AND momentum_signal = 1
  AND oscillator_signal = 1
  AND ratio_signal = 1
ORDER BY timestamp DESC;
```

### Backtest Historical Data

```sql
-- Analyze performance over last 24 hours
SELECT
    slug,
    name,
    AVG(durability_score) as avg_durability,
    AVG(momentum_score) as avg_momentum,
    AVG(valuation_score) as avg_valuation,
    COUNT(*) as data_points
FROM cp_backtest_h."FE_DMV_SCORES"
WHERE timestamp >= NOW() - INTERVAL '24 hours'
GROUP BY slug, name
ORDER BY avg_momentum DESC
LIMIT 20;
```

---

## 🐛 Troubleshooting

### Common Issues

#### ❌ "Missing environment variables"

**Solution**:
- **Local**: Create `.env` file from `.env.example`
- **GitHub Actions**: Configure production environment secrets

#### ❌ "Database connection failed"

**Solutions**:
1. Verify credentials in `.env` or secrets
2. Check database host is accessible
3. Verify PostgreSQL port (default: 5432)
4. Check firewall rules on GCP

#### ❌ "FE_*_SIGNALS table not found"

**Solution**:
1. Ensure analysis scripts ran before core script
2. Check execution order: TVV/PCT → OSC/MOM/RAT → Core
3. Manually run prerequisite scripts first

#### ❌ "ModuleNotFoundError: No module named 'dotenv'"

**Solution**:
```bash
pip install python-dotenv
# or
pip install -r requirements.txt
```

#### ❌ R package not found

**Solution**:
```r
install.packages("dotenv")
# or
source("requirements.R")
install_if_missing(required_packages)
```

### Execution Order Issues

**CRITICAL**: Scripts MUST run in this sequence:

1. **Data Collection** (runs at :01)
   - `gcp_ohlcv_1h_250coins.R`

2. **Technical Analysis** (runs at :05)
   - Step 1: `gcp_dmv_tvv_pct_1h.py`
   - Step 2: `gcp_dmv_osc_mom_rat_1h.py`
   - Step 3: `gcp_dmv_core_1h.py` (**MUST run last**)

If you see dependency errors, verify this execution order.

---

## 📚 Documentation

- **[CHANGELOG.md](CHANGELOG.md)** - Version history and release notes
- **[CLAUDE.md](CLAUDE.md)** - Comprehensive project memory, architecture details, and development guidelines
- **[.env.example](.env.example)** - Environment variable template

---

## 🔐 Security

- ✅ **No Hardcoded Credentials**: All sensitive data in environment variables
- ✅ **GitHub Secrets**: Production credentials stored securely
- ✅ **Protected .env**: .gitignore prevents credential leaks
- ✅ **Read-Only Queries**: Analysis scripts use SELECT only

---

## 🛠️ Technology Stack

- **Languages**: Python 3.9+, R 4.0+
- **Database**: PostgreSQL 13+ (GCP Cloud SQL)
- **Data Source**: CoinMarketCap API (via crypto2 R package)
- **Automation**: GitHub Actions (cron schedules)
- **Environment**: python-dotenv, dotenv (R)
- **Python Libraries**: pandas, numpy, sqlalchemy, psycopg2
- **R Libraries**: crypto2, dplyr, DBI, RPostgres

---

## 📈 Performance

- **Data Collection**: ~5-10 minutes (API rate limits)
- **TVV & PCT Analysis**: ~2-3 minutes
- **OSC, MOM, RAT Analysis**: ~3-5 minutes
- **DMV Core Aggregation**: ~1-2 minutes
- **Total Pipeline**: ~10-15 minutes per hour

---

## 🚦 Status

- ✅ **Production Ready**: v1.0.0
- ✅ **Automated**: Hourly execution via GitHub Actions
- ✅ **Monitored**: Structured logging with timestamps
- ✅ **Documented**: Comprehensive guides and memory
- ✅ **Secure**: Environment-based credential management

---

## 📝 Version

**Current Version**: 1.0.0
**Last Updated**: 2025-10-28
**Status**: Production Ready

---

## 📞 Support

- **Issues**: Report at GitHub repository Issues tab
- **Documentation**: See [CLAUDE.md](CLAUDE.md) for detailed guidelines
- **Changelog**: See [CHANGELOG.md](CHANGELOG.md) for version history

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 🙏 Acknowledgments

- Based on architecture patterns from [CryptoPrism-DB](https://github.com/yourusername/CryptoPrism-DB)
- Data provided by CoinMarketCap API via [crypto2](https://github.com/sstoeckl/crypto2) R package
- Technical analysis indicators powered by pandas_ta and custom implementations

---

**Built with ❤️ for the crypto trading community**
