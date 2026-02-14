import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta, timezone
from streamlit_lightweight_charts import renderLightweightCharts

# ── BOMB CODE LOGIC ────────────────────────────────────────────────
HOUR_VALUES = {
    0:12,1:1,2:2,3:3,4:4,5:5,6:6,7:7,8:8,9:9,10:10,11:11,
    12:12,13:1,14:2,15:3,16:4,17:5,18:6,19:7,20:8,21:9,22:10,23:11
}

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

# ── Data fetch ─────────────────────────────────────────────────────
symbol = 'BTC-USD'

@st.cache_data(ttl=60, show_spinner=False)
def get_btc_data():
    with st.status("Fetching BTC 1-minute data from yfinance...", expanded=True) as status:
        try:
            status.update(label="Downloading...", state="running")
            df = yf.download(symbol, period='2d', interval='1m', progress=False)
            if df.empty:
                status.update(label="No data returned from yfinance", state="error")
                return pd.DataFrame()
            df = df[['Open','High','Low','Close','Volume']].rename(columns=str.lower)
            df.index.name = 'timestamp'
            status.update(label=f"Success — {len(df)} candles loaded", state="complete", expanded=False)
            return df.tail(600)
        except Exception as e:
            status.update(label=f"Fetch error: {str(e)[:120]}", state="error")
            return pd.DataFrame()

# ── Signal logic ───────────────────────────────────────────────────
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

# ── TradingView Lightweight Chart ──────────────────────────────────
def make_tradingview_chart(df):
    if df.empty:
        st.error("No data available for chart")
        return

    # Prepare data format for Lightweight Charts
    chart_data = df.reset_index().copy()
    chart_data['time'] = chart_data['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
    chart_data = chart_data[['time', 'open', 'high', 'low', 'close', 'volume']]
    chart_data = chart_data.rename(columns={'volume': 'value'})

    # Candlestick series
    candlestick = {
        "type": "Candlestick",
        "data": chart_data[['time', 'open', 'high', 'low', 'close']].to_dict(orient='records'),
        "options": {
            "upColor": "#00ff9d",
            "downColor": "#ff3366",
            "borderVisible": False,
            "wickUpColor": "#00ff9d",
            "wickDownColor": "#ff3366"
        }
    }

    # Volume bars (optional - comment out if unwanted)
    volume = {
        "type": "Histogram",
        "data": chart_data[['time', 'value']].to_dict(orient='records'),
        "options": {
            "color": "#26a69a",
            "priceFormat": {"type": "volume"},
            "priceScaleId": "",
            "scaleMargins": {"top": 0.82, "bottom": 0}
        }
    }

    # Markers for PH signals (only recent ones to avoid clutter)
    markers = []
    now = datetime.now(timezone.utc)
    recent_start = now - timedelta(hours=24)
    recent_df = chart_data[pd.to_datetime(chart_data['time']) >= recent_start]

    for _, row in recent_df.iterrows():
        ts_dt = pd.to_datetime(row['time'])
        h_info = get_signal_info(ts_dt.to_pydatetime())

        if h_info['ht']:
            markers.append({
                "time": row['time'],
                "position": "aboveBar",
                "color": "#ffaa00",
                "shape": "arrowDown",
                "text": h_info['ht']
            })

        if h_info['dt']:
            markers.append({
                "time": row['time'],
                "position": "belowBar",
                "color": "#00ccff",
                "shape": "arrowUp",
                "text": h_info['dt']
            })

    # Current signal as prominent marker
    info = get_signal_info(now)
    current_markers = []
    if info['signal']:
        last_time = chart_data['time'].iloc[-1]
        color = "#00ff00" if "BUY" in info['signal'] else "#ff00ff"
        current_markers = [{
            "time": last_time,
            "position": "inBar",
            "color": color,
            "shape": "circle",
            "text": info['signal'],
            "size": 2
        }]

    # Full chart configuration
    chart_config = [{
        "chart": {
            "layout": {
                "background": {"type": "solid", "color": "#0e1117"},
                "textColor": "#d1d4dc"
            },
            "grid": {
                "vertLines": {"color": "#2a2e39"},
                "horzLines": {"color": "#2a2e39"}
            },
            "rightPriceScale": {"borderColor": "#2a2e39"},
            "timeScale": {"borderColor": "#2a2e39", "timeVisible": True, "secondsVisible": False},
            "width": 1000,
            "height": 700
        },
        "series": [candlestick, volume],
        "markers": markers + current_markers
    }]

    renderLightweightCharts(chart_config, key="btc_bombcode_tradingview")

# ── Main App ───────────────────────────────────────────────────────
st.title("BTC Bombcode Live Monitor – TradingView Style")

data = get_btc_data()

if not data.empty:
    make_tradingview_chart(data)

    now = datetime.now(timezone.utc)
    info = get_signal_info(now)
    txt = f"**Day classification**: {info['cls']}   |   **PH**: {info['ph']}"
    if info['signal']:
        txt += f"   →   {info['signal']}"
    st.markdown(txt)

    st.caption(
        f"Updated: {now.strftime('%H:%M:%S UTC')} | "
        "Source: yfinance • Data refreshes ~every 60s • "
        "Zoom, pan & hover like real TradingView"
    )
else:
    st.info("Waiting for data... First load can take 30–90 seconds.")
