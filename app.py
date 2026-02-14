import streamlit as st
import pandas as pd
import yfinance as yf
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

# ── Current day signal logic ───────────────────────────────────────
def get_current_signal_info(now):
    bc_d = bombcode_day(now.day)
    bc_f = bombcode_full(now.month, now.day, now.year)
    cls = classify(bc_d, bc_f)
    return {
        'cls': cls,
        'day_bc': bc_d,
        'full_bc': bc_f,
        'signal': f"**{cls.upper()} day** (day_bc={bc_d}, full_bc={bc_f})"
    }

# ── Historical data + backtest ─────────────────────────────────────
@st.cache_data(ttl=3600)  # cache 1 hour
def load_and_backtest():
    with st.status("Loading historical BTC daily data (2015–now)...", expanded=True) as status:
        try:
            df = yf.download('BTC-USD', start='2015-01-01', progress=False)
            if df.empty:
                status.update(label="No data from yfinance", state="error")
                return None, None

            df = df[['Open', 'Close']].copy()
            df['Return'] = (df['Close'] / df['Open'] - 1) * 100  # open-to-close %

            # Add bombcode columns
            df['day_bc'] = df.index.day.map(bombcode_day)
            df['full_bc'] = df.index.map(lambda dt: bombcode_full(dt.month, dt.day, dt.year))
            df['cls'] = df.apply(lambda r: classify(r['day_bc'], r['full_bc']), axis=1)

            status.update(label=f"Loaded {len(df)} days", state="complete")

            # ── Statistics ──────────────────────────────────────────────
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

        except Exception as e:
            status.update(label=f"Error: {str(e)[:200]}", state="error")
            return None, None, None, None

# ── Main App ───────────────────────────────────────────────────────
st.title("BTC Bombcode Analyzer")

st.markdown("**Current day status** (live)")

now = datetime.now(timezone.utc)
info = get_current_signal_info(now)

st.markdown(f"""
**Classification**: {info['cls']}  
**day_bc**: {info['day_bc']}  
**full_bc**: {info['full_bc']}  
{info['signal']}
""")

st.caption(f"Updated: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")

st.divider()

st.subheader("Historical Backtest (daily open → close returns, 2015–present)")

by_cls, top_combos, day_bc_only, full_bc_only = load_and_backtest()

if by_cls is not None:
    st.markdown("### By Classification (High / Low / None)")
    st.dataframe(by_cls)

    st.markdown("### Top day_bc + full_bc combinations (min 30 days)")
    st.dataframe(top_combos)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Average return by day_bc")
        st.dataframe(day_bc_only.to_frame(name="Avg Return %"))

    with col2:
        st.markdown("### Average return by full_bc")
        st.dataframe(full_bc_only.to_frame(name="Avg Return %"))

    st.info("""
    Observations to make:
    • Does "Low" classification show better average returns or win rate?
    • Are there any day_bc + full_bc combos with strong positive edge (Avg > 0.4–0.6% daily + decent sample)?
    • Do master numbers (11,22) or specific values stand out?
    """)
else:
    st.error("Could not load historical data. yfinance might be blocked or down.")
    st.info("Try running locally or in Colab with the same logic to debug.")

st.caption("Data source: yfinance • Backtest uses open-to-close daily returns • No transaction costs included")
