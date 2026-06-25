# Mini Market Data Terminal — Full Walkthrough & Presentation Guide

This document teaches the whole project end to end: the architecture, every file
and what it does, the concepts you should be able to explain, a script for the
demo video, how to put it on GitHub, and a rubric self-assessment.

For the chronological build/debug history — every problem we hit and how it was
fixed — see [`CHANGELOG.md`](CHANGELOG.md).

---

## 1. The big picture (architecture)

The project is three programs that all share **one data layer**:

```
                         ┌─────────────────────┐
                         │   Alpaca (cloud)    │
                         │  REST API + WebSocket│
                         └──────────┬──────────┘
                                    │  (your API keys)
                         ┌──────────▼──────────┐
                         │  data_connector.py  │   ← the ONLY file that
                         │   class MarketData  │     talks to Alpaca
                         └──────────┬──────────┘
                  ┌─────────────────┼──────────────────┐
                  │                 │                  │
        ┌─────────▼────────┐  ┌─────▼──────┐   ┌────────▼─────────┐
        │     app.py       │  │ stream_    │   │  (a notebook, a  │
        │ Streamlit UI     │  │ quotes.py  │   │  test, anything) │
        │ (charts, quotes) │  │ CLI stream │   │                  │
        └──────────────────┘  └────────────┘   └──────────────────┘
```

**Why this shape?** It's the single most important design idea in the project,
and the one to emphasize in the video: *separation of concerns*. The UI doesn't
know anything about Alpaca request objects or websockets — it just calls
`market.snapshot("AAPL")`. If Alpaca changed its API tomorrow, you'd edit one
file (`data_connector.py`) and everything downstream keeps working. This is the
"organize your code into modules" requirement, done properly.

**Two ways data flows in:**
- **REST (request/response):** the UI *asks* "what's the latest quote?" and gets
  one answer. We call this on a timer (polling) to make the UI feel live.
- **WebSocket (streaming):** Alpaca *pushes* every quote to us as it happens,
  with no asking. That's `stream_quotes.py`.

Both are required by the rubric, and we do both — REST powers the UI, WebSocket
is the dedicated streamer.

---

## 2. File-by-file walkthrough

### `data_connector.py` — the data layer

This wraps the three Alpaca clients we use and exposes simple methods.

- **`load_dotenv()`** (top of file): reads a local `.env` file and loads
  `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` into the environment. This is how keys
  stay *out* of the code.
- **`class MarketData.__init__`**: reads the keys from the environment (raising a
  clear error if they're missing), then builds:
  - `TradingClient` — account info and positions (the *trading* API).
  - `StockHistoricalDataClient` — historical bars and latest quotes/trades (the
    *market-data* API).
  - `feed="iex"` — free Alpaca accounts get the IEX data feed (a slice of total
    US volume). Paid plans get the full SIP feed; for this project IEX is fine.
- **`account()` / `positions()`**: thin pass-throughs to the trading client. Used
  by the UI's buying-power readout and positions table.
- **`bars(symbol, days, timeframe)`**: builds a `StockBarsRequest` and returns the
  result as a DataFrame. The important subtlety: a single-symbol request comes
  back with a **MultiIndex** `(symbol, timestamp)`. We do `df.xs(symbol,
  level="symbol")` to flatten it to a plain time-indexed frame. *(This is the
  exact bug class you hit earlier with `goog_data["Close"]` being two-dimensional
  — worth mentioning you understand it.)*
- **`quote()` / `last_trade()`**: latest bid/ask and last traded price.
- **`snapshot()`**: combines quote + last trade and computes the **spread**
  (ask − bid) — exactly the four numbers the quote panel shows.
- **`new_stream()`**: returns a fresh `StockDataStream`. It's a separate method
  because the stream **blocks** when it runs, so it only belongs in a script, not
  inside the request/response UI.

### `app.py` — the Streamlit terminal UI

**How Streamlit works (the mental model):** Streamlit reruns the *entire script*
top to bottom every time something changes (a widget value, a timer tick). There
is no callback spaghetti — you write a straight-line script, and Streamlit
re-executes it and diffs the output. That's why "auto-refresh" is literally "rerun
the script on a timer."

Walking through it:
- **`st.set_page_config(layout="wide")`** — full-width terminal layout.
- **The CSS block** — this is the "design system" the brief asked for, in one
  place. The `:root { --bg … --green … --mono … }` variables are the **design
  tokens** (colors + font stacks). Key choices:
  - a **Dark / Light theme**: the base block defines the dark palette, and the
    `Theme` dropdown injects a second `:root` block that overrides only the colors
    for light mode — so every `var(--…)` flips at once. Streamlit's own widgets
    (dropdowns, slider, tabs, buttons, scrollbars) are explicitly re-styled with
    the same vars so they flip too;
  - the whole UI is the **monospaced `Ubuntu Mono`** terminal font (loaded from
    Google Fonts); both `--mono` and `--sans` point at it, with `tabular-nums` so
    digits line up and prices don't jitter;
  - green/red used *only* for price direction, amber as the single accent;
  - because the Plotly chart can't read CSS variables, it gets its own matching
    light/dark colors from a small `THEMES` dict in Python.
- **`@st.cache_resource get_market()`** — builds the connector once per session
  (the clients are reusable; no reason to rebuild every rerun).
- **`load_bars(...)`** — caches the heavy historical pull, keyed on a
  `bucket = time // interval` argument so a fresh API pull only happens once per
  bar (every 5 min for 5-min bars). Quotes are **not** cached — the quote
  fragment refetches them on its own ~1-second timer so they stay live.
- **The day's change/percent** comes from the *previous close*, which the
  connector's one-call `snapshot()` returns alongside the quote (Alpaca's snapshot
  endpoint bundles the previous daily bar) — so no extra request is needed.
- **The controls row** — `text_input` is the "type a ticker" requirement;
  selectboxes/slider control the chart interval, history length and the
  **Dark / Light theme**, plus a **Live bar** checkbox for the live candle.
- **Live panels are `st.fragment`s** — instead of rerunning the whole page on a
  timer, each live panel (quote, watchlist, positions) is wrapped as
  `st.fragment(run_every=…)`, so it re-runs **only itself** in the background and
  repaints just its own output — no full-page reload, no flicker. The quote is the
  fast one (~1s); the rest are gentler to stay under Alpaca's rate limit (one
  snapshot call now returns quote + trade + prev-close).
  - The **chart's bars** stay cached against a `bucket = time // interval` key, so
    a fresh API pull only happens once per bar — not on every tick.
  - With **Live bar** on, the chart becomes a fragment that re-renders every ~2s,
    drawing a live current-price line and growing the forming candle from the
    latest trade. Streamlit re-creates the Plotly chart on each tick (so it can't
    hold a mid-pan zoom), so live mode pins the view to the most recent bars --
    turn Live bar off to pan/zoom through history.
- **Three-column grid** — `left` market-watch, `center` chart, `right` quote
  panel; then a full-width positions table at the bottom. This is the
  brief's modular layout: watchlist / chart / quote / positions.
- **The center area has two tabs:**
  - **Chart** — a Plotly candlestick (OHLC) with a volume sub-panel underneath
    (volume tinted by candle direction), a dark/light template matching the
    theme, green/red candles. It
    opens zoomed in on the last ~2 sessions so individual 5-min bars are readable,
    and you drag to pan or double-click / home icon for the full 30 days. To keep
    the candles flush with no dead space, three things happen:
    - the bars are filtered to **regular trading hours (9:30–16:00 ET)** so IEX's
      pre/after-market bars don't leave empty bands;
    - `rangebreaks` hide weekends and the overnight gap, **plus market holidays
      detected from the data** (any business day with no bars, e.g. Juneteenth) —
      time-based breaks alone can't know the market calendar;
    - the opening view is anchored to a **bar position** (not a calendar date,
      which could land on a weekend/holiday and open onto an empty "cliff");
    - x-axis labels are single-line and angled so they don't collide at the day
      boundary where the collapsed overnight squeezes ticks together;
    - the volume sub-axis is anchored at zero and scaled to the 95th-percentile of
      the window's volume, so everyday bars stay visible instead of being dwarfed
      by the odd auction spike.
  - **Data (OHLCV)** — the same bars as a **themed, monospaced HTML table**
    (Timestamp ET + Open/High/Low/Close/Volume, newest first). It's hand-built
    rather than `st.dataframe`, because Streamlit's grid is a canvas that can't be
    themed or set to a monospace font; the HTML table follows the Dark/Light theme
    and the Ubuntu Mono font. The screen shows the newest 500 rows, while the
    one-click **Excel** and **CSV** downloads always hold the *full* range
    (timezone stripped for export, since Excel can't store tz-aware datetimes).
    This is the most literal way to satisfy "show OHLCV clearly."
- **The quote panel** — big monospaced last price colored by direction, then
  bid / ask / spread / last, and an "updated at" timestamp.
- **The positions table** — pulls real paper positions and colors unrealized P&L.
- Every panel is wrapped in `try/except` so one bad symbol or a closed market
  shows a tidy message instead of a stack trace.

### `stream_quotes.py` — the websocket streamer

- Builds a stream via `MarketData().new_stream()` (so it reuses the same keys, no
  duplication).
- `on_quote` is an **async** callback — Alpaca calls it for every incoming quote.
- `stream.subscribe_quotes(on_quote, *symbols)` says "send me quotes for these."
- `stream.run()` **blocks** and runs its own event loop — that's why this is a
  script, not a notebook cell (Jupyter already has an event loop, so it would
  clash).
- The `except ValueError` catches `connection limit exceeded` and prints a useful
  hint. Remember: the free plan allows **one** live connection — don't run two
  streamers at once.

### `launch.py` / `start.command` — the one-command launcher
- **`launch.py`** — what you actually run day to day. It installs missing
  dependencies on first run, prompts for your Alpaca keys if `.env` is missing/has
  placeholders (and saves them), verifies the keys authenticate, then starts the
  Streamlit app. So the whole project is `python3 launch.py` (use `py` on Windows).
- **`start.command`** — a double-clickable macOS wrapper that just runs
  `launch.py` in Terminal.

### Config files
- **`.env`** — your real keys. **Gitignored**, so it never reaches GitHub.
- **`.env.example`** — a template with dummy values, committed so others know
  what to set. (This is the rubric's "config files with dummy keys, not real
  secrets.")
- **`.gitignore`** — keeps `.env`, caches, and `.DS_Store` out of the repo.
- **`requirements.txt`** — exact libraries to `pip install` (includes `openpyxl`,
  which pandas needs to write the `.xlsx` export).
- **`.streamlit/config.toml`** — pins the default Streamlit theme (`base="dark"`)
  so the native widgets start from a predictable place; the in-app `Theme` toggle
  restyles everything on top of it.
- Always launch Streamlit via `python3 -m streamlit run app.py` (or `launch.py`;
  `py` on Windows), never the bare `streamlit` command — that avoids stale
  launcher-script errors (`No module named 'streamlit.cli'`).

---

## 3. Concepts you should be able to explain on camera

- **Paper trading** — a simulated account with fake money; no real orders, no
  card. The whole project runs against it.
- **OHLCV bar** — one time bucket's Open, High, Low, Close, Volume. A candlestick
  draws one bar.
- **Bid / Ask / Spread** — bid = highest price a buyer will pay; ask = lowest a
  seller will accept; spread = ask − bid (a liquidity/cost measure).
- **REST vs WebSocket** — pull one answer on request vs. a pushed live feed.
- **Polling** — repeatedly asking via REST on a timer to *simulate* live (what the
  UI does, per-panel via Streamlit fragments). Cheaper/simpler than wiring a
  websocket into the UI.
- **IEX vs SIP feed** — IEX (free) is one exchange's tape; SIP (paid) is the
  consolidated national tape.

---

## 4. Demo video script (aim for 2–5 minutes)

Have the app already running (`python3 launch.py`) and a terminal ready.

1. **Intro (15s).** "This is a mini market-data terminal built on Alpaca's API in
   Python. It has three parts: a data connector, a live Streamlit UI, and a
   command-line quote streamer."
2. **Architecture (30s).** Show the diagram in this guide or the folder. "All
   Alpaca access lives in one module, `data_connector.py`. The UI and the
   streamer both call into it — separation of concerns, so the UI never touches
   the API directly."
3. **Authentication (20s).** Show `.env.example` and explain keys load from the
   environment, never hard-coded; the real `.env` is gitignored. Point to the
   buying-power readout in the header as proof auth works.
4. **Historical data + chart (40s).** Type a ticker (e.g. `MSFT`). Show the
   candlestick + volume. **Drag** to pan through the month, **double-click** to
   snap back to the full 30 days, **mouse-wheel** to zoom. "This is 30 days of
   5-minute bars, filtered to regular trading hours, with weekends and holidays
   collapsed so the candles are flush." Then open the **Data (OHLCV)** tab and
   click **Download Excel** to show the raw OHLCV export.
5. **Live quote (40s).** Point at the quote panel — last price, bid, ask, spread,
   and the updating timestamp. It refreshes itself ~once a second in the
   background (no button to press) — if markets are open, just let it tick on
   camera. Mention it's a Streamlit *fragment*, so only that panel repaints.
6. **Streaming (40s).** Switch to the terminal, run `python3 stream_quotes.py AAPL`,
   and show real quotes printing. "This is the websocket feed — Alpaca pushes
   each quote instead of us asking." Ctrl+C to stop cleanly.
7. **Positions + wrap (20s).** Show the positions table (or "no open positions").
   "Built on a clean modular core, a switchable dark/light institutional UI in a
   monospace terminal font, both REST and streaming. Thanks for watching."

Tips: full-screen the browser, hide bookmarks, slow down your clicks, and
pre-pick a moment when the market is open so quotes actually move.

---

## 5. Putting it on GitHub

1. **Regenerate your Alpaca keys first.** Your old keys were written into files
   earlier, so treat them as burned: Alpaca dashboard → Paper Trading → API Keys →
   regenerate. Put the new ones only in `.env`.
2. **Confirm `.env` is ignored:**
   ```bash
   cd "Newminimarket"
   git init
   git status          # .env must NOT appear in the list
   ```
   If `.env` shows up, the `.gitignore` isn't being picked up — fix before
   committing.
3. **First commit & push:**
   ```bash
   git add .
   git commit -m "Mini market data terminal (Alpaca)"
   gh repo create Newminimarket --public --source=. --push
   # or make the repo on github.com and: git remote add origin <url>; git push -u origin main
   ```
4. **Add the screenshot.** Drop a screen capture at `docs/screenshot.png` (the
   README already links it) so the repo looks finished.
5. **Sanity check the repo on github.com:** README renders, `.env` is absent,
   `requirements.txt` present, code in place.

---

## 6. Rubric self-assessment (Homework #1, 100 pts)

| Component | Pts | Status | Notes / how to push it higher |
|---|---|---|---|
| Alpaca authentication & API key handling | 10 | ✅ Strong | Keys from env/`.env`, gitignored, dummy `.env.example`. Verified live (account + buying power print). |
| Historical data retrieval | 20 | ✅ Strong | `bars()` pulls 30d of 1/5-min bars, MultiIndex flattened. Verified (566 bars returned). |
| Historical chart | 15 | ✅ Strong | Candlestick + volume (zoomed, pannable) **plus** a Data tab with the OHLCV table and Excel/CSV export — OHLCV shown two clear ways. |
| Real-time quote streaming | 20 | ✅ Strong | `stream_quotes.py` websocket; verified printing live quotes. |
| UI displays bid/ask + updates | 20 | ✅ Strong | Quote panel shows bid/ask/last/spread and refreshes itself ~1×/sec in the background via `st.fragment(run_every=…)` — only that panel repaints, no full-page reload. To go further, drive it from the websocket. |
| Code organization | 5 | ✅ Strong | Single data layer, UI/stream separated, clear names. |
| GitHub repo completeness | 5 | ⚠️ To do | README ✅, requirements ✅, `.gitignore` ✅ — **you still need to push it and add the screenshot.** |
| Demo video | 5 | ⚠️ To do | Use the script in section 4. |

**Estimated once pushed + video recorded: ~100/100.** The only open items are the
two you have to physically do: push to GitHub and record the demo.

### Optional upgrades (if you want to over-deliver)
- Overlay a moving average (e.g. SMA-20) on the chart.
- Make the market-watch rows clickable to set the active ticker.
- Feed the live websocket into the UI so bid/ask updates with zero polling delay.
- Add a tiny `tests/` with one test that mocks Alpaca and checks `snapshot()`
  returns the right keys.
