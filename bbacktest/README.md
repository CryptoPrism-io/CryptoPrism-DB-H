# bbacktest

This folder contains a minimal, ready-to-run backtest scaffold that reads hourly prices and DMV signals from your PostgreSQL database and runs a simple strategy.

Contents:
- `vectorbt_backtest.py` — optional vectorbt-based backtest. If `vectorbt` is not installed, the script will still run a data sanity check and print instructions to install it.

Requirements:
- Environment variables set (same as the rest of the repo): `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_PORT` (default `5432`), `DB_NAME_BT` (default `cp_backtest_h`).
- Python packages: `pandas`, `sqlalchemy`, `psycopg2-binary`, `python-dotenv`. Optionally `vectorbt`.

Quick start:
1. Ensure `.env` is present at repo root with DB credentials.
2. (Optional) Install vectorbt: `pip install vectorbt`
3. Run: `python bbacktest/vectorbt_backtest.py`

Notes:
- The script uses a small default window (last 14 days) and limits to coins present in both prices and DMV signals.
- Fees/slippage are placeholders — adjust to your venue.

