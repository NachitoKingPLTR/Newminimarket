"""
Live bid/ask quote streamer (websocket).

Run from a terminal -- NOT the notebook -- because stream.run() blocks and needs
its own event loop:

    python stream_quotes.py            # AAPL
    python stream_quotes.py TSLA NVDA  # one or more symbols

Ctrl+C to stop. Free Alpaca accounts allow ONE live connection at a time, so
don't run two streamers at once (or a streamer plus the app's own stream).
"""

import sys

from data_connector import MarketData


def main():
    symbols = [s.upper() for s in sys.argv[1:]] or ["AAPL"]
    stream = MarketData().new_stream()

    async def on_quote(q):
        print(f"{q.symbol:6} bid={q.bid_price:<10} ask={q.ask_price:<10} ({q.timestamp})")

    stream.subscribe_quotes(on_quote, *symbols)
    print(f"Streaming {', '.join(symbols)} -- Ctrl+C to stop "
          f"(quotes flow during market hours only)\n")

    try:
        stream.run()
    except KeyboardInterrupt:
        print("\nStopping...")
        stream.stop()
    except ValueError as e:
        # Usually "connection limit exceeded" -- another stream is still open.
        print(f"\nStream error: {e}")
        print("Only one live connection is allowed. Close other streamers "
              "(pkill -f stream_quotes.py), wait a moment, and retry.")


if __name__ == "__main__":
    main()
