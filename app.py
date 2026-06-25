"""
Mini Market Data Terminal -- Streamlit UI.

A compact, dark, institutional-looking terminal: type a ticker and get a live
quote, a candlestick chart of recent history, and your paper-trading positions.
The quote and positions refresh on a timer so it feels live.

    python -m streamlit run app.py

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
from streamlit_autorefresh import st_autorefresh

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
      .stTextInput label, .stSelectbox label, .stSlider label {
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
              "vol_up": "#244a33", "vol_down": "#4a2630"},
    "Light": {"template": "plotly_white", "chart_bg": "#ffffff", "font": "#1c2128",
              "grid": "#e6e9ee", "up": "#1a7f37", "down": "#cf222e",
              "vol_up": "#a7d4b4", "vol_down": "#f0b6bb"},
}


# The `bucket` argument is the trick: it only changes once per bar interval, so a
# new API pull happens at the bar's cadence (e.g. every 5 min for 5-min bars) --
# not on every page refresh. The fast refresh is reserved for the live quote.
@st.cache_data(show_spinner=False)
def load_bars(symbol, days, tf_label, bucket):
    return market.bars(symbol, days=days, timeframe=TIMEFRAMES[tf_label])


@st.cache_data(ttl=300, show_spinner=False)
def prior_close(symbol):
    """Previous session's close, used for the day's change/percent."""
    daily = market.bars(symbol, days=7, timeframe=TimeFrame.Day)
    closes = daily["close"].tolist()
    # last row may be today's still-forming bar, so step back one when we can
    return closes[-2] if len(closes) >= 2 else closes[-1]


# --- small formatting helpers ---------------------------------------------

def fmt(x, nd=2):
    return f"{x:,.{nd}f}" if x is not None else "--"


def cls(change):
    """CSS class for a number based on its sign."""
    if change is None:
        return "muted"
    return "pos" if change >= 0 else "neg"


# --------------------------------------------------------------------------
# Controls (top): symbol entry + chart settings + refresh cadence.
# --------------------------------------------------------------------------
c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
symbol = c1.text_input("Ticker", value="AAPL").strip().upper()
tf_label = c2.selectbox("Interval", list(TIMEFRAMES), index=1)  # default 5Min
days = c3.slider("History (days)", 5, 60, 30)
every = c4.selectbox("Refresh", ["Off", "5s", "10s", "30s"], index=2)
theme = c5.selectbox("Theme", ["Dark", "Light"], index=0)
THEME = THEMES[theme]  # chart colors for the chosen theme

# st_autorefresh just reruns the whole script on a timer; that's enough to
# repoll the live quote and positions. Off = no timer.
if every != "Off":
    st_autorefresh(interval=int(every.rstrip("s")) * 1000, key="tick")

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

# --- top bar (brand / clock / buying power) --------------------------------
try:
    acct = market.account()
    bp = f"${float(acct.buying_power):,.0f}"
except Exception:
    bp = "--"

st.markdown(
    f"""
    <div class="topbar">
      <div class="brand">MINI<span>·</span>TERMINAL
        <span class="badge">PAPER</span>
        <span class="badge">IEX</span>
      </div>
      <div class="num muted">{datetime.now():%Y-%m-%d %H:%M:%S} &nbsp;·&nbsp;
        Buying Power <span class="accent">{bp}</span></div>
    </div>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------
# Main grid: watchlist | chart | quote panel
# --------------------------------------------------------------------------
left, center, right = st.columns([1.4, 5, 2], gap="medium")

# ---- left: market watch ----
with left:
    rows = ""
    for sym in WATCHLIST:
        try:
            last = market.last_trade(sym)
            ref = prior_close(sym)
            pct = (last - ref) / ref * 100 if ref else None
            rows += (
                f'<div class="watch"><span class="sym">{sym}</span>'
                f'<span class="{cls(pct)}">{fmt(last)} '
                f'<span style="font-size:11px">{("+" if (pct or 0)>=0 else "")}{fmt(pct)}%</span>'
                f'</span></div>'
            )
        except Exception:
            rows += f'<div class="watch"><span class="sym">{sym}</span><span class="muted">--</span></div>'
    st.markdown(f'<div class="panel"><div class="panel-title">Market Watch</div>{rows}</div>',
                unsafe_allow_html=True)

# ---- center: candlestick + volume ----
with center:
    try:
        # bucket changes once per bar interval -> chart data refreshes at the
        # bar cadence, while the quote panel below refreshes every page tick.
        bucket = int(time.time() // INTERVAL_SECONDS[tf_label])
        bars = load_bars(symbol, days, tf_label, bucket)
        if bars.empty:
            st.markdown('<div class="panel"><div class="panel-title">Chart</div>'
                        '<div class="muted">No bars returned for this symbol/range.</div></div>',
                        unsafe_allow_html=True)
        else:
            # Alpaca timestamps are UTC; show them in market time so the session
            # gaps line up when we hide non-trading hours below.
            bars = bars.copy()
            if bars.index.tz is not None:
                bars.index = bars.index.tz_convert("America/New_York")

            # Keep regular trading hours only (9:30-4:00 ET). IEX includes
            # pre/after-market bars, which would otherwise show as empty bands
            # when we collapse the overnight gap. (Daily bars are left as-is.)
            if tf_label != "1Day":
                bars = bars.between_time("09:30", "16:00")

            tab_chart, tab_data = st.tabs(["Chart", "Data (OHLCV)"])

            # ---- Chart tab ----
            with tab_chart:
                # color volume bars by candle direction
                vol_colors = [THEME["vol_up"] if c >= o else THEME["vol_down"]
                              for o, c in zip(bars["open"], bars["close"])]

                fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                    row_heights=[0.78, 0.22], vertical_spacing=0.03)
                fig.add_trace(go.Candlestick(
                    x=bars.index, open=bars["open"], high=bars["high"],
                    low=bars["low"], close=bars["close"],
                    increasing_line_color=THEME["up"], decreasing_line_color=THEME["down"],
                    name=symbol), row=1, col=1)
                fig.add_trace(go.Bar(x=bars.index, y=bars["volume"],
                                     marker_color=vol_colors, name="Vol"), row=2, col=1)

                # Hide non-trading time so candles sit flush: weekends, the
                # overnight gap, AND market holidays. Holidays are detected from
                # the data (business days that have no bars -- e.g. Juneteenth),
                # because plotly's time-based breaks don't know the market calendar
                # and would otherwise leave an empty band that looks like the data
                # just stopped.
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
                # calendar date, which could land on a weekend/holiday and open onto
                # an empty gap). All `days` of data stay loaded: drag to pan, or
                # double-click / home icon for the full range.
                init_range = None
                if tf_label != "1Day":
                    per_day = max(1, round(len(bars) / max(1, len(present))))
                    n = min(len(bars) - 1, per_day * 2)
                    init_range = [bars.index[-(n + 1)], bars.index[-1]]

                # Scale the volume axis to the *typical* volume of the opening
                # window (95th percentile), anchored at zero. Otherwise a single
                # auction spike sets the scale and every normal bar is dwarfed --
                # and the axis floor drifts above zero so low bars vanish entirely.
                vol_src = bars.iloc[-(n + 1):] if init_range is not None else bars
                vmax = float(vol_src["volume"].quantile(0.95)) * 1.2
                vol_range = [0, vmax] if vmax > 0 else None

                fig.update_layout(
                    template=THEME["template"], height=520, margin=dict(l=8, r=8, t=28, b=8),
                    paper_bgcolor=THEME["chart_bg"], plot_bgcolor=THEME["chart_bg"], dragmode="pan",
                    font=dict(family="Ubuntu Mono, SF Mono, monospace", size=11, color=THEME["font"]),
                    xaxis_rangeslider_visible=False, showlegend=False,
                    title=dict(text=f"{symbol}  ·  {tf_label}  ·  {days}d", x=0.01, font=dict(size=13)),
                    # uirevision keeps your zoom/pan across auto-refreshes; it only
                    # resets when you change symbol / interval / history.
                    uirevision=f"{symbol}|{tf_label}|{days}",
                )
                # Single-line, angled, sparse ticks so labels don't collide at the
                # day boundary (where the collapsed overnight puts 15:55 next to
                # the next 09:30).
                fig.update_xaxes(gridcolor=THEME["grid"], rangebreaks=breaks, range=init_range,
                                 tickangle=-30, tickformat="%b %d %H:%M", nticks=7)
                fig.update_yaxes(gridcolor=THEME["grid"], row=1, col=1)            # price
                fig.update_yaxes(gridcolor=THEME["grid"], rangemode="tozero",
                                 range=vol_range, row=2, col=1)                # volume
                # scrollZoom = mouse-wheel zoom. Combined with uirevision above,
                # this keeps your view stable across the auto-refresh reruns.
                st.plotly_chart(fig, use_container_width=True,
                                config={"scrollZoom": True})

            # ---- Data tab: OHLCV spreadsheet + downloads ----
            with tab_data:
                ohlcv = (bars[["open", "high", "low", "close", "volume"]]
                         .rename(columns=str.title)
                         .sort_index(ascending=False))  # newest first
                ohlcv.index.name = "Timestamp (ET)"
                # Render OHLCV as a themed HTML table (same style as the Positions
                # table) so it follows the Light/Dark theme AND stays monospace --
                # st.dataframe is a canvas that ignores our CSS entirely. The
                # downloads below always hold the full set; on screen we show the
                # most recent rows so scrolling stays snappy on big ranges.
                CAP = 500
                shown = ohlcv.head(CAP)
                head = ("<tr><th class='sym' style='text-align:left'>Timestamp (ET)</th>"
                        "<th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Volume</th></tr>")
                trs = "".join(
                    f"<tr><td class='sym'>{ts:%Y-%m-%d %H:%M}</td>"
                    f"<td>{fmt(r['Open'])}</td><td>{fmt(r['High'])}</td>"
                    f"<td>{fmt(r['Low'])}</td><td>{fmt(r['Close'])}</td>"
                    f"<td>{int(r['Volume']):,}</td></tr>"
                    for ts, r in shown.iterrows())
                more = (f"<div class='muted' style='font-size:11px;margin-top:6px'>"
                        f"showing newest {len(shown):,} of {len(ohlcv):,} bars · "
                        f"full set in the downloads below</div>") if len(ohlcv) > CAP else ""
                st.markdown(
                    f"<div style='max-height:460px;overflow:auto'>"
                    f"<table class='pos-table'>{head}{trs}</table></div>{more}",
                    unsafe_allow_html=True)

                # For export, drop the tz (keep the ET wall-clock time) -- Excel
                # can't store timezone-aware datetimes.
                export_df = ohlcv.copy()
                export_df.index = export_df.index.tz_localize(None)

                # one-click downloads
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
        st.markdown(f'<div class="panel"><div class="panel-title">Chart</div>'
                    f'<div class="neg">Error loading {symbol}: {e}</div></div>',
                    unsafe_allow_html=True)

# ---- right: live quote panel ----
with right:
    try:
        snap = market.snapshot(symbol)
        ref = prior_close(symbol)
        chg = (snap["last"] - ref) if ref else None
        pct = (chg / ref * 100) if (ref and chg is not None) else None
        st.markdown(
            f"""
            <div class="panel">
              <div class="panel-title">Quote</div>
              <div class="quote-sym">{symbol}</div>
              <div class="quote-last {cls(chg)}">{fmt(snap["last"])}</div>
              <div class="num {cls(chg)}" style="margin-bottom:10px;">
                {("+" if (chg or 0)>=0 else "")}{fmt(chg)} ({("+" if (pct or 0)>=0 else "")}{fmt(pct)}%)
              </div>
              <div class="kv"><span class="k">BID</span><span>{fmt(snap["bid"])}</span></div>
              <div class="kv"><span class="k">ASK</span><span>{fmt(snap["ask"])}</span></div>
              <div class="kv"><span class="k">SPREAD</span><span>{fmt(snap["spread"], 4)}</span></div>
              <div class="kv"><span class="k">LAST</span><span>{fmt(snap["last"])}</span></div>
              <div class="num muted" style="font-size:11px;margin-top:8px;">
                upd {snap["ts"]:%H:%M:%S}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    except Exception as e:
        st.markdown(f'<div class="panel"><div class="panel-title">Quote</div>'
                    f'<div class="neg">No quote for {symbol}.</div>'
                    f'<div class="muted" style="font-size:11px">{e}</div></div>',
                    unsafe_allow_html=True)

# --------------------------------------------------------------------------
# Bottom: open positions from the paper account.
# --------------------------------------------------------------------------
st.write("")
try:
    positions = market.positions()
    if not positions:
        body = '<div class="muted">No open positions in the paper account.</div>'
    else:
        head = ("<tr><th class='sym' style='text-align:left'>Symbol</th><th>Qty</th>"
                "<th>Avg Cost</th><th>Last</th><th>Mkt Value</th><th>Unreal. P&L</th><th>%</th></tr>")
        trs = ""
        for p in positions:
            pl = float(p.unrealized_pl)
            plpc = float(p.unrealized_plpc) * 100
            trs += (
                f"<tr><td class='sym'>{p.symbol}</td>"
                f"<td>{float(p.qty):g}</td>"
                f"<td>{fmt(float(p.avg_entry_price))}</td>"
                f"<td>{fmt(float(p.current_price))}</td>"
                f"<td>{fmt(float(p.market_value))}</td>"
                f"<td class='{cls(pl)}'>{('+' if pl>=0 else '')}{fmt(pl)}</td>"
                f"<td class='{cls(plpc)}'>{('+' if plpc>=0 else '')}{fmt(plpc)}%</td></tr>"
            )
        body = f"<table class='pos-table'>{head}{trs}</table>"
    st.markdown(f'<div class="panel"><div class="panel-title">Positions</div>{body}</div>',
                unsafe_allow_html=True)
except Exception as e:
    st.markdown(f'<div class="panel"><div class="panel-title">Positions</div>'
                f'<div class="neg">Could not load positions: {e}</div></div>',
                unsafe_allow_html=True)
