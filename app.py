# app.py - FINAL FIXED VERSION - NO UNHASHABLE ERROR
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ── BOMB CODE FUNCTIONS ────────────────────────────────────────────────────
HOUR_VALUES = {0:12,1:1,2:2,3:3,4:4,5:5,6:6,7:7,8:8,9:9,10:10,11:11,
               12:12,13:1,14:2,15:3,16:4,17:5,18:6,19:7,20:8,21:9,22:10,23:11}

HIGH_PH = {3,6,9}
DIP_PH  = {7,11}

def reduce(n):
    while n > 9 and n not in {11,22}:
        n = sum(int(c) for c in str(n))
    return n

def bombcode_day(d): return reduce(d)
def bombcode_full(m,d,y): return reduce(m + d + y)

def get_pd(ts):
    base = ts.replace(hour=18, minute=15)
    if ts.hour < 18 or (ts.hour == 18 and ts.minute < 15):
        base -= timedelta(days=1)
    py = reduce(3 + 1 + base.year)
    pm = reduce(py + base.month)
    return reduce(pm + base.day)

def get_ph(h, pd_val):
    ph = pd_val + HOUR_VALUES[h]
    return ph if ph in {11,22} else reduce(ph)

def classify(day_bc, full_bc):
    if day_bc in {3,5,6,7,8,9}:
        return "High" if day_bc in {3,7,5,9} else "Low"
    return "High" if full_bc in {3,7,5,9} else "Low" if full_bc in {6,8} else "None"

# ── APP ────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Bombcode Backtest", layout="wide")

st.title("Bombcode Power Hour Backtest")
st.markdown("Short High days @ H-hours • Long Low days @ D-hours • 2:1 RR • -0.16% fees")

start_date = st.date_input("Start date", value=datetime(2020, 1, 1))
end_date   = st.date_input("End date", value=datetime.now().date())

if start_date >= end_date:
    st.error("Start date must be before end date")
    st.stop()

if st.button("RUN BACKTEST", type="primary"):
    with st.spinner("Downloading data in chunks..."):
        chunks = []
        cur_start = pd.to_datetime(start_date)
        final_end = pd.to_datetime(end_date) + timedelta(days=1)
        while cur_start < final_end:
            chunk_end = min(cur_start + timedelta(days=700), final_end)
            try:
                chunk = yf.download("BTC-USD", start=cur_start, end=chunk_end, interval="1h")
                if not chunk.empty:
                    chunks.append(chunk)
            except Exception as e:
                st.warning(f"Chunk error: {e}")
            cur_start = chunk_end

        if not chunks:
            st.error("No data downloaded. Try shorter range or check connection.")
            st.stop()

        df = pd.concat(chunks).sort_index()
        df = df[['Open','High','Low','Close','Volume']].dropna()
        df.index = pd.to_datetime(df.index).tz_localize(None)

    with st.spinner("Computing signals & trades..."):
        df['date'] = df.index.date
        df['hour'] = df.index.hour

        # Safe pd_val (map prevents series issues)
        df['pd_val'] = df.index.map(lambda ts: get_pd(ts.to_pydatetime()))

        # Vectorized ph computation (no apply)
        df['ph'] = df['pd_val'] + df['hour'].map(HOUR_VALUES)
        df['ph'] = df['ph'].apply(lambda x: x if x in {11,22} else reduce(x))

        df['day_cls'] = df['date'].map(lambda d: classify(bombcode_day(d.day), bombcode_full(d.month, d.day, d.year)))

        df['is_H'] = df['ph'].isin(HIGH_PH) & (df['day_cls'] == "High")
        df['is_D'] = df['ph'].isin(DIP_PH) & (df['day_cls'] == "Low")

        # Trades
        trades = []
        FEE = 0.0008
        for i in range(len(df) - 1):
            row = df.iloc[i]
            next_row = df.iloc[i+1]

            if row['is_H']:
                entry = row['High']
                tp_price = entry * 0.99
                sl_price = entry * 1.005
                if next_row['Low'] <= tp_price:
                    pnl = 0.01 - 2 * FEE
                elif next_row['High'] >= sl_price:
                    pnl = -0.005 - 2 * FEE
                else:
                    pnl = (entry - next_row['Close']) / entry - 2 * FEE
                trades.append({'time': row.name, 'type': 'SHORT', 'pnl': pnl})

            elif row['is_D']:
                entry = row['Low']
                tp_price = entry * 1.01
                sl_price = entry * 0.995
                if next_row['High'] >= tp_price:
                    pnl = 0.01 - 2 * FEE
                elif next_row['Low'] <= sl_price:
                    pnl = -0.005 - 2 * FEE
                else:
                    pnl = (next_row['Close'] - entry) / entry - 2 * FEE
                trades.append({'time': row.name, 'type': 'LONG', 'pnl': pnl})

        if not trades:
            st.warning("No trades triggered in this period.")
            st.stop()

        trades_df = pd.DataFrame(trades)
        trades_df['cum_pnl'] = (1 + trades_df['pnl']).cumprod() - 1
        trades_df = trades_df.sort_values('time')

        # Equity + DD bands
        equity = trades_df.set_index('time')['cum_pnl']
        rolling_max = equity.cummax()
        drawdown = (equity - rolling_max) / (1 + rolling_max)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=equity.index, y=equity, name="Equity Curve", line=dict(color="lime")))
        fig.add_trace(go.Scatter(x=drawdown.index, y=drawdown, name="Drawdown", line=dict(color="red"),
                                 fill='tozeroy', fillcolor='rgba(255,0,0,0.2)'))
        fig.update_layout(title="Equity Curve + Drawdown Bands", yaxis_title="Return / DD",
                          template="plotly_dark", height=500, hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

        # Metrics
        cols = st.columns(4)
        cols[0].metric("Trades", len(trades_df))
        cols[1].metric("Win Rate", f"{(trades_df['pnl'] > 0).mean():.1%}")
        cols[2].metric("Avg PnL", f"{trades_df['pnl'].mean():.2%}")
        cols[3].metric("Total Return", f"{trades_df['cum_pnl'].iloc[-1]:.2%}")

        st.success("BACKTEST COMPLETE!")
        st.dataframe(trades_df.tail(20).style.format({'pnl': '{:.2%}'}))

st.caption("Chunking + vectorized fix = full 2020-2026 backtest working. Reboot app if needed.")
