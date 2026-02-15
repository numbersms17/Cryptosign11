import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime, timezone

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

# ── Load historical data ───────────────────────────────────────────
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

# ── Single-day stats ───────────────────────────────────────────────
def compute_single_stats(df):
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

# ── Full_BC Sequence Scanner ───────────────────────────────────────
def scan_full_bc_sequences(df, min_length=4):
    chains = []
    current_chain = []
    start_idx = None
    for i in range(len(df)):
        try:
            curr_raw = df.iloc[i]['full_bc']
            if pd.isna(curr_raw):
                curr = np.nan
            else:
                curr = float(curr_raw.item() if hasattr(curr_raw, 'item') else curr_raw)
        except:
            curr = np.nan

        if pd.isna(curr):
            if current_chain and start_idx is not None:
                try:
                    open_price = df.iloc[start_idx]['Open'].item()
                    close_price = df.iloc[i-1]['Close'].item()
                    chain_return = (close_price / open_price - 1) * 100
                    start_date = df.index[start_idx].date()
                    end_date = df.index[i-1].date()
                    seq_str = '→'.join(map(str, current_chain))
                    bias = 'LONG' if chain_return > 0 else 'SHORT'
                    chains.append({
                        'Sequence': seq_str,
                        'Length': len(current_chain),
                        'Start_Date': start_date,
                        'End_Date': end_date,
                        'Return': round(chain_return, 2),
                        'Bias': bias
                    })
                except:
                    pass  # skip invalid chain
            current_chain = []
            start_idx = None
            continue

        if not current_chain:
            current_chain = [curr]
            start_idx = i
            continue

        prev = current_chain[-1]
        is_consecutive = (curr == prev + 1)
        is_wrap = (prev == 9 and curr == 1)

        if is_consecutive or is_wrap:
            current_chain.append(curr)
        else:
            if len(current_chain) >= min_length and start_idx is not None:
                try:
                    open_price = df.iloc[start_idx]['Open'].item()
                    close_price = df.iloc[i-1]['Close'].item()
                    chain_return = (close_price / open_price - 1) * 100
                    start_date = df.index[start_idx].date()
                    end_date = df.index[i-1].date()
                    seq_str = '→'.join(map(str, current_chain))
                    bias = 'LONG' if chain_return > 0 else 'SHORT'
                    chains.append({
                        'Sequence': seq_str,
                        'Length': len(current_chain),
                        'Start_Date': start_date,
                        'End_Date': end_date,
                        'Return': round(chain_return, 2),
                        'Bias': bias
                    })
                except:
                    pass
            current_chain = [curr]
            start_idx = i

    # Last chain
    if len(current_chain) >= min_length and start_idx is not None:
        try:
            open_price = df.iloc[start_idx]['Open'].item()
            close_price = df.iloc[-1]['Close'].item()
            chain_return = (close_price / open_price - 1) * 100
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
                'Bias': bias
            })
        except:
            pass

    chain_df = pd.DataFrame(chains)
    if chain_df.empty:
        return None, None

    pattern_stats = chain_df.groupby('Sequence').agg({
        'Length': 'mean',
        'Return': ['count', 'mean', 'std', lambda x: (x > 0).mean() * 100],
        'Bias': lambda x: x.mode()[0] if not x.empty else 'MIXED'
    }).round(2)
    pattern_stats.columns = ['Avg_Length', 'Count', 'Avg_Return', 'Volatility', 'Win_Rate', 'Common_Bias']
    pattern_stats = pattern_stats.sort_values('Win_Rate', ascending=False)
    return chain_df, pattern_stats

# ── Main App ───────────────────────────────────────────────────────
st.title("BTC Bombcode Analyzer – Sequence Scanner (Scalar Fixed)")

now = datetime.now(timezone.utc)
info = get_current_info(now)

st.subheader("Current Day")
st.markdown(f"""
**Classification**: {info['cls']}  
**day_bc**: {info['day_bc']}  
**full_bc**: {info['full_bc']}  
{info['signal']}
""")
st.caption(f"Updated: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")

st.divider()

df = load_historical_data()

if df is not None:
    st.subheader("Single-Day Backtest")
    by_cls, top_combos, day_bc_only, full_bc_only = compute_single_stats(df)
    st.text("By Classification:\n" + by_cls.to_string())
    st.text("Top Combos (min 30 days):\n" + top_combos.to_string())
    st.text("By day_bc:\n" + day_bc_only.to_string())
    st.text("By full_bc:\n" + full_bc_only.to_string())

    st.divider()

    st.subheader("Full_BC Sequence Scanner (Consecutive Chains)")
    st.info("Detects ascending full_bc chains ≥4 days (with 9→1 wrap). Stats sorted by winrate. Bias from actual returns.")
    chain_df, pattern_stats = scan_full_bc_sequences(df, min_length=4)
    if pattern_stats is not None:
        st.text("Pattern Stats (High Winrate First):\n" + pattern_stats.to_string())
        st.text("Detected Chains Sample (first 20):\n" + chain_df.head(20).to_string(index=False))
    else:
        st.warning("No qualifying full_bc chains found.")
else:
    st.error("Failed to load BTC data.")

st.caption("yfinance daily • Full scalar-safe • Winrate-focused")
