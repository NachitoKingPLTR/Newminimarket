"""
Mini Market Data Terminal -- Streamlit UI.

A compact, dark/light, institutional-looking terminal: type a ticker and get a
live quote, a candlestick chart of recent history, and your paper-trading
positions. The live panels (quote, watchlist, positions) each update on their
own in the background using Streamlit *fragments* -- only the panel that changed
repaints, so there's no full-page refresh.

    python3 -m streamlit run app.py

Data comes from Alpaca via data_connector.MarketData. Quotes only move during
US market hours; outside of those you'll still see the last known values.
"""

import io
import time
from datetime import datetime

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from data_connector import MarketData

st.set_page_config(page_title="Mini Terminal", layout="wide",
                   initial_sidebar_state="collapsed")

# --------------------------------------------------------------------------
# Look and feel. One CSS block keeps the "design tokens" (colors, fonts) in
# one spot. Dark charcoal background, monospaced numbers, green/red for moves.
# --------------------------------------------------------------------------
st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Ubuntu+Mono:wght@400;700&display=swap');
      :root {
        --bg:#0b0e14; --panel:#12161f; --border:#232b38;
        --text:#e6edf3; --muted:#7d8693;
        --green:#3fb950; --red:#f85149; --amber:#d29922; --blue:#58a6ff;
        --mono:"Ubuntu Mono","SF Mono","JetBrains Mono",ui-monospace,monospace;
        --sans:"Ubuntu Mono","SF Mono","JetBrains Mono",ui-monospace,monospace;
      }
      .stApp { background:var(--bg); color:var(--text); font-family:var(--sans); }
      header[data-testid="stHeader"] { background:transparent; }
      [data-testid="stToolbar"] { display:none; }
      .block-container { padding-top:1.2rem; padding-bottom:1rem; max-width:100%; }
      #MainMenu, footer { visibility:hidden; }

      /* dark-theme the input widgets so they match the terminal */
      .stTextInput input, .stNumberInput input { background:var(--panel) !important;
        color:var(--text) !important; border:1px solid var(--border) !important;
        font-family:var(--mono); }
      div[data-baseweb="select"] > div { background:var(--panel) !important;
        border:1px solid var(--border) !important; color:var(--text) !important; }
      .stTextInput label, .stSelectbox label, .stSlider label, .stCheckbox label {
        color:var(--muted) !important; font-size:11px !important;
        text-transform:uppercase; letter-spacing:.1em; }

      /* --- native Streamlit widgets: force them onto the theme + monospace ---
         These widgets don't read our CSS vars on their own, so without this they
         get stranded in the wrong colors in Light mode (and a proportional font).
         Everything below uses var(--...), so it flips with the Theme toggle. */

      /* every DOM-rendered control is monospace (the canvas data grid can't be
         reached by CSS at all -- the Data tab uses an HTML table instead). */
      html, body, .stApp, .stApp button, .stApp input, .stApp select,
      .stApp textarea, [data-baseweb="select"] * { font-family:var(--mono) !important; }

      /* selectbox chevron icon follows the palette */
      div[data-baseweb="select"] svg { fill:var(--muted) !important; color:var(--muted) !important; }

      /* selectbox dropdown menu (portaled to <body>) -- themed in BOTH modes */
      ul[data-baseweb="menu"] { background:var(--panel) !important;
        border:1px solid var(--border) !important; }
      ul[data-baseweb="menu"] li { color:var(--text) !important; }
      ul[data-baseweb="menu"] li:hover,
      ul[data-baseweb="menu"] li[aria-selected="true"] {
        background:var(--border) !important; color:var(--text) !important; }

      /* history slider */
      .stSlider div[data-testid="stTickBar"] { color:var(--muted) !important; }
      .stSlider div[data-testid="stThumbValue"] { color:var(--text) !important;
        background:transparent !important; }
      .stSlider [data-baseweb="slider"] > div > div { background:var(--border) !important; }
      .stSlider [data-baseweb="slider"] > div > div > div { background:var(--text) !important; }
      .stSlider [data-baseweb="slider"] [role="slider"] { background:var(--text) !important; }

      /* checkbox tick box follows the palette */
      .stCheckbox [data-baseweb="checkbox"] span:first-child { background:var(--panel) !important;
        border-color:var(--border) !important; }

      /* Chart / Data tabs */
      button[data-baseweb="tab"] { color:var(--muted) !important; }
      button[data-baseweb="tab"][aria-selected="true"] { color:var(--text) !important; }
      div[data-baseweb="tab-list"] { border-bottom:1px solid var(--border) !important; }
      div[data-baseweb="tab-highlight"], div[data-baseweb="tab-border"] {
        background:var(--amber) !important; }

      /* download buttons */
      .stDownloadButton button { background:var(--panel) !important; color:var(--text) !important;
        border:1px solid var(--border) !important; }
      .stDownloadButton button:hover { border-color:var(--muted) !important; }

      /* themed scrollbars */
      *::-webkit-scrollbar { width:10px; height:10px; }
      *::-webkit-scrollbar-track { background:var(--panel); }
      *::-webkit-scrollbar-thumb { background:var(--border); border-radius:5px; }
      *::-webkit-scrollbar-thumb:hover { background:var(--muted); }
      * { scrollbar-color:var(--border) var(--panel); }

      .panel { background:var(--panel); border:1px solid var(--border);
               border-radius:6px; padding:12px 14px; height:100%; }
      .panel-title { font-size:11px; letter-spacing:.12em; text-transform:uppercase;
                     color:var(--muted); margin-bottom:8px; }

      /* numbers: tabular so columns line up */
      .num { font-family:var(--mono); font-variant-numeric:tabular-nums; }
      .pos { color:var(--green); } .neg { color:var(--red); }
      .muted { color:var(--muted); } .accent { color:var(--amber); }

      .quote-last { font-family:var(--mono); font-size:42px; font-weight:700;
                    line-height:1.1; }
      .quote-sym  { font-size:20px; font-weight:700; letter-spacing:.05em; }
      .kv { display:flex; justify-content:space-between; font-family:var(--mono);
            font-size:14px; padding:3px 0; border-bottom:1px solid var(--border); }
      .kv .k { color:var(--muted); }

      .watch { display:flex; justify-content:space-between; align-items:center;
               padding:6px 4px; border-bottom:1px solid var(--border);
               font-family:var(--mono); font-size:13px; }
      .watch .sym { color:var(--text); font-weight:600; }

      table.pos-table { width:100%; border-collapse:collapse; font-family:var(--mono);
                        font-size:13px; }
      table.pos-table th { color:var(--muted); text-align:right; font-weight:500;
                           padding:6px 10px; border-bottom:1px solid var(--border);
                           font-size:11px; letter-spacing:.08em; text-transform:uppercase; }
      table.pos-table td { text-align:right; padding:6px 10px;
                           border-bottom:1px solid var(--border); }
      table.pos-table td.sym { text-align:left; font-weight:600; }

      .topbar { display:flex; justify-content:space-between; align-items:baseline;
                border-bottom:1px solid var(--border); padding-bottom:8px; margin-bottom:14px; }
      .topbar .brand { font-weight:700; letter-spacing:.18em; font-size:16px; }
      .topbar .brand span { color:var(--amber); }
      .badge { font-family:var(--mono); font-size:12px; color:var(--muted);
               border:1px solid var(--border); border-radius:4px; padding:2px 8px; margin-left:8px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------
# Data layer. One connector per session -- the Alpaca clients are reusable, so
# there's no reason to rebuild them on every refresh.
# --------------------------------------------------------------------------
@st.cache_resource
def get_market():
    return MarketData()


try:
    market = get_market()
except Exception as e:
    st.error(f"Couldn't connect to Alpaca: {e}")
    st.stop()

WATCHLIST = ["AAPL", "MSFT", "NVDA", "TSLA", "SPY"]
TIMEFRAMES = {"1Min": TimeFrame.Minute, "5Min": TimeFrame(5, TimeFrameUnit.Minute),
              "15Min": TimeFrame(15, TimeFrameUnit.Minute), "1Hour": TimeFrame.Hour,
              "1Day": TimeFrame.Day}
# how often new bars actually appear, per interval (seconds)
INTERVAL_SECONDS = {"1Min": 60, "5Min": 300, "15Min": 900, "1Hour": 3600, "1Day": 86400}

# Per-theme chart colors. The UI panels are themed with CSS variables (see the
# style block above + the Light override below); the Plotly chart can't read
# those CSS vars, so it takes its colors from here instead.
THEMES = {
    "Dark":  {"template": "plotly_dark",  "chart_bg": "#12161f", "font": "#e6edf3",
              "grid": "#1c2330", "up": "#3fb950", "down": "#f85149",
              "vol_up": "#244a33", "vol_down": "#4a2630", "accent": "#d29922"},
    "Light": {"template": "plotly_white", "chart_bg": "#ffffff", "font": "#1c2128",
              "grid": "#e6e9ee", "up": "#1a7f37", "down": "#cf222e",
              "vol_up": "#a7d4b4", "vol_down": "#f0b6bb", "accent": "#9a6700"},
}

# How often each live panel re-polls itself in the background (Streamlit
# fragments). The quote is the fast one you watch; the rest are gentler so we
# stay well under Alpaca's request limit. One snapshot call now returns
# quote + trade + prev-close, so a 1-second quote is only ~60 requests/min.
QUOTE_EVERY = "1s"
WATCH_EVERY = "5s"
POS_EVERY = "3s"
CANDLE_EVERY = "2s"   # only used when the "Live bar" toggle is on


# The `bucket` argument is the trick: it only changes once per bar interval, so a
# new API pull happens at the bar's cadence (e.g. every 5 min for 5-min bars) --
# not on every refresh. Live quotes don't go through here; they poll directly.
@st.cache_data(show_spinner=False)
def load_bars(symbol, days, tf_label, bucket):
    return market.bars(symbol, days=days, timeframe=TIMEFRAMES[tf_label])


# Short-lived caches for the live data. Because @st.cache_data is shared across
# Streamlit sessions, these also de-duplicate identical calls across multiple
# browser tabs -- so the request rate stays bounded (e.g. the quote can't exceed
# ~1 call/sec no matter how many tabs are open), keeping us under Alpaca's limit.
@st.cache_data(ttl=1, show_spinner=False)
def live_snapshot(symbol):
    return market.snapshot(symbol)


@st.cache_data(ttl=4, show_spinner=False)
def live_snapshots(symbols):
    return market.snapshots(list(symbols))


@st.cache_data(ttl=15, show_spinner=False)
def buying_power():
    try:
        return f"${float(market.account().buying_power):,.0f}"
    except Exception:
        return "--"


@st.cache_data(ttl=600, show_spinner=False)
def prior_close(symbol):
    """Fallback previous-session close from daily bars, used only when the
    snapshot's previous_daily_bar is missing -- keeps the day-change populated
    off-hours / for thin symbols."""
    try:
        daily = market.bars(symbol, days=7, timeframe=TimeFrame.Day)
        closes = daily["close"].tolist()
        return closes[-2] if len(closes) >= 2 else (closes[-1] if closes else None)
    except Exception:
        return None


# --- small formatting helpers ---------------------------------------------

def fmt(x, nd=2):
    return f"{x:,.{nd}f}" if x is not None else "--"


def num(x):
    """Coerce to float, or None -- never raises on a missing/odd value."""
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def sign(v):
    """Leading '+' for non-negative numbers; nothing for negative or missing."""
    return ("+" if v >= 0 else "") if v is not None else ""


def cls(change):
    """CSS class for a number based on its sign."""
    if change is None:
        return "muted"
    return "pos" if change >= 0 else "neg"


def prep_bars(symbol, days, tf_label):
    """Cached OHLCV bars, in market time, regular hours only -- the shape the
    chart and the data table both want."""
    bucket = int(time.time() // INTERVAL_SECONDS[tf_label])
    bars = load_bars(symbol, days, tf_label, bucket)
    if bars.empty:
        return bars
    bars = bars.copy()
    # Alpaca timestamps are UTC; show them in market time so the session gaps
    # line up when we hide non-trading hours below.
    if bars.index.tz is not None:
        bars.index = bars.index.tz_convert("America/New_York")
    # Keep regular trading hours only (9:30-4:00 ET). IEX includes pre/after-
    # market bars, which would otherwise show as empty bands when we collapse
    # the overnight gap. (Daily bars are left as-is.)
    if tf_label != "1Day":
        bars = bars.between_time("09:30", "16:00")
    return bars


# --------------------------------------------------------------------------
# Controls (top): symbol entry + chart settings + theme + live-candle toggle.
# (The old "Refresh" dropdown is gone -- the live panels now refresh themselves
# in the background, so there's nothing to set.)
# --------------------------------------------------------------------------
c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
symbol = c1.text_input("Ticker", value="AAPL").strip().upper()
tf_label = c2.selectbox("Interval", list(TIMEFRAMES), index=1)  # default 5Min
days = c3.slider("History (days)", 5, 60, 30)
theme = c4.selectbox("Theme", ["Dark", "Light"], index=0)
live_bar = c5.checkbox(
    "Live bar", value=False,
    help="Show a live current-price line and grow the forming candle from the "
         "latest trade (updates every ~2s). The chart tracks the most recent "
         "bars while it's on -- turn it off to pan/zoom through history.")
THEME = THEMES[theme]  # chart colors for the chosen theme

# The style block above defines the DARK theme by default. In Light mode we inject
# a second <style> that overrides just the color tokens -- a later rule with the
# same `:root` selector wins, so every var(--...) in the UI flips to the light
# palette with no other code changes. (Fonts stay the same in both themes.)
if theme == "Light":
    st.markdown(
        """
        <style>
          :root {
            --bg:#f5f6f8; --panel:#ffffff; --border:#d8dde4;
            --text:#1c2128; --muted:#6a737d;
            --green:#1a7f37; --red:#cf222e; --amber:#9a6700; --blue:#0969da;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

# --- top bar (brand / live clock / buying power) ---------------------------
# Its own 1-second fragment so the clock actually ticks (the rest of the page no
# longer reruns on a timer). Buying power is cached (15s) so it isn't an API hit
# every second.
def clock_panel():
    st.markdown(
        f"""
        <div class="topbar">
          <div class="brand">MINI<span>·</span>TERMINAL
            <span class="badge">PAPER</span>
            <span class="badge">IEX</span>
          </div>
          <div class="num muted">{datetime.now():%Y-%m-%d %H:%M:%S} &nbsp;·&nbsp;
            Buying Power <span class="accent">{buying_power()}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.fragment(run_every="1s")(clock_panel)()


# --------------------------------------------------------------------------
# Live panels. Each of these is a Streamlit *fragment*: it re-runs ONLY itself
# on its own timer (run_every=...), in the background, and repaints just its own
# output -- the rest of the page stays put. That's the "continuous refresh with
# no full-page reload" behavior.
# --------------------------------------------------------------------------

def watch_panel():
    """Market-watch list: last price + day % for the watchlist (one API call)."""
    try:
        snaps = live_snapshots(tuple(WATCHLIST))
    except Exception:
        snaps = {}
    rows = ""
    for sym in WATCHLIST:
        d = snaps.get(sym) or {}
        last, ref = d.get("last"), d.get("prev_close")
        if ref is None:
            ref = prior_close(sym)
        if last is None:
            rows += (f'<div class="watch"><span class="sym">{sym}</span>'
                     f'<span class="muted">--</span></div>')
            continue
        pct = (last - ref) / ref * 100 if (ref not in (None, 0)) else None
        rows += (
            f'<div class="watch"><span class="sym">{sym}</span>'
            f'<span class="{cls(pct)}">{fmt(last)} '
            f'<span style="font-size:11px">{sign(pct)}{fmt(pct)}%</span>'
            f'</span></div>'
        )
    st.markdown(f'<div class="panel"><div class="panel-title">Market Watch</div>{rows}</div>',
                unsafe_allow_html=True)


def quote_panel(symbol):
    """The live quote -- last/bid/ask/spread, day change, updated-at time."""
    try:
        snap = live_snapshot(symbol)
        last, ref = snap.get("last"), snap.get("prev_close")
        if ref is None:
            ref = prior_close(symbol)
        chg = (last - ref) if (ref is not None and last is not None) else None
        pct = (chg / ref * 100) if (ref not in (None, 0) and chg is not None) else None
        ts = snap.get("ts")
        ts_str = ts.strftime("%H:%M:%S") if ts else "--"
        st.markdown(
            f"""
            <div class="panel">
              <div class="panel-title">Quote</div>
              <div class="quote-sym">{symbol}</div>
              <div class="quote-last {cls(chg)}">{fmt(last)}</div>
              <div class="num {cls(chg)}" style="margin-bottom:10px;">
                {sign(chg)}{fmt(chg)} ({sign(pct)}{fmt(pct)}%)
              </div>
              <div class="kv"><span class="k">BID</span><span>{fmt(snap["bid"])}</span></div>
              <div class="kv"><span class="k">ASK</span><span>{fmt(snap["ask"])}</span></div>
              <div class="kv"><span class="k">SPREAD</span><span>{fmt(snap["spread"], 4)}</span></div>
              <div class="kv"><span class="k">LAST</span><span>{fmt(last)}</span></div>
              <div class="num muted" style="font-size:11px;margin-top:8px;">upd {ts_str}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    except Exception as e:
        st.markdown(f'<div class="panel"><div class="panel-title">Quote</div>'
                    f'<div class="neg">No quote for {symbol}.</div>'
                    f'<div class="muted" style="font-size:11px">{e}</div></div>',
                    unsafe_allow_html=True)


def positions_panel():
    """Open paper positions with live unrealized P&L."""
    try:
        positions = market.positions()
        if not positions:
            body = '<div class="muted">No open positions in the paper account.</div>'
        else:
            head = ("<tr><th class='sym' style='text-align:left'>Symbol</th><th>Qty</th>"
                    "<th>Avg Cost</th><th>Last</th><th>Mkt Value</th><th>Unreal. P&L</th><th>%</th></tr>")
            trs = ""
            for p in positions:
                # Fields can be None when a position can't be marked to market
                # (market closed) -- coerce safely so one null cell doesn't take
                # down the whole table.
                qty = num(p.qty)
                pl = num(p.unrealized_pl)
                plpc = num(p.unrealized_plpc)
                plpc = plpc * 100 if plpc is not None else None
                trs += (
                    f"<tr><td class='sym'>{p.symbol}</td>"
                    f"<td>{f'{qty:g}' if qty is not None else '--'}</td>"
                    f"<td>{fmt(num(p.avg_entry_price))}</td>"
                    f"<td>{fmt(num(p.current_price))}</td>"
                    f"<td>{fmt(num(p.market_value))}</td>"
                    f"<td class='{cls(pl)}'>{sign(pl)}{fmt(pl)}</td>"
                    f"<td class='{cls(plpc)}'>{sign(plpc)}{fmt(plpc)}%</td></tr>"
                )
            body = f"<table class='pos-table'>{head}{trs}</table>"
        st.markdown(f'<div class="panel"><div class="panel-title">Positions</div>{body}</div>',
                    unsafe_allow_html=True)
    except Exception as e:
        st.markdown(f'<div class="panel"><div class="panel-title">Positions</div>'
                    f'<div class="neg">Could not load positions: {e}</div></div>',
                    unsafe_allow_html=True)


def render_candles(symbol, days, tf_label, theme_colors, live):
    """The candlestick + volume chart. When `live` is on, the forming (last)
    candle is grown from the latest trade before drawing -- this function then
    runs inside a fragment that re-renders it every couple of seconds."""
    try:
        bars = prep_bars(symbol, days, tf_label)
        if bars.empty:
            st.markdown('<div class="panel"><div class="panel-title">Chart</div>'
                        '<div class="muted">No bars returned for this symbol/range.</div></div>',
                        unsafe_allow_html=True)
            return

        # Live: grow the forming (last) candle from the latest trade, like a real
        # terminal. close = latest trade; high/low stretch to include it.
        live_px = None
        if live and len(bars):
            try:
                live_px = float(market.last_trade(symbol))
                i = bars.index[-1]
                bars.loc[i, "close"] = live_px
                bars.loc[i, "high"] = max(float(bars.loc[i, "high"]), live_px)
                bars.loc[i, "low"] = min(float(bars.loc[i, "low"]), live_px)
            except Exception:
                live_px = None  # market closed / no trade yet -- draw bars as-is

        # color volume bars by candle direction
        vol_colors = [theme_colors["vol_up"] if c >= o else theme_colors["vol_down"]
                      for o, c in zip(bars["open"], bars["close"])]

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                            row_heights=[0.78, 0.22], vertical_spacing=0.03)
        fig.add_trace(go.Candlestick(
            x=bars.index, open=bars["open"], high=bars["high"],
            low=bars["low"], close=bars["close"],
            increasing_line_color=theme_colors["up"], decreasing_line_color=theme_colors["down"],
            name=symbol), row=1, col=1)
        fig.add_trace(go.Bar(x=bars.index, y=bars["volume"],
                             marker_color=vol_colors, name="Vol"), row=2, col=1)

        # Hide non-trading time so candles sit flush: weekends, the overnight gap,
        # AND market holidays. Holidays are detected from the data (business days
        # that have no bars -- e.g. Juneteenth), because plotly's time-based breaks
        # don't know the market calendar and would otherwise leave an empty band.
        breaks = [dict(bounds=["sat", "mon"])]
        if tf_label != "1Day":
            breaks.append(dict(bounds=[16, 9.5], pattern="hour"))
        present = set(bars.index.normalize())
        allbiz = pd.date_range(bars.index[0].normalize(), bars.index[-1].normalize(),
                               freq="B", tz=bars.index.tz)
        holidays = [d for d in allbiz if d not in present]
        if holidays:
            breaks.append(dict(values=[d.strftime("%Y-%m-%d") for d in holidays],
                               dvalue=24 * 60 * 60 * 1000))

        # Open on the most recent ~2 sessions, anchored to a real bar (not a
        # calendar date, which could land on a weekend/holiday and open onto an
        # empty gap). All `days` of data stay loaded: drag to pan, or double-click
        # / home icon for the full range.
        init_range = None
        n = None
        if tf_label != "1Day":
            per_day = max(1, round(len(bars) / max(1, len(present))))
            n = min(len(bars) - 1, per_day * 2)
            init_range = [bars.index[-(n + 1)], bars.index[-1]]

        # Scale the volume axis to the *typical* volume of the opening window
        # (95th percentile), anchored at zero. Otherwise a single auction spike
        # sets the scale and every normal bar is dwarfed.
        vol_src = bars.iloc[-(n + 1):] if init_range is not None else bars
        vmax = float(vol_src["volume"].quantile(0.95)) * 1.2
        vol_range = [0, vmax] if vmax > 0 else None

        fig.update_layout(
            template=theme_colors["template"], height=520, margin=dict(l=8, r=8, t=28, b=8),
            paper_bgcolor=theme_colors["chart_bg"], plot_bgcolor=theme_colors["chart_bg"], dragmode="pan",
            font=dict(family="Ubuntu Mono, SF Mono, monospace", size=11, color=theme_colors["font"]),
            xaxis_rangeslider_visible=False, showlegend=False,
            title=dict(text=f"{symbol}  ·  {tf_label}  ·  {days}d", x=0.01, font=dict(size=13)),
            # uirevision keeps your zoom/pan across re-renders; it only resets when
            # you change symbol / interval / history.
            uirevision=f"{symbol}|{tf_label}|{days}",
        )
        # Single-line, angled, sparse ticks so labels don't collide at the day
        # boundary (where the collapsed overnight puts 15:55 next to the next 09:30).
        fig.update_xaxes(gridcolor=theme_colors["grid"], rangebreaks=breaks, range=init_range,
                         tickangle=-30, tickformat="%b %d %H:%M", nticks=7)
        fig.update_yaxes(gridcolor=theme_colors["grid"], row=1, col=1)            # price
        fig.update_yaxes(gridcolor=theme_colors["grid"], rangemode="tozero",
                         range=vol_range, row=2, col=1)                            # volume

        # A live current-price line so the update is unmistakable at any zoom --
        # a few cents of candle movement is invisible on a multi-day chart, but a
        # full-width line that jumps with each trade reads clearly as "live".
        if live_px is not None:
            fig.add_hline(y=live_px, line_color=theme_colors["accent"], line_dash="dot",
                          line_width=1, row=1, col=1,
                          annotation_text=f" {fmt(live_px)} ",
                          annotation_position="top right",
                          annotation_font_color=theme_colors["accent"],
                          annotation_font_size=11)

        # No `key` here on purpose: with a key, Streamlit re-initialises the chart
        # on every fragment tick and throws away your pan/zoom. Without it,
        # Streamlit diffs the figure and Plotly's `uirevision` (set above) keeps
        # your view stable across the live re-renders.
        st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True})
    except Exception as e:
        st.markdown(f'<div class="panel"><div class="panel-title">Chart</div>'
                    f'<div class="neg">Error loading {symbol}: {e}</div></div>',
                    unsafe_allow_html=True)


def render_data_tab(symbol, days, tf_label):
    """The OHLCV table + Excel/CSV downloads. Rendered once (not on the live
    timer) -- the downloads always hold the official, unpatched bars."""
    try:
        bars = prep_bars(symbol, days, tf_label)
        if bars.empty:
            st.markdown('<div class="muted">No bars returned for this symbol/range.</div>',
                        unsafe_allow_html=True)
            return
        ohlcv = (bars[["open", "high", "low", "close", "volume"]]
                 .rename(columns=str.title)
                 .sort_index(ascending=False))  # newest first
        ohlcv.index.name = "Timestamp (ET)"
        # Render OHLCV as a themed HTML table (same style as the Positions table)
        # so it follows the Light/Dark theme AND stays monospace -- st.dataframe is
        # a canvas that ignores our CSS. Downloads hold the full set; on screen we
        # show the most recent rows so scrolling stays snappy on big ranges.
        CAP = 500
        shown = ohlcv.head(CAP)
        head = ("<tr><th class='sym' style='text-align:left'>Timestamp (ET)</th>"
                "<th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Volume</th></tr>")

        def vol_cell(v):
            return f"{int(v):,}" if pd.notna(v) else "--"

        trs = "".join(
            f"<tr><td class='sym'>{ts:%Y-%m-%d %H:%M}</td>"
            f"<td>{fmt(r['Open'])}</td><td>{fmt(r['High'])}</td>"
            f"<td>{fmt(r['Low'])}</td><td>{fmt(r['Close'])}</td>"
            f"<td>{vol_cell(r['Volume'])}</td></tr>"
            for ts, r in shown.iterrows())
        more = (f"<div class='muted' style='font-size:11px;margin-top:6px'>"
                f"showing newest {len(shown):,} of {len(ohlcv):,} bars · "
                f"full set in the downloads below</div>") if len(ohlcv) > CAP else ""
        st.markdown(
            f"<div style='max-height:460px;overflow:auto'>"
            f"<table class='pos-table'>{head}{trs}</table></div>{more}",
            unsafe_allow_html=True)

        # For export, drop the tz (keep the ET wall-clock time) -- Excel can't
        # store timezone-aware datetimes.
        export_df = ohlcv.copy()
        export_df.index = export_df.index.tz_localize(None)

        xls = io.BytesIO()
        with pd.ExcelWriter(xls, engine="openpyxl") as writer:
            export_df.to_excel(writer, sheet_name="OHLCV")
        d1, d2 = st.columns(2)
        d1.download_button(
            "⬇  Download Excel", xls.getvalue(),
            file_name=f"{symbol}_{tf_label}_{days}d_OHLCV.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True)
        d2.download_button(
            "⬇  Download CSV", export_df.to_csv().encode(),
            file_name=f"{symbol}_{tf_label}_{days}d_OHLCV.csv",
            mime="text/csv", use_container_width=True)
    except Exception as e:
        st.markdown(f'<div class="neg">Error loading {symbol}: {e}</div>',
                    unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Layout: watchlist | chart | quote, then a full-width positions row.
# The live panels are wrapped in st.fragment(run_every=...) at call time, so
# each one re-runs itself on its own background timer. The chart only gets a
# timer when "Live bar" is on (run_every=None means "no auto-rerun").
# --------------------------------------------------------------------------
left, center, right = st.columns([1.4, 5, 2], gap="medium")

with left:
    st.fragment(run_every=WATCH_EVERY)(watch_panel)()

with center:
    tab_chart, tab_data = st.tabs(["Chart", "Data (OHLCV)"])
    with tab_chart:
        st.fragment(run_every=(CANDLE_EVERY if live_bar else None))(render_candles)(
            symbol, days, tf_label, THEME, live_bar)
    with tab_data:
        render_data_tab(symbol, days, tf_label)

with right:
    st.fragment(run_every=QUOTE_EVERY)(quote_panel)(symbol)

st.write("")
st.fragment(run_every=POS_EVERY)(positions_panel)()
