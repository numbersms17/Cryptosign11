import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# ── Reduce & bombcode ──────────────────────────────────────────────
def reduce(n):
    while n > 9 and n not in {11, 22}:
        n = sum(int(c) for c in str(n))
    return n

def bombcode(m, d, y):
    return reduce(m + d + y)

# ── Hour values & PH ───────────────────────────────────────────────
HOUR_VALUES = {
    0:3,1:1,2:2,3:3,4:4,5:5,6:6,7:7,8:8,9:9,
    10:1,11:2,12:3,13:1,14:2,15:3,16:4,17:5,18:6,
    19:7,20:8,21:9,22:1,23:2
}

PEAK_PH = {3,6,9}
DIP_PH = {7,11}

def get_pd_for_timestamp(ts):
    base = ts.replace(hour=18, minute=0, second=0, microsecond=0)
    if ts.hour < 18:
        base -= timedelta(days=1)
    py = reduce(3 + 1 + base.year)
    pm = reduce(py + base.month)
    return reduce(pm + base.day)

def get_ph(hour, pd):
    val = HOUR_VALUES[hour]
    ph = pd + val
    return ph if ph in {11,22} else reduce(ph)

# ── Load BTC prices ────────────────────────────────────────────────
@st.cache_data(ttl=3600 * 6)
def load_btc_prices(start_date, end_date):
    try:
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = (end_date + timedelta(days=1)).strftime('%Y-%m-%d')
        df = yf.download('BTC-USD', start=start_str, end=end_str, progress=False)
        if df.empty:
            return None
        return df['Close']
    except Exception as e:
        st.error(f"Price load error: {str(e)}")
        return None

# ── Generate & backtest signals ────────────────────────────────────
def run_swing_backtest(start_date, end_date):
    prices = load_btc_prices(start_date, end_date)
    if prices is None:
        return None, None

    # Hourly data for PH
    hourly_data = []
    current = datetime(start_date.year, start_date.month, start_date.day, 0, 0)
    end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59)
    while current <= end_dt:
        pd_val = get_pd_for_timestamp(current)
        ph = get_ph(current.hour, pd_val)
        hourly_data.append({
            'ts': current,
            'date': current.date(),
            'ph': ph,
            'is_high': ph in PEAK_PH,
            'is_dip': ph in DIP_PH
        })
        current += timedelta(hours=1)

    # Monthly bombcode counters
    month_data = defaultdict(lambda: {k: [] for k in ['six','three','seven','nine','eight']})
    for h in hourly_data:
        if h['ts'].hour == 0:
            b = bombcode(h['date'].month, h['date'].day, h['date'].year)
            ym = (h['date'].year, h['date'].month)
            if b == 6: month_data[ym]['six'].append(h['date'])
            if b == 3: month_data[ym]['three'].append(h['date'])
            if b == 7: month_data[ym]['seven'].append(h['date'])
            if b == 9: month_data[ym]['nine'].append(h['date'])
            if b == 8: month_data[ym]['eight'].append(h['date'])

    active_trades = []
    completed = []

    def next_month_first6(entry):
        y, m = entry.year, entry.month
        ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
        return month_data[(ny, nm)]['six'][0] if month_data[(ny, nm)]['six'] else None

    def next_month_first7(entry):
        y, m = entry.year, entry.month
        ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
        return month_data[(ny, nm)]['seven'][0] if month_data[(ny, nm)]['seven'] else None

    # Process day by day
    current_date = start_date
    while current_date <= end_date:
        ym = (current_date.year, current_date.month)
        data = month_data[ym]

        # Check exits
        still_active = []
        for trade in active_trades:
            entry_date, ttype, desc = trade
            exit_triggered = False

            if ttype.startswith('L') and any(h['date'] == current_date and h['is_high'] for h in hourly_data):
                if ttype == 'L1' and len(data['seven']) >= 2 and data['seven'][1] == current_date:
                    exit_triggered = True
                elif ttype == 'L1b' and len(data['three']) >= 2 and data['three'][1] == current_date:
                    exit_triggered = True
                elif ttype == 'L3' and len(data['nine']) >= 2 and data['nine'][1] == current_date:
                    exit_triggered = True
                elif ttype == 'L4' and len(data['nine']) >= 3 and data['nine'][2] == current_date:
                    exit_triggered = True
                elif ttype == 'L2' and next_month_first7(entry_date) == current_date:
                    exit_triggered = True

            elif ttype in {'SHORT','S1','S2'} and any(h['date'] == current_date and h['is_dip'] for h in hourly_data):
                if ttype == 'SHORT' and len(data['eight']) >= 3 and data['eight'][2] == current_date:
                    exit_triggered = True
                elif ttype == 'S1' and next_month_first6(entry_date) == current_date:
                    exit_triggered = True
                elif ttype == 'S2' and next_month_first6(entry_date) == current_date:
                    exit_triggered = True

            if exit_triggered:
                entry_close = prices.get(pd.Timestamp(entry_date))
                exit_close = prices.get(pd.Timestamp(current_date))
                ret = (exit_close / entry_close - 1) * 100 if pd.notna(entry_close) and pd.notna(exit_close) else None

                completed.append({
                    'Type': ttype,
                    'Entry': entry_date,
                    'Exit': current_date,
                    'Held days': (current_date - entry_date).days,
                    'Return %': round(ret, 2) if ret is not None else 'N/A',
                    'Desc': desc
                })
            else:
                still_active.append(trade)

        active_trades = still_active

        # Entries at midnight
        if current_date in data['six']:
            idx = data['six'].index(current_date)
            if idx == 0:
                if len(data['seven']) >= 2 and data['seven'][1] >= current_date:
                    active_trades.append((current_date, 'L1', '1st 6 → 2nd 7'))
                if len(data['three']) >= 2 and data['three'][1] >= current_date:
                    active_trades.append((current_date, 'L1b', '1st 6 → 2nd 3'))
            if idx == 1 and len(data['nine']) >= 2 and data['nine'][1] >= current_date:
                active_trades.append((current_date, 'L3', '2nd 6 → 3rd 9'))
            if idx == 2:
                if len(data['nine']) >= 3 and data['nine'][2] >= current_date:
                    active_trades.append((current_date, 'L4', '3rd 6 → 4th 9'))
                if next_month_first7(current_date) and next_month_first7(current_date) <= end_date:
                    active_trades.append((current_date, 'L2', '3rd 6 → next 1st 7'))

        elif current_date in data['seven'] and data['seven'].index(current_date) == 1:
            if len(data['eight']) >= 3 and data['eight'][2] >= current_date:
                active_trades.append((current_date, 'SHORT', '2nd 7 → 3rd 8'))

        elif current_date in data['nine'] and data['nine'].index(current_date) == 2:
            if next_month_first6(current_date) and next_month_first6(current_date) <= end_date:
                active_trades.append((current_date, 'S1', '3rd 9 → next 1st 6'))

        elif current_date in data['three'] and data['three'].index(current_date) == 3:
            if next_month_first6(current_date) and next_month_first6(current_date) <= end_date:
                active_trades.append((current_date, 'S2', '4th 3 → next 1st 6'))

        current_date += timedelta(days=1)

    # Results
    return completed

# ── App ────────────────────────────────────────────────────────────
st.title("BTC Swing Codes Backtest – 2022 to Now")

st.subheader("Run Backtest")
start_date = st.date_input("Start Date", value=datetime(2022, 1, 1).date())
end_date = st.date_input("End Date", value=datetime.now(timezone.utc).date())

if st.button("Run Backtest"):
    with st.spinner("Loading prices & generating signals..."):
        completed = run_swing_backtest(start_date, end_date)

    if not completed:
        st.error("No signals or data loaded.")
    else:
        longs = [t for t in completed if t['Type'].startswith('L')]
        shorts = [t for t in completed if t['Type'] in {'SHORT', 'S1', 'S2'}]

        st.subheader("Results Summary")
        st.text(f"Total completed signals: {len(completed)}")
        st.text(f"LONGS: {len(longs)}")
        st.text(f"SHORTS: {len(shorts)}")

        long_returns = [t['Return %'] for t in longs if t['Return %'] != 'N/A' and isinstance(t['Return %'], (int, float))]
        short_returns = [t['Return %'] for t in shorts if t['Return %'] != 'N/A' and isinstance(t['Return %'], (int, float))]

        if long_returns:
            st.text(f"Longs avg return: {sum(long_returns)/len(long_returns):.2f}%")
            st.text(f"Long win rate (>0%): {len([r for r in long_returns if r > 0])/len(long_returns)*100:.1f}%")
        if short_returns:
            st.text(f"Shorts avg return: {sum(short_returns)/len(short_returns):.2f}%")
            st.text(f"Short win rate (<0%): {len([r for r in short_returns if r < 0])/len(short_returns)*100:.1f}%")

        st.subheader("All Completed Trades")
        for t in sorted(completed, key=lambda x: x['Entry'], reverse=True):
            st.text(f"{t['Type']} | Entry: {t['Entry']} | Exit: {t['Exit']} | Held: {t['Held days']}d | Return: {t['Return %']}% | {t['Desc']}")

st.caption("Signals generated from your swing code logic. Returns calculated close-to-close. Not financial advice.")
