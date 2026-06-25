"""
Market data connector for the mini terminal.

This is the one place that talks to Alpaca. Everything else (the UI, the CLI
streamer) goes through this so it doesn't have to deal with request objects,
multi-index DataFrames, or websocket setup. Keys are read from the environment
(or a local .env file) -- never hard-coded.
"""

import os
from datetime import datetime, timedelta

import pandas as pd
from dotenv import load_dotenv

from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.live import StockDataStream
from alpaca.data.requests import (
    StockBarsRequest,
    StockLatestQuoteRequest,
    StockLatestTradeRequest,
)
from alpaca.data.timeframe import TimeFrame

# Pull ALPACA_API_KEY / ALPACA_SECRET_KEY from a .env file if there is one.
load_dotenv()


class MarketData:
    """Thin wrapper around the Alpaca clients we actually use."""

    def __init__(self, api_key=None, api_secret=None, feed="iex", paper=True):
        # Fall back to the environment if keys weren't passed in explicitly.
        self.api_key = api_key or os.environ.get("ALPACA_API_KEY")
        self.api_secret = api_secret or os.environ.get("ALPACA_SECRET_KEY")
        if not self.api_key or not self.api_secret:
            raise RuntimeError(
                "Missing API keys. Set ALPACA_API_KEY and ALPACA_SECRET_KEY "
                "(see .env.example)."
            )

        self.feed = feed  # free accounts get the IEX feed
        self.trading = TradingClient(self.api_key, self.api_secret, paper=paper)
        self.data = StockHistoricalDataClient(self.api_key, self.api_secret)

    # --- account ---------------------------------------------------------

    def account(self):
        """Account object -- used for the auth check and the buying-power readout."""
        return self.trading.get_account()

    def positions(self):
        """Open positions for the paper account (list, possibly empty)."""
        return self.trading.get_all_positions()

    # --- historical ------------------------------------------------------

    def bars(self, symbol, days=30, timeframe=TimeFrame.Minute):
        """Historical OHLCV bars for the last `days` days as a clean DataFrame."""
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=timeframe,
            start=datetime.now() - timedelta(days=days),
            feed=self.feed,
        )
        df = self.data.get_stock_bars(request).df
        # A single-symbol pull comes back with a (symbol, timestamp) MultiIndex;
        # drop the symbol level so we're left with a plain time-indexed frame.
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level="symbol")
        return df

    # --- latest snapshot -------------------------------------------------

    def quote(self, symbol):
        """Latest bid/ask."""
        req = StockLatestQuoteRequest(symbol_or_symbols=symbol, feed=self.feed)
        q = self.data.get_stock_latest_quote(req)[symbol]
        return {"bid": q.bid_price, "ask": q.ask_price, "ts": q.timestamp}

    def last_trade(self, symbol):
        """Last traded price."""
        req = StockLatestTradeRequest(symbol_or_symbols=symbol, feed=self.feed)
        return self.data.get_stock_latest_trade(req)[symbol].price

    def snapshot(self, symbol):
        """bid / ask / last / spread in one shot -- what the quote panel needs."""
        q = self.quote(symbol)
        last = self.last_trade(symbol)
        spread = None
        if q["bid"] and q["ask"]:
            spread = round(q["ask"] - q["bid"], 4)
        return {"bid": q["bid"], "ask": q["ask"], "last": last,
                "spread": spread, "ts": q["ts"]}

    # --- streaming -------------------------------------------------------

    def new_stream(self):
        """A fresh websocket stream. The caller subscribes and runs it.

        Kept separate from the REST clients because the stream blocks when it
        runs, so it only makes sense from a script or a dedicated thread.
        """
        return StockDataStream(self.api_key, self.api_secret)
