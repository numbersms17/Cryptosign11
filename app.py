import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
import time
from datetime import datetime, timedelta, timezone

# ── BOMB CODE LOGIC (unchanged) ────────────────────────────────────
HOUR_VALUES = {0:12,1:1,2:2,3:3,4:4,5:5,6:6,7:7,8:8,9:9,10:10,11:11,
               12:12,13:1,14:2,15:3,16:4,17:5,18:6,19:7,20:8,21:9,22:10,23:11}

HIGH_PH = {3,6,9}
DIP_PH  = {7,11}

def reduce(n):
    while n > 9 and n not in {11,22}:
        n = sum(int(c) for c in str(n))
    return n

def bombcode_day(d):     return reduce(d)
def bombcode_full(m,d,y): return reduce(m + d + y)

def get_pd(ts):
    base = ts.replace(hour=18, minute=15)
    if ts.hour < 18 or (ts.hour == 18 and ts.minute < 15):
        base -= timedelta(days=1)
    py = reduce(3 + 1 + base.year)
    pm = reduce(py + base.month)
    return reduce(pm + base.day)

def get_ph(h, pd):
    ph = pd + HOUR_VALUES[h]
    return ph if ph in {11,22} else reduce(ph)

def fmt(h): return f"{h%12 or 12}{'am' if h<12 else 'pm'}"

def classify(day_bc, full_bc):
    if day_bc in {3,5,6,7,8,9}:
        return "High" if day_bc in {3,7,5,9} else "Low"
    return "High" if full_bc in {3,7,5,9} else "Low" if full_bc in {6,8} else "None"

# ── yfinance only (reliable) ───────────────────────────────────────
symbol = 'BTC-USD'

# Cache data fetch with TTL ~60s
@st.cache_data(ttl=60, show_spinner="Fetching fresh BTC data...")
def get_btc_data():
    try:
        print("Fetching BTC data from yfinance...")
        df = yf.download('BTC-USD', period='2d', interval='1m', progress=False)
        if df.empty:
            print("yfinance empty")
            return pd.DataFrame()
        df = df[['Open','High','Low','Close','Volume']].rename(columns=str.lower)
        df.index.name = 'timestamp'
        print(f"yfinance got {len(df)} rows")
        return df.tail(400)
    except Exception as e:
        print(f"Fetch fail: {str(e)[:150]}")
        return pd.DataFrame()

# ── Signal & Chart functions (unchanged, but now use now=UTC) ──────
def get_signal_info(now):
    pd_val = get_pd(now)
    ph = get_ph(now.hour, pd_val)
    ht = {3:'H1',6:'H2',9:'H3'}.get(ph, '')
    dt = {7:'D1',11:'D2'}.get(ph, '')
    bc_d = bombcode_day(now.day)
    bc_f = bombcode_full(now.month, now.day, now.year)
    cls = classify(bc_d, bc_f)
    signal = ""
    if cls == "Low" and ph in DIP_PH and dt:
        signal = f"**BUY** at {fmt(now.hour)} ({dt})"
    elif cls == "High" and ph in HIGH_PH and ht:
        signal = f"**SHORT** at {fmt(now.hour)} ({ht})"
    return {'cls':cls, 'ph':ph, 'ht':ht, 'dt':dt, 'signal':signal}

def make_chart(df, info):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index, open=df.open, high=df.high, low=df.low, close=df.close,
        name=symbol, increasing_line_color='lime', decreasing_line_color='red'
    ))

    now_naive = datetime.now(timezone.utc)
    today_start = now_naive.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start = pd.to_datetime(today_start)

    today_df = df[df.index >= today_start]

    for ts in today_df.index:
        h_info = get_signal_info(ts.to_pydatetime())
        if h_info['ht']:
            fig.add_vline(x=ts, line_dash="dot", line_color="orange", opacity=0.5)
            fig.add_annotation(x=ts, y=df.loc[ts,'high']*1.003, text=h_info['ht'],
                               showarrow=True, arrowhead=1, ax=20, ay=-30, font_color="orange")
        if h_info['dt']:
            fig.add_vline(x=ts, line_dash="dot", line_color="cyan", opacity=0.5)
            fig.add_annotation(x=ts, y=df.loc[ts,'low']*0.997, text=h_info['dt'],
                               showarrow=True, arrowhead=1, ax=-20, ay=30, font_color="cyan")

    if info['signal']:
        fig.add_annotation(
            x=df.index[-1], y=df.close.iloc[-1], text=info['signal'],
            showarrow=True, arrowhead=2, ax=50, ay=-80,
            font=dict(size=16, color="yellow" if "BUY" in info['signal'] else "magenta"),
            bgcolor="rgba(0,0,0,0.7)"
        )

    fig.update_layout(
        title=f"{symbol} Live – {info['cls']} day | PH = {info['ph']}",
        xaxis_rangeslider_visible=False,
        height=650,
        template="plotly_dark"
    )
    return fig

# ── Main UI ─────────────────────────────────────────────────────────
st.title("BTC Bombcode Live Monitor")

data = get_btc_data()  # auto-refreshes every ~60s thanks to ttl

if not data.empty:
    now = datetime.now(timezone.utc)
    info = get_signal_info(now)
    fig = make_chart(data, info)
    st.plotly_chart(fig, use_container_width=True)

    txt = f"**Day**: {info['cls']}   |   **PH**: {info['ph']}"
    if info['signal']:
        txt += f"   →   {info['signal']}"
    st.markdown(txt)

    st.caption(f"Updated: {now.strftime('%H:%M:%S UTC')} | yfinance • Data auto-refreshes ~every 60s")
else:
    st.info("Loading BTC data... (first load may take 30–90s)")
    st.caption("If stuck >2 min: Check logs for 'Fetch fail' messages. Reboot app if needed.")

st.caption("No threads = no drama • Refresh page manually if signals feel stale")
