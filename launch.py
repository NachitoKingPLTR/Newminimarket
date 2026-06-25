#!/usr/bin/env python3
"""
One-step launcher for the Mini Market Data Terminal.

    python launch.py

Makes sure the dependencies are installed, asks for your Alpaca paper keys the
first time (and saves them to .env), checks they work, then opens the terminal
UI -- historical chart + live quote viewer -- in your browser.
"""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV_FILE = HERE / ".env"
PLACEHOLDERS = {"", "your_paper_api_key_here", "your_paper_secret_key_here"}


def read_env():
    """Read existing key/value pairs out of .env (if it's there)."""
    keys = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                keys[k.strip()] = v.strip()
    return keys


def have_real_keys(keys):
    return (keys.get("ALPACA_API_KEY") not in PLACEHOLDERS
            and keys.get("ALPACA_SECRET_KEY") not in PLACEHOLDERS)


def ask_for_keys():
    """Prompt for keys and write them to .env."""
    print("\n  Alpaca paper-trading keys needed (one-time setup).")
    print("  Get them at https://app.alpaca.markets  ->  Paper Trading  ->  API Keys\n")
    api = input("  API Key:    ").strip()
    sec = input("  Secret Key: ").strip()
    ENV_FILE.write_text(
        "# Local paper-trading keys (gitignored).\n"
        f"ALPACA_API_KEY={api}\n"
        f"ALPACA_SECRET_KEY={sec}\n"
    )
    print("\n  Saved to .env\n")
    return {"ALPACA_API_KEY": api, "ALPACA_SECRET_KEY": sec}


def ensure_deps():
    """Install requirements the first time if anything's missing."""
    try:
        import streamlit, alpaca, plotly, dotenv, openpyxl  # noqa: F401
        from streamlit_autorefresh import st_autorefresh  # noqa: F401
    except ImportError:
        print("  Installing dependencies (first run only)...\n")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r",
                        str(HERE / "requirements.txt")], check=True)


def verify(keys):
    """Quick auth check so bad keys fail here with a clear message."""
    os.environ["ALPACA_API_KEY"] = keys["ALPACA_API_KEY"]
    os.environ["ALPACA_SECRET_KEY"] = keys["ALPACA_SECRET_KEY"]
    from data_connector import MarketData
    MarketData().account()  # raises if the keys are wrong


def main():
    os.chdir(HERE)
    ensure_deps()

    keys = read_env()
    while not have_real_keys(keys):
        keys = ask_for_keys()

    # confirm the keys actually work; re-ask until they do
    while True:
        try:
            verify(keys)
            break
        except Exception as e:
            print(f"\n  Those keys didn't work ({e}).")
            print("  Let's try again.")
            keys = ask_for_keys()

    print("  Keys OK. Launching the terminal in your browser...")
    print("  (stop it anytime with Ctrl+C in this window)\n")
    subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py"])


if __name__ == "__main__":
    main()
