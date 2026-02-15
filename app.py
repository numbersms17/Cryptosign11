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

# ── Current day info ───────────────────────────────────────────────
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

# ── Load recent historical data (2022 → 2025 or latest) ────────────
@st.cache_data(ttl=3600 * 6)
def load_recent_data():
    try:
        df = yf.download('BTC-USD', start='2022-01-01', end='2026-01-01', progress=False)
        if df.empty:
            return None
        df = df[['Open', 'Close']].copy()
        df['Return'] = (df['Close'] / df['Open'] - 1) * 100
        df['day_bc'] = df.index.day.map(bombcode_day)
        df['full_bc'] = df.index.map(lambda dt: bombcode_full(dt.month, dt.day, dt.year))
        
        # Classification logic
        conditions = [
            (df['day_bc'].isin([3,5,6,7,8,9])) & (df['day_bc'].isin([3,7,5,9])),
            (df['day_bc'].isin([3,5,6,7,8,9])) & (~df['day_bc'].isin([3,7,5,9])),
            df['full_bc'].isin([3,7,5,9]),
            df['full_bc'].isin([6,8])
        ]
        choices = ['High', 'Low', 'High', 'Low']
        df['cls'] = np.select(conditions, choices, default='None')
        
        return df
    except Exception as e:
        st.error(f"Data load error: {str(e)}")
        return None

# ── Statistics ─────────────────────────────────────────────────────
def compute_stats(df):
    if df is None or df.empty:
        return None, None, None, None
    
    # By classification
    by_cls = df.groupby('cls')['Return'].agg(
        Days='count',
        Avg_Daily_Return='% mean',
        Median_Return='% median',
        Win_Rate=lambda x: (x > 0).mean() * 100,
        Volatility='% std'
    ).round(2)
    
    # Top combos (≥20 days in recent period)
    combos = df.groupby(['cls', 'day_bc', 'full_bc'])['Return'].agg(
        Days='count',
        Avg_Return='% mean',
        Win_Rate=lambda x: (x > 0).mean() * 100
    ).round(2)
    strong_combos = combos[combos['Days'] >= 20].sort_values('Avg_Return', ascending=False)
    
    # By single numbers
    by_day_bc = df.groupby('day_bc')['Return'].mean().sort_values(ascending=False).round(2)
    by_full_bc = df.groupby('full_bc')['Return'].mean().sort_values(ascending=False).round(2)
    
    return by_cls, strong_combos, by_day_bc, by_full_bc

# ── Price Swing Scanner (recent years) ─────────────────────────────
def scan_swings(df, min_days=4, max_days=10, threshold_pct=10):
    swings = []
    for length in range(min_days, max_days + 1):
        for start in range(len(df) - length):
            slice_df = df.iloc[start:start+length]
            try:
                open_p = float(slice_df['Open'].iloc[0])
                close_p = float(slice_df['Close'].iloc[-1])
                ret = (close_p / open_p - 1) * 100
                if abs(ret) >= threshold_pct:
                    start_date = slice_df.index[0].date()
                    end_date = slice_df.index[-1].date()
                    start_full = int(slice_df['full_bc'].iloc[0])
                    end_full = int(slice_df['full_bc'].iloc[-1])
                    direction = 'UP (potential top/short)' if ret >= 0 else 'DOWN (potential bottom/long)'
                    swings.append({
                        'Start': start_date,
                        'End': end_date,
                        'Days': length,
                        '% Return': round(ret, 2),
                        'Direction': direction,
                        'Start_full_bc': start_full,
                        'End_full_bc': end_full
                    })
            except:
                continue
    
    if not swings:
        return None, None
    
    swing_df = pd.DataFrame(swings)
    stats = swing_df.groupby('Start_full_bc').agg(
        Count='size',
        Avg_Return='% mean',
        Up_Pct=lambda x: (x > 0).mean() * 100
    ).round(2).sort_values('Avg_Return', ascending=False)
    
    return swing_df, stats

# ── Main App ───────────────────────────────────────────────────────
st.title("BTC Bombcode Analyzer – 2022–2025 Focus")

now = datetime.now(timezone.utc)
info = get_current_info(now)

st.subheader("Today")
st.markdown(f"""
**Classification**: {info['cls']}  
**day_bc**: {info['day_bc']}  
**full_bc**: {info['full_bc']}  
{info['signal']}
""")
st.caption(f"Updated: {now.strftime('%Y-%m-%d %H:%M UTC')}")

st.divider()

df = load_recent_data()

if df is not None:
    st.subheader("Performance 2022–2025")
    by_cls, strong_combos, by_day_bc, by_full_bc = compute_stats(df)
    
    st.markdown("**By Classification**")
    st.dataframe(by_cls)
    
    st.markdown("**Strongest combos (≥20 days, sorted by avg return)**")
    st.dataframe(strong_combos.head(15))
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**By day_bc (average return)**")
        st.dataframe(by_day_bc.to_frame('%'))
    with col2:
        st.markdown("**By full_bc (average return)**")
        st.dataframe(by_full_bc.to_frame('%'))
    
    st.divider()
    
    st.subheader("Big Swings Scanner (≥10% in 4–10 days)")
    swing_df, swing_stats = scan_swings(df, threshold_pct=10)
    if swing_stats is not None:
        st.markdown("**Entry bias by starting full_bc**")
        st.dataframe(swing_stats)
        
        st.markdown("**Recent big swings sample**")
        st.dataframe(swing_df.tail(15))
    else:
        st.warning("No swings ≥10% detected in period. Try lowering threshold to 7–8%.")

else:
    st.error("Could not load BTC data from yfinance.")

st.caption("Data: daily BTC-USD 2022–2025 • yfinance • Numerology patterns only • Not financial advice")
