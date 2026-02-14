import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime, timezone

# Debug versions
st.write(f"pandas version: {pd.__version__}")
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

# ── Current day signal ─────────────────────────────────────────────
def get_current_info(now):
    bc_d = bombcode_day(now.day)
    bc_f = bombcode_full(now.month, now.day, now.year)
    if bc_d in {3, 5, 6, 7, 8, 9}:
        cls = "High" if bc_d in {3, 7, 5, 9} else "Low"
    else:
        if bc_f in {3, 7, 5, 9}:
            cls = "High"
        elif bc_f in {6, 8}:
            cls = "Low"
        else:
            cls = "None"
    return {
        'cls': cls,
        'day_bc': bc_d,
        'full_bc': bc_f,
        'signal': f"**{cls.upper()} day** (day_bc={bc_d} | full_bc={bc_f})"
    }

# ── Historical backtest load ───────────────────────────────────────
@st.cache_data(ttl=3600 * 6)  # cache 6 hours
def load_backtest_data():
    try:
        st.write("Downloading BTC-USD daily data from yfinance (2015–present)...")
        df = yf.download('BTC-USD', start='2015-01-01', progress=False)
        if df.empty:
            st.error("yfinance returned empty DataFrame.")
            return None
        
        st.write(f"Downloaded {len(df)} days successfully.")
        
        df = df[['Open', 'Close']].copy()
        df['Return'] = (df['Close'] / df['Open'] - 1) * 100
        
        # Vectorized bombcode calculation
        df['day_bc'] = df.index.day.map(bombcode_day)
        df['full_bc'] = df.index.map(lambda dt: bombcode_full(dt.month, dt.day, dt.year))
        
        # Drop any rows with NaN in bc columns (very rare)
        df = df.dropna(subset=['day_bc', 'full_bc'])
        
        # Vectorized classification using np.select (avoids apply + lambda hashing issues)
        conditions = [
            (df['day_bc'].isin([3, 5, 6, 7, 8, 9])) & (df['day_bc'].isin([3, 7, 5, 9])),
            (df['day_bc'].isin([3, 5, 6, 7, 8, 9])) & (~df['day_bc'].isin([3, 7, 5, 9])),
            df['full_bc'].isin([3, 7, 5, 9]),
            df['full_bc'].isin([6, 8])
        ]
        choices = ['High', 'Low', 'High', 'Low']
        df['cls'] = np.select(conditions, choices, default='None')
        
        st.write("Classification completed successfully.")
        return df
    except Exception as e:
        st.error(f"Error during data load or processing: {str(e)}")
        st.info("If error persists, try rebooting app or changing Python version in Streamlit settings to 3.10/3.11.")
        return None

# ── Compute statistics ─────────────────────────────────────────────
def compute_statistics(df):
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

    top_combos = combos[combos['Days'] >= 30].sort_values('Avg_Return', ascending=False).head(20)

    day_bc_only = df.groupby('day_bc')['Return'].mean().sort_values(ascending=False).round(2)
    full_bc_only = df.groupby('full_bc')['Return'].mean().sort_values(ascending=False).round(2)

    return by_cls, top_combos, day_bc_only, full_bc_only

# ── Main App ───────────────────────────────────────────────────────
st.title("BTC Bombcode Analyzer – Backtest Edition")

now = datetime.now(timezone.utc)
info = get_current_info(now)

st.subheader("Current Day Classification")
st.markdown(f"""
**Classification**: {info['cls']}  
**day_bc**: {info['day_bc']}  
**full_bc**: {info['full_bc']}  
{info['signal']}
""")
st.caption(f"Updated: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")

st.divider()

st.subheader("Historical Backtest (Daily Open → Close Returns, 2015–present)")

df = load_backtest_data()

if df is not None:
    by_cls, top_combos, day_bc_only, full_bc_only = compute_statistics(df)

    st.markdown("### Overall by Classification")
    st.dataframe(by_cls)

    st.markdown("### Top Combinations (day_bc + full_bc) – min 30 days")
    st.dataframe(top_combos)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Average Return by day_bc")
        st.dataframe(day_bc_only.to_frame(name="Avg Return %"))

    with col2:
        st.markdown("### Average Return by full_bc")
        st.dataframe(full_bc_only.to_frame(name="Avg Return %"))

    st.success("Backtest loaded and computed!")
    st.info("""
    Key things to check:
    - Does 'Low' classification have higher Avg_Return or Win_Rate than 'High'/'None'?
    - Any day_bc + full_bc combos with strong positive Avg_Return (e.g. >0.4–0.6% daily) and many days?
    - Are master numbers (11,22) or specific values standing out?
    """)
else:
    st.warning("Backtest data could not be loaded or processed.")

st.caption("Powered by yfinance daily data • Vectorized for reliability • No charts")
