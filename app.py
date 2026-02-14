import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go
import yfinance as yf
import time
import threading
from datetime import datetime, timedelta

# ── BOMB CODE LOGIC ────────────────────────────────────────────────
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

# ── Exchange fallback ───────────────────────────────────────────────
@st.cache_resource
def get_exchange():
    for name, factory in [
        ("bybit",     ccxt.bybit),
        ("gateio",    ccxt.gateio),
        ("binanceus", ccxt.binanceus),
        ("okx",       ccxt.okx),
    ]:
        try:
            ex = factory({'enableRateLimit': True})
            ex.fetch_ohlcv('BTC/USDT', '1m', limit=1)
            st.write(f"Connected to **{name}**")
            return ex, 'BTC/USDT'
        except:
            pass
    st.warning("All CCXT failed → using yfinance BTC-USD")
    return None, 'BTC-USD'

exchange, symbol = get_exchange()

# Data
if 'df' not in st.session_state:
    st.session_state.df = pd.DataFrame(
        columns=['timestamp','open','high','low','close','volume']
    ).set_index('timestamp')

# ── Fetch data ──────────────────────────────────────────────────────
def fetch_data():
    if exchange is None:
        df = yf.download('BTC-USD', period='2d', interval='1m')
        df = df[['Open','High','Low','Close','Volume']].rename(columns=str.lower)
        df.index.name = 'timestamp'
        return df.tail(400)
    else:
        since = int((datetime.utcnow() - timedelta(hours=8)).timestamp() * 1000)
        ohlcv = exchange.fetch_ohlcv(symbol, '1m', since=since, limit=400)
        df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df

# ── Signal ──────────────────────────────────────────────────────────
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

# ── Plot ────────────────────────────────────────────────────────────
def make_chart(df, info):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index, open=df.open, high=df.high, low=df.low, close=df.close,
        name=symbol, increasing_line_color='lime', decreasing_line_color='red'
    ))

    now_naive = datetime.utcnow()
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

# ── UI ──────────────────────────────────────────────────────────────
st.title("BTC Bombcode Live Monitor")

chart_placeholder = st.empty()
status_placeholder = st.empty()
update_placeholder = st.empty()

# Background updater
def updater():
    while True:
        try:
            new_df = fetch_data()
            if not st.session_state.df.empty:
                last_ts = st.session_state.df.index.max()
                st.session_state.df = pd.concat([
                    st.session_state.df,
                    new_df[new_df.index > last_ts]
                ])
            else:
                st.session_state.df = new_df
            time.sleep(60)  # ↑ increased to 60s to avoid rate limits on free deploy
        except Exception as e:
            st.error(f"Fetch error: {str(e)[:100]}…")
            time.sleep(300)

if 'updater_running' not in st.session_state:
    st.session_state.updater_running = True
    threading.Thread(target=updater, daemon=True).start()

# Main loop (Streamlit reruns on interaction, but thread keeps data fresh)
if not st.session_state.df.empty:
    now = datetime.utcnow()
    info = get_signal_info(now)
    fig = make_chart(st.session_state.df.tail(300), info)
    chart_placeholder.plotly_chart(fig, use_container_width=True)

    txt = f"**Day**: {info['cls']}   |   **PH**: {info['ph']}"
    if info['signal']:
        txt += f"   →   {info['signal']}"
    status_placeholder.markdown(txt)

    source = 'yfinance' if exchange is None else exchange.id
    update_placeholder.caption(f"Updated: {now.strftime('%H:%M:%S UTC')} | {source}")
else:
    st.info("Loading BTC data... (may take a minute)")

st.caption("Refresh page to update signals • Data refreshes every ~60s in background")
