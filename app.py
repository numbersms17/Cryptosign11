# app.py - SIMPLE DAILY HIGH/LOW BACKTEST - FIXED FLOAT IN SET ERROR
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

def classify(day_bc, full_bc):
    day_bc = int(day_bc)   # FIX: force int to avoid float in set error
    full_bc = int(full_bc)
    if day_bc in {3,5,6,7,8,9}:
        return "High" if day_bc in {3,7,5,9} else "Low"
    return "High" if full_bc in {3,7,5,9} else "Low" if full_bc in {6,8} else "None"

# ── APP ────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Bombcode Daily High/Low Backtest", layout="wide")

st.title("Bombcode Daily High/Low Backtest")
st.markdown("""
**Simplified Rules**  
- On **High** days → Short at the **daily high**  
- On **Low** days → Long at the **daily low**  
- Exit: next day close  
- Fees/slippage: -0.16% round-trip  
- Data: daily candles (BTC-USD)
""")

start_date = st.date_input("Start date", value=datetime(2020, 1, 1))
end_date   = st.date_input("End date", value=datetime.now().date())

if start_date >= end_date:
    st.error("Start date must be before end date")
    st.stop()

if st.button("RUN BACKTEST", type="primary"):
    with st.spinner("Downloading daily data & backtesting..."):
        df = yf.download("BTC-USD", start=start_date, end=end_date + timedelta(days=1), interval="1d")
        df = df[['Open','High','Low','Close','Volume']].dropna()

        # Daily classification
        df['date'] = df.index.date
        df['day_bc'] = df.index.map(lambda d: bombcode_day(d.day))
        df['full_bc'] = df.index.map(lambda d: bombcode_full(d.month, d.day, d.year))
        df['day_cls'] = df.apply(lambda r: classify(r['day_bc'], r['full_bc']), axis=1)

        # Trades
        trades = []
        FEE = 0.0008 * 2  # round-trip

        for i in range(len(df) - 1):
            row = df.iloc[i]
            next_row = df.iloc[i+1]

            if row['day_cls'] == "High":
                entry = row['High']
                exit_price = next_row['Close']
                pnl = (entry - exit_price) / entry - FEE
                trades.append({'time': row.name, 'type': 'SHORT', 'pnl': pnl})

            elif row['day_cls'] == "Low":
                entry = row['Low']
                exit_price = next_row['Close']
                pnl = (exit_price - entry) / entry - FEE
                trades.append({'time': row.name, 'type': 'LONG', 'pnl': pnl})

        if not trades:
            st.warning("No trades triggered.")
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

st.caption("Daily high/low version - no hourly data, no chunking errors. Full history works.")
