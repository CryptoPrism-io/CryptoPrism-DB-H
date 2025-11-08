#!/usr/bin/env python3
"""Launch vectorbt backtest using the local .venv interpreter."""

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    venv_python = repo_root / ".venv" / "Scripts" / "python.exe"

    if not venv_python.exists():
        print("[ERROR] .venv not found. Run `py -3.12 -m venv .venv` first.")
        return 1

    script = repo_root / "bbacktest" / "vectorbt_backtest.py"
    if not script.exists():
        print(f"[ERROR] Backtest script missing: {script}")
        return 1

    args = [str(venv_python), str(script)] + sys.argv[1:]
    try:
        return subprocess.call(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

