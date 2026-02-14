import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime, timezone, timedelta

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

# ── Historical data load ───────────────────────────────────────────
@st.cache_data(ttl=3600 * 6)
def load_historical_data():
    try:
        df = yf.download('BTC-USD', start='2015-01-01', progress=False)
        if df.empty:
            return None
        df = df[['Open', 'Close']].copy()
        df['Return'] = (df['Close'] / df['Open'] - 1) * 100
        df['day_bc'] = df.index.day.map(bombcode_day)
        df['full_bc'] = df.index.map(lambda dt: bombcode_full(dt.month, dt.day, dt.year))
        conditions = [
            df['day_bc'].isin([3,5,6,7,8,9]) & df['day_bc'].isin([3,7,5,9]),
            df['day_bc'].isin([3,5,6,7,8,9]) & ~df['day_bc'].isin([3,7,5,9]),
            df['full_bc'].isin([3,7,5,9]),
            df['full_bc'].isin([6,8])
        ]
        choices = ['High', 'Low', 'High', 'Low']
        df['cls'] = np.select(conditions, choices, default='None')
        return df
    except Exception as e:
        st.error(f"Data load error: {str(e)}")
        return None

# ── Single-day stats (original backtest) ───────────────────────────
def compute_single_stats(df):
    if df is None:
        return None, None, None, None
    by_cls = df.groupby('cls')['Return'].agg(['count', 'mean', 'median', lambda x: (x > 0).mean() * 100, 'std']).round(2)
    by_cls.columns = ['Days', 'Avg_Return', 'Median', 'Win_Rate', 'Volatility']
    combos = df.groupby(['cls', 'day_bc', 'full_bc'])['Return'].agg(['count', 'mean', 'median', lambda x: (x > 0).mean() * 100, 'std']).round(2)
    combos.columns = ['Days', 'Avg_Return', 'Median', 'Win_Rate', 'Volatility']
    top_combos = combos[combos['Days'] >= 30].sort_values('Avg_Return', ascending=False).head(20)
    day_bc_only = df.groupby('day_bc')['Return'].mean().sort_values(ascending=False).round(2)
    full_bc_only = df.groupby('full_bc')['Return'].mean().sort_values(ascending=False).round(2)
    return by_cls, top_combos, day_bc_only, full_bc_only

# ── Genius Mode: Full_BC Sequence Scanner ──────────────────────────
def scan_full_bc_sequences(df, min_length=4):
    chains = []
    current_chain = []
    for i in range(len(df)):
        if not current_chain:
            current_chain = [df.iloc[i]['full_bc']]
            start_idx = i
            continue
        prev = current_chain[-1]
        curr = df.iloc[i]['full_bc']
        # Consecutive check: +1 or wrap (9→1) or master jump (1→11, 10→11, 21→22 if fits)
        if curr == prev + 1 or (prev == 9 and curr == 1) or (prev in {1,10,21} and curr in {11,22}):
            current_chain.append(curr)
        else:
            if len(current_chain) >= min_length:
                chain_return = (df.iloc[i-1]['Close'] / df.iloc[start_idx]['Open'] - 1) * 100
                start_date = df.index[start_idx].date()
                end_date = df.index[i-1].date()
                seq_str = '→'.join(map(str, current_chain))
                avg_full_bc = np.mean(current_chain)
                bias = 'LONG' if chain_return > 0 else 'SHORT'
                chains.append({
                    'Sequence': seq_str,
                    'Length': len(current_chain),
                    'Start_Date': start_date,
                    'End_Date': end_date,
                    'Return': round(chain_return, 2),
                    'Bias': bias,
                    'Avg_Full_BC': round(avg_full_bc, 2)
                })
            current_chain = [curr]
            start_idx = i
    # Last chain if qualifying
    if len(current_chain) >= min_length:
        chain_return = (df.iloc[-1]['Close'] / df.iloc[start_idx]['Open'] - 1) * 100
        start_date = df.index[start_idx].date()
        end_date = df.index[-1].date()
        seq_str = '→'.join(map(str, current_chain))
        bias = 'LONG' if chain_return > 0 else 'SHORT'
        chains.append({
            'Sequence': seq_str,
            'Length': len(current_chain),
            'Start_Date': start_date,
            'End_Date': end_date,
            'Return': round(chain_return, 2),
            'Bias': bias,
            'Avg_Full_BC': round(np.mean(current_chain), 2)
        })
    chain_df = pd.DataFrame(chains)
    if chain_df.empty:
        return None
    # Group by sequence pattern for stats
    pattern_stats = chain_df.groupby('Sequence').agg({
        'Length': 'mean',
        'Return': ['count', 'mean', 'std', lambda x: (x > 0).mean() * 100],
        'Bias': lambda x: x.mode()[0] if not x.empty else 'MIXED'
    }).round(2)
    pattern_stats.columns = ['Avg_Length', 'Count', 'Avg_Return', 'Volatility', 'Win_Rate', 'Common_Bias']
    pattern_stats = pattern_stats.sort_values('Win_Rate', ascending=False)
    return chain_df, pattern_stats

# ── Main App ───────────────────────────────────────────────────────
st.title("BTC Bombcode Analyzer – Genius Sequence Edition")

now = datetime.now(timezone.utc)
info = get_current_info(now)

st.subheader("Current Day")
st.markdown(f"""
**Classification**: {info['cls']}  
**day_bc**: {info['day_bc']}  
**full_bc**: {info['full_bc']}  
{info['signal']}
""")
st.caption(f"UTC: {now.strftime('%Y-%m-%d %H:%M:%S')}")

st.divider()

df = load_historical_data()

if df is not None:
    st.subheader("Single-Day Backtest (Original)")
    by_cls, top_com
