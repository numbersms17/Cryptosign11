# app.py
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ── Bombcode functions ─────────────────────────────────────────────────────
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

# ── Streamlit App ───────────────────────────────────────────────────────────
st.set_page_config(page_title="Bombcode Backtest", layout="wide")

st.title("Bombcode Power Hour Backtest")
st.markdown("""
**Rules**  
• High days → Short at **high** of every H1/H2/H3 hour  
• Exit after 60 min (next hour close) or TP +1% / SL -0.5%  
• Low days → Long at **low** of every D1/D2 hour  
• Exit after 60 min or TP +1% / SL -0.5% (2:1 RR)  
• Fees/slippage: -0.08% entry + -0.08% exit
""")

col1, col2 = st.columns(2)
start_date = col1.date_input("Start date", value=datetime(2020, 1, 1))
end_date   = col2.date_input("End date", value=datetime.now().date())

if start_date >= end_date:
    st.error("Start date must be before end date")
    st.stop()

if st.button("Run Backtest", type="primary"):
    with st.spinner("Downloading data (chunked for Yahoo limits) & computing..."):
        try:
            # ── Chunked download to bypass 730-day limit for 1h ──────────────
            data_frames = []
            current_start = pd.to_datetime(start_date)
            final_end = pd.to_datetime(end_date) + timedelta(days=1)

            while current_start < final_end:
                chunk_end = min(current_start + timedelta(days=729), final_end)
                st.write(f"Fetching chunk: {current_start.date()} → {chunk_end.date()}")
                chunk = yf.download('BTC-USD', start=current_start, end=chunk_end, interval='1h')
                if not chunk.empty:
                    data_frames.append(chunk)
                current_start = chunk_end

            if not data_frames:
                st.error("No data could be downloaded. Try shorter range or check Yahoo availability.")
                st.stop()

            df = pd.concat(data_frames).sort_index()
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
            df.index = pd.to_datetime(df.index).tz_localize(None)  # Ensure naive

            # ── Compute daily classification ─────────────────────────────────
            df['date'] = df.index.date
            daily_cls = {}
            for d in pd.unique(df['date']):
                dt = datetime.combine(d, datetime.min.time())
                bc_d = bombcode_day(dt.day)
                bc_f = bombcode_full(dt.month, dt.day, dt.year)
                daily_cls[d] = classify(bc_d, bc_f)

            df['day_cls'] = df['date'].map(daily_cls)

            df['hour'] = df.index.hour

            # Safe 'pd' computation
            df['pd_val'] = [get_pd(ts.to_pydatetime()) for ts in df.index]

            # Then 'ph'
            df['ph'] = df.apply(lambda row: get_ph(row['hour'], row['pd_val']), axis=1)

            df['is_H'] = df['ph'].isin(HIGH_PH)
            df['is_D'] = df['ph'].isin(DIP_PH)

            # ── Trades ──────────────────────────────────────────────────────
            trades = []
            FEE = 0.0008

            for idx, row in df.iterrows():
                ts = idx
                cls = row['day_cls']
                if pd.isna(cls): continue

                next_idx = df.index.get_loc(ts) + 1
                if next_idx >= len(df): continue
                next_row = df.iloc[next_idx]

                if cls == "High" and row['is_H']:
                    entry = row['High']
                    tp_price = entry * (1 - 0.01)
                    sl_price = entry * (1 + 0.005)

                    low_next = next_row['Low']
                    high_next = next_row['High']
                    exit_close = next_row['Close']

                    if low_next <= tp_price:
                        pnl = 0.01 - 2 * FEE
                        exit_price = tp_price
                    elif high_next >= sl_price:
                        pnl = -0.005 - 2 * FEE
                        exit_price = sl_price
                    else:
                        pnl = (entry - exit_close) / entry - 2 * FEE
                        exit_price = exit_close

                    trades.append({'entry_time': ts, 'type': 'short', 'day_cls': cls,
                                   'pnl': pnl})

                elif cls == "Low" and row['is_D']:
                    entry = row['Low']
                    tp_price = entry * (1 + 0.01)
                    sl_price = entry * (1 - 0.005)

                    high_next = next_row['High']
                    low_next = next_row['Low']
                    exit_close = next_row['Close']

                    if high_next >= tp_price:
                        pnl = 0.01 - 2 * FEE
                        exit_price = tp_price
                    elif low_next <= sl_price:
                        pnl = -0.005 - 2 * FEE
                        exit_price = sl_price
                    else:
                        pnl = (exit_close - entry) / entry - 2 * FEE
                        exit_price = exit_close

                    trades.append({'entry_time': ts, 'type': 'long', 'day_cls': cls,
                                   'pnl': pnl})

            if not trades:
                st.warning("No trades triggered in this period.")
                st.stop()

            trades_df = pd.DataFrame(trades)
            trades_df['cum_pnl'] = (1 + trades_df['pnl']).cumprod() - 1
            trades_df = trades_df.sort_values('entry_time')

            # ── Equity & drawdown ───────────────────────────────────────────
            equity = trades_df.set_index('entry_time')['cum_pnl']
            rolling_max = equity.cummax()
            drawdown = (equity - rolling_max) / (1 + rolling_max)

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=equity.index, y=equity,
                                     name="Equity Curve", line_color="lime"))
            fig.add_trace(go.Scatter(x=drawdown.index, y=drawdown,
                                     name="Drawdown", line_color="red", fill='tozeroy',
                                     fillcolor='rgba(255,0,0,0.15)'))
            fig.update_layout(title="Equity Curve & Drawdown Bands",
                              yaxis_title="Return / DD", template="plotly_dark",
                              height=500, hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

            # ── Metrics ─────────────────────────────────────────────────────
            colA, colB, colC, colD = st.columns(4)
            colA.metric("Total Trades", len(trades_df))
            colB.metric("Win Rate", f"{(trades_df['pnl'] > 0).mean():.1%}")
            colC.metric("Avg PnL", f"{trades_df['pnl'].mean():.2%}")
            colD.metric("Total Return", f"{trades_df['cum_pnl'].iloc[-1]:.2%}")

            st.subheader("By Type & Day Class")
            st.dataframe(
                trades_df.groupby(['day_cls', 'type'])['pnl'].agg(
                    ['count', 'mean', 'sum', lambda x: (x > 0).mean()]
                ).rename(columns={'<lambda_0>': 'win_rate'})
                .style.format({
                    'mean': '{:.2%}', 'sum': '{:.2%}', 'win_rate': '{:.1%}'
                })
            )

            st.subheader("Last 20 Trades")
            st.dataframe(
                trades_df.tail(20)[['entry_time', 'type', 'day_cls', 'pnl']]
                .style.format({'pnl': '{:.2%}'})
            )

        except Exception as e:
            st.error(f"Error during backtest: {str(e)}")
            st.info("Yahoo limits 1h data to \~730 days — try a shorter range (e.g. 2024–2026). For full history, consider Binance API or CSV upload.")

st.info("Deployed on Streamlit Cloud? Reboot app after code changes.")
