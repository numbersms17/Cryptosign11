import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone

# Debug yfinance version
st.write(f"yfinance version: {yf.__version__}")

# ── BOMB CODE LOGIC ────────────────────────────────────────────────
def reduce(n):
    while n > 9 and n not in {11, 22}:
        n = sum(int(c) for c in str(n))
    return n

def bombcode_day(d):
    return reduce(d)

def bombcode_full(m, d, y):
    return reduce(m + d + y)

def classify(day_bc, full_bc):
    if day_bc in {3, 5, 6, 7, 8, 9}:
        return "High" if day_bc in {3, 7, 5, 9} else "Low"
    return "High" if full_bc in {3, 7, 5, 9} else "Low" if full_bc in {6, 8} else "None"

# ── Current day ────────────────────────────────────────────────────
def get_current_info(now):
    bc_d = bombcode_day(now.day)
    bc_f = bombcode_full(now.month, now.day, now.year)
    cls = classify(bc_d, bc_f)
    return {
        'cls': cls,
        'day_bc': bc_d,
        'full_bc': bc_f,
        'signal': f"**{cls.upper()} day** (day_bc={bc_d} | full_bc={bc_f})"
    }

# ── Backtest data load ─────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_backtest():
    try:
        st.write("Trying to download BTC-USD daily from yfinance...")
        df = yf.download('BTC-USD', start='2015-01-01', progress=False)
        if df.empty:
            st.error("yfinance returned empty DataFrame.")
            return None
        st.write(f"Downloaded {len(df)} days successfully.")
        df = df[['Open', 'Close']].copy()
        df['Return'] = (df['Close'] / df['Open'] - 1) * 100

        df['day_bc'] = df.index.day.map(bombcode_day)
        df['full_bc'] = df.index.map(lambda dt: bombcode_full(dt.month, dt.day, dt.year))
        df['cls'] = df.apply(lambda r: classify(r['day_bc'], r['full_bc']), axis=1)
        return df
    except Exception as e:
        st.error(f"yfinance download crashed: {str(e)}")
        st.info("Likely websockets issue — check requirements.txt pin to yfinance==0.2.37 and Python 3.10/3.11 in app settings.")
        return None

# ── Stats ──────────────────────────────────────────────────────────
def compute_stats(df):
    if df is None:
        return None, None, None, None

    by_cls = df.groupby('cls')['Return'].agg(
        Days='count',
        Avg_Return='mean',
        Median='median',
        Win_Rate=lambda x: (x > 0).mean() * 100,
        Volatility='std'
    ).round(2)

    combos = df.groupby(['cls', 'day_bc', 'full_bc'])['Return'].agg(
        Days='count',
        Avg_Return='mean',
        Median='median',
        Win_Rate=lambda x: (x > 0).mean() * 100,
        Volatility='std'
    ).round(2)

    top_combos = combos[combos['Days'] >= 30].sort_values('Avg_Return', ascending=False).head(15)

    day_bc_only = df.groupby('day_bc')['Return'].mean().sort_values(ascending=False).round(2)
    full_bc_only = df.groupby('full_bc')['Return'].mean().sort_values(ascending=False).round(2)

    return by_cls, top_combos, day_bc_only, full_bc_only

# ── Main ───────────────────────────────────────────────────────────
st.title("BTC Bombcode Analyzer")

now = datetime.now(timezone.utc)
info = get_current_info(now)

st.subheader("Current Day Status")
st.markdown(f"""
**Classification**: {info['cls']}  
**day_bc**: {info['day_bc']}  
**full_bc**: {info['full_bc']}  
{info['signal']}
""")
st.caption(f"UTC: {now.strftime('%Y-%m-%d %H:%M:%S')}")

st.divider()

st.subheader("Historical Backtest (2015–now daily returns)")

df = load_backtest()

if df is not None:
    by_cls, top_combos, day_bc_only, full_bc_only = compute_stats(df)

    st.markdown("### By Classification (High/Low/None)")
    st.dataframe(by_cls)

    st.markdown("### Top day_bc + full_bc Combos (min 30 days)")
    st.dataframe(top_combos)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### By day_bc")
        st.dataframe(day_bc_only.to_frame("Avg Return %"))

    with col2:
        st.markdown("### By full_bc")
        st.dataframe(full_bc_only.to_frame("Avg Return %"))

    st.success("Backtest complete — check if 'Low' or specific combos show edge!")
else:
    st.warning("No data loaded. Fix yfinance as above and reboot app.")

st.caption("Uses yfinance daily download • Pin yfinance==0.2.37 in requirements.txt")
