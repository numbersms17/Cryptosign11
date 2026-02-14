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

# ── Current day classification ─────────────────────────────────────
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

# ── Load historical data + backtest ────────────────────────────────
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
        
        # Vectorized bombcode
        df['day_bc'] = df.index.day.map(bombcode_day)
        df['full_bc'] = df.index.map(lambda dt: bombcode_full(dt.month, dt.day, dt.year))
        
        # Debug: show if columns exist and sample values
        st.write("Columns after adding bombcode:", list(df.columns))
        if 'day_bc' in df.columns and 'full_bc' in df.columns:
            st.write("day_bc sample (first 5):", df['day_bc'].head().tolist())
            st.write("full_bc sample (first 5):", df['full_bc'].head().tolist())
        else:
            st.error("Bombcode columns missing after mapping!")
            return None
        
        # Classification - try vectorized first
        try:
            conditions = [
                df['day_bc'].isin([3,5,6,7,8,9]) & df['day_bc'].isin([3,7,5,9]),
                df['day_bc'].isin([3,5,6,7,8,9]) & ~df['day_bc'].isin([3,7,5,9]),
                df['full_bc'].isin([3,7,5,9]),
                df['full_bc'].isin([6,8])
            ]
            choices = ['High', 'Low', 'High', 'Low']
            df['cls'] = np.select(conditions, choices, default='None')
            st.write("Used vectorized np.select for classification")
        except Exception as vec_err:
            st.warning(f"Vectorized classify failed: {vec_err} → falling back to loop")
            # Safe loop fallback
            cls_list = []
            for _, row in df.iterrows():
                cls_list.append(classify(row['day_bc'], row['full_bc']))
            df['cls'] = cls_list
        
        st.write("Classification done. Sample cls:", df['cls'].head(5).tolist())
        return df
    
    except Exception as e:
        st.error(f"Error during load/processing: {str(e)}")
        st.info("Check debug messages above. If columns are missing, index may not be datetime.")
        return None

def classify(day_bc, full_bc):
    if day_bc in {3,5,6,7,8,9}:
        return "High" if day_bc in {3,7,5,9} else "Low"
    return "High" if full_bc in {3,7,5,9} else "Low" if full_bc in {6,8} else "None"

# ── Compute stats ──────────────────────────────────────────────────
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
    st.markdown("Copy-paste this table:")
    st.text(by_cls.to_string())

    st.markdown("### Top Combinations (day_bc + full_bc) – min 30 days")
    st.markdown("Copy-paste this table:")
    st.text(top_combos.to_string())

    st.markdown("### Average Return by day_bc")
    st.markdown("Copy-paste this table:")
    st.text(day_bc_only.to_string())

    st.markdown("### Average Return by full_bc")
    st.markdown("Copy-paste this table:")
    st.text(full_bc_only.to_string())

    st.success("Backtest complete – tables are text-formatted for easy copy.")
else:
    st.warning("Failed to load or process historical data. Chec debug messages above.")

st.caption("Uses yfinance daily • Safe classification loop fallback • Text tables for copy-paste")
