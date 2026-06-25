# Development Log

The thought and editing process behind the terminal — every problem we hit and
how it was solved. Written so the reasoning is reproducible, not just the result.

---

## 0. Background (notebook prework)
Before the standalone app, the same Alpaca/pandas ideas were worked out in the
course notebooks, which surfaced two issues that shaped the connector:
- **`yfinance` `'Adj Close'` KeyError** — recent `yfinance` defaults to
  `auto_adjust=True`, which drops the `Adj Close` column. Fix: pass
  `auto_adjust=False` (or use `Close`). *(Lesson: library defaults drift.)*
- **`ValueError: Cannot set a DataFrame with multiple columns…`** — a single-symbol
  download returns **MultiIndex columns** `(field, ticker)`, so `data["Close"]` is
  a 1-column DataFrame, not a Series. Fix: flatten the columns. This is the same
  bug class the connector handles with `df.xs(symbol, level="symbol")`.

## 1. Initial build
- **`data_connector.py`** — one `MarketData` class wrapping the Alpaca trading +
  market-data clients and the websocket. Keys load from the environment / `.env`,
  never hard-coded (rubric: API key handling).
- **`app.py`** — dark, monospaced, Bloomberg-style Streamlit terminal: watchlist,
  candlestick + volume chart, live quote panel, positions table.
- **`stream_quotes.py`** — CLI websocket bid/ask streamer.
- Supporting: `requirements.txt`, `README`, `GUIDE`, `.env.example`, `.gitignore`.

## 2. `connection limit exceeded` (websocket)
Running the streamer repeatedly threw `connection limit exceeded`, spamming
retries. **Cause:** the free Alpaca plan allows **one** live websocket; earlier
runs that weren't stopped cleanly kept the slot occupied, and each retry opened
*another* socket. **Fixes:** kill stray processes (`pkill -f stream_quotes.py`);
always stop with Ctrl+C; the script now catches the error and exits with a clear
message instead of retry-spamming.

## 3. Keys hard-coded in the notebook
The Alpaca secret was sitting in a notebook/script. **Fix:** moved all key
handling to env vars + a gitignored `.env`, with `.env.example` holding dummy
placeholders for the repo. Flagged that the exposed keys should be regenerated.

## 4. Excel export crashed
The **Data (OHLCV)** tab's Excel download raised *"Excel does not support
datetimes with timezones."* **Cause:** the bar index is tz-aware (ET). **Fix:**
strip the timezone (`tz_localize(None)`) for the export only, keeping the ET
wall-clock time; the on-screen table still shows ET.

## 5. `streamlit` launcher broken
`streamlit run app.py` failed with `No module named 'streamlit.cli'` — a stale
launcher script from an older version. **Fix:** run via `python -m streamlit run
app.py`, and updated all docs to match.

## 6. One-command launcher
To make it turnkey, added **`launch.py`** (install deps → prompt for keys → verify
→ open the app) and a double-clickable **`start.command`**. Now the whole project
is `python launch.py`.

## 7. Chart: zoom reset on every refresh
With auto-refresh on, the chart rebuilt every few seconds and threw away the
user's zoom/pan. **Fix:** plotly `uirevision` (tied to symbol|interval|history) so
the view is preserved across reruns and only resets when a control changes. Also
split the refresh cadence: the **quote** refetches every tick, but the **chart's
bars** are cached on a `bucket = time // interval` key, so a new pull happens only
once per bar (every 5 min for 5-min bars).

## 8. Chart: the "cliff" #1 — opening view on a weekend
The chart opened onto an empty band on the left. **Cause:** the initial range was
a *calendar* offset (`last_bar − 3 days`), which landed on a Sunday. **Fix:**
anchor the opening view to a **bar position** (~2 sessions back), so the left edge
is always a real trading bar.

## 9. Chart: "nothing after Jun 19" — the holiday gap
Data looked like it stopped at Jun 19 even though it ran to Jun 24. **Cause:**
**Jun 19, 2026 is Juneteenth**, a market holiday with no bars; the time-based
`rangebreaks` (weekends + overnight) don't know the market calendar, so plotly
reserved an empty slot for that Friday and the axis looked broken.
**Fix:** detect holidays *from the data* — any business day in range with zero
bars — and add them to `rangebreaks`. Self-maintaining for future holidays.
*(Briefly tried a categorical x-axis, which removed all gaps but broke the zoom
range; reverted to a datetime axis + data-driven holiday breaks.)*

## 10. Chart: the "cliff" #2 — pre/after-market bars
Zoomed into one day, an empty 03:00–09:00 band appeared. **Cause:** IEX returns
pre-market (from ~08:00) and after-hours bars, which sat inside the overnight gap
we were collapsing and confused the axis. **Fix:** filter the bars to **regular
trading hours (9:30–16:00 ET)** so there's no extended-hours data to leave a band.

## 11. Chart: overlapping x-axis labels
At the day boundary, the collapsed overnight put one session's `15:55` next to the
next `09:30`, and plotly's default two-line (time + date) labels overlapped.
**Fix:** single-line, angled labels (`tickformat="%b %d %H:%M"`, `tickangle=-30`,
fewer ticks).

## 12. Chart: volume bars vanishing
Low-volume bars didn't render — the volume axis floor had drifted above zero and a
single auction spike set the scale, so normal bars were either below the floor or
1px tall. **Fix:** anchor the volume axis at zero (`rangemode="tozero"`) and scale
it to the **95th percentile** of the opening window's volume (×1.2) instead of the
max, so the occasional spike clips at the top but everyday bars are clearly
visible. (True per-zoom rescaling would need a JS relayout handler, which Streamlit
1.30 doesn't expose cleanly; this keeps bars visible at every zoom level.)

## 13. Excel export crashed again — `No module named 'openpyxl'`
The **Data (OHLCV)** tab's Excel download failed with `No module named 'openpyxl'`
— and because the export is built on every rerun, the error surfaced under the
whole center panel. **Cause:** `openpyxl` is the engine pandas uses to write
`.xlsx`, and it was never listed in `requirements.txt`. **Fix:** added `openpyxl`
to `requirements.txt` and to `launch.py`'s dependency check, and installed it.

## 14. OS-specific run instructions
The docs said `python …`, but on macOS/Linux the command is usually `python3`
(plain `python` often doesn't exist) and on Windows it's `py`. **Fix:** the README
and GUIDE now show per-OS commands, with a note on the `python` vs `python3`
difference.

## 15. Font: a real terminal font, everywhere
The UI used `SF Mono` for numbers but `Inter` (a proportional UI sans) for labels,
which read like a generic web app rather than a terminal. **Fix:** the whole
interface is now the monospaced **Ubuntu Mono** (loaded from Google Fonts); both
`--mono` and `--sans` point at it, so brand, labels, numbers, and tables are all
monospace.

## 16. Dark / Light theme toggle
Added a `Theme` dropdown. **How:** the base CSS defines the dark palette; choosing
Light injects a second `:root` block that overrides only the color tokens, so every
`var(--…)` flips. The Plotly chart can't read CSS vars, so it takes matching
light/dark colors from a Python `THEMES` dict.

## 17. Native Streamlit widgets ignored the theme
A multi-lens audit found that Streamlit's own widgets (the dropdowns and their
popovers, the slider, the tabs, the download buttons, scrollbars) don't read our
CSS variables, so they'd be stranded in the wrong colors in Light mode and weren't
monospace. **Fixes:** explicit CSS for each, all bound to the theme vars so they
flip; a pinned base theme in `.streamlit/config.toml`; and the **Data (OHLCV)**
grid was rebuilt as a themed HTML table — `st.dataframe` is a canvas that can't be
themed or set to a monospace font, so the new table follows the theme and the font,
shows the newest 500 rows on screen, and the downloads keep the full set.

---

## Current state
The chart is clean from every angle tested: regular-hours only, no
weekend/overnight/holiday gaps, opens on a readable ~2-session zoom, pans to the
full 30 days, zoom survives auto-refresh, and labels never collide. The terminal
runs in a monospaced Ubuntu Mono font with a working **Dark/Light theme** across
every panel, control, and the chart; the OHLCV table and the Excel/CSV export work.
The data layer is verified live against Alpaca. Open items are the two manual
deliverables: push to GitHub and record the 2–5 min demo (see `GUIDE.md` §4–5).
