import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime, timezone

# ── BOMB CODE LOGIC ────────────────────────────────────────────────
def reduce(n):
    while n > 9:
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

# ── Price Swing Scanner: Big Up/Down Moves ─────────────────────────
def scan_price_swings(df, min_days=4, max_days=10, threshold_pct=10):
    swings = []
    for length in range(min_days, max_days + 1):
        for start in range(len(df) - length):
            slice_df = df.iloc[start:start+length]
            total_return = (slice_df['Close'].iloc[-1] / slice_df['Open'].iloc[0] - 1) * 100
            if abs(total_return) >= threshold_pct:
                start_date = slice_df.index[0].date()
                end_date = slice_df.index[-1].date()
                start_full_bc = slice_df['full_bc'].iloc[0]
                end_full_bc = slice_df['full_bc'].iloc[-1]
                start_day_bc = slice_df['day_bc'].iloc[0]
                direction = 'UP (Top/Short)' if total_return >= threshold_pct else 'DOWN (Bottom/Long)'
                swings.append({
                    'Start_Date': start_date,
                    'End_Date': end_date,
                    'Length': length,
                    'Total_Return (%)': round(total_return, 2),
                    'Direction': direction,
                    'Start_full_bc': start_full_bc,
                    'End_full_bc': end_full_bc,
                    'Start_day_bc': start_day_bc
                })
    swing_df = pd.DataFrame(swings)
    if swing_df.empty:
        return None, None
    # Stats by start full_bc (entry bias)
    start_stats = swing_df.groupby('Start_full_bc').agg({
        'Total_Return (%)': ['count', 'mean', lambda x: (x > 0).mean() * 100],
        'Direction': lambda x: x.mode()[0] if not x.empty else 'MIXED'
    }).round(2)
    start_stats.columns = ['Count', 'Avg_Return', 'Up_Pct', 'Common_Dir']
    start_stats = start_stats.sort_values('Avg_Return', ascending=False)
    return swing_df, start_stats

# ── Month-End vs Month-Start Bias ──────────────────────────────────
def month_bias(df):
    monthly = df.resample('M').agg({
        'Open': 'first',
        'Close': 'last',
        'Return': 'sum'
    })
    monthly['Monthly_Return (%)'] = (monthly['Close'] / monthly['Open'] - 1) * 100
    monthly['Month_End_Bias'] = monthly['Monthly_Return (%)'].apply(
        lambda x: 'Strong Close Up (Top/Short)' if x > 5 else 'Strong Close Down (Bottom/Long)' if x < -5 else 'Neutral'
    )
    return monthly[['Monthly_Return (%)', 'Month_End_Bias']]

# ── Main App ───────────────────────────────────────────────────────
st.title("BTC Bombcode Analyzer – Price Swing Scanner")

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

    st.subheader("Price Swing Scanner – Big Moves (≥10% over 4–10 days)")
    st.info("Detects historical swings with strong up/down moves. Look at Start_full_bc for entry bias (e.g. certain numbers start big drops → short).")
    swing_df, start_stats = scan_price_swings(df, min_days=4, max_days=10, threshold_pct=10)
    if start_stats is not None:
        st.text("Swing Stats by Start full_bc (Entry Bias):\n" + start_stats.to_string())
        st.text("Detected Swings Sample (first 20):\n" + swing_df.head(20).to_string(index=False))
    else:
        st.warning("No swings ≥10% found (try lowering threshold_pct to 5 or 8).")

    st.divider()

    st.subheader("Month-End vs Month-Start Bias")
    st.info("Monthly close performance – strong close up = potential top/short, strong close down = potential bottom/long.")
    month_df = month_bias(df)
    st.text("Monthly Bias Summary:\n" + month_df.to_string())

else:
    st.error("Failed to load BTC data.")

st.caption("yfinance daily • Price swing focus • Bottom/Top of month check")
