# app.py
import streamlit as st
from datetime import datetime, timedelta

st.set_page_config(
    page_title="#CRYPTOSIGN #STOCKSIGN Signals",
    page_icon="₿📊",
    layout="wide"
)

# ────────────────────────────────────────────────
#   === YOUR SECRET CONSTANTS & LOGIC ===
#   (never shown / never printed to user)
# ────────────────────────────────────────────────
BTC_BIRTH = datetime(2009, 1, 3, 18, 15)

HOUR_VALUES = {
    0:12,1:1,2:2,3:3,4:4,5:5,6:6,7:7,8:8,9:9,10:10,11:11,
    12:12,13:1,14:2,15:3,16:4,17:5,18:6,19:7,20:8,21:9,22:10,23:11
}

HIGH_PH = {3, 6, 9}
DIP_PH  = {7, 11}

def reduce(n: int) -> int:
    while n > 9 and n not in {11, 22}:
        n = sum(int(c) for c in str(n))
    return n

def get_pd(ts: datetime) -> int:
    base = ts.replace(hour=18, minute=15)
    if ts.hour < 18 or (ts.hour == 18 and ts.minute < 15):
        base -= timedelta(days=1)
    py = reduce(3 + 1 + base.year)
    pm = reduce(py + base.month)
    return reduce(pm + base.day)

def get_ph(h: int, pd: int) -> int:
    ph = pd + HOUR_VALUES[h]
    return ph if ph in {11, 22} else reduce(ph)

def fmt_hour(h: int) -> str:
    return f"{h % 12 or 12}{'am' if h < 12 else 'pm'}"

def bombcode_day(day: int) -> int:
    return reduce(day)

def bombcode_full(month: int, day: int, year: int) -> int:
    return reduce(month + day + year)

def classify(day_bc: int, full_bc: int) -> str:
    if day_bc in {3, 5, 6, 7, 8, 9}:
        return "High" if day_bc in {3, 7, 5, 9} else "Low"
    return ("High" if full_bc in {3, 7, 5, 9} else
            "Low"  if full_bc in {6, 8} else "None")

# ────────────────────────────────────────────────
def generate_signals(start_date: datetime.date, end_date: datetime.date):
    # Step 1: Collect all hourly data
    hourly = []
    cur = datetime(start_date.year, start_date.month, start_date.day)
    while cur.date() <= end_date:
        pd = get_pd(cur)
        ph = get_ph(cur.hour, pd)
        hourly.append({
            'date': cur.date(),
            'time': fmt_hour(cur.hour),
            'ph':   ph,
            'is_high': ph in HIGH_PH,
            'is_dip':  ph in DIP_PH,
        })
        cur += timedelta(hours=1)

    # Step 2: Aggregate per day
    daily = {}
    for h in hourly:
        d = h['date']
        if d not in daily:
            bc_d = bombcode_day(d.day)
            bc_f = bombcode_full(d.month, d.day, d.year)
            daily[d] = {
                'str':  d.strftime("%A, %B %d, %Y"),
                'cls':  classify(bc_d, bc_f),
                'high_times': [],
                'dip_times':  [],
            }
        if h['is_high']:
            daily[d]['high_times'].append(h['time'])
        if h['is_dip']:
            daily[d]['dip_times'].append(h['time'])

    # Step 3: Prepare next High/Low lookup
    dates = sorted(daily.keys())
    next_high = {}
    next_low  = {}
    for i, d in enumerate(dates):
        for j in range(i + 1, len(dates)):
            if daily[dates[j]]['cls'] == 'High' and d not in next_high:
                next_high[d] = dates[j]
            if daily[dates[j]]['cls'] == 'Low' and d not in next_low:
                next_low[d] = dates[j]

    # Step 4: Build signals with entry/exit logic
    active_longs = []
    active_shorts = {}  # date → exit date

    lines = []

    for date in dates:
        data = daily[date]
        cls = data['cls']
        sig_parts = []

        sorted_high = sorted(data['high_times'])
        sorted_dip  = sorted(data['dip_times'])

        # BUY / LONG entry (on Low days)
        if cls == "Low" and sorted_dip:
            hold_until = next_high.get(date)
            hold_str = hold_until.strftime("%b %d") if hold_until else "—"
            buys = ", ".join(sorted_dip)
            sig_parts.append(f"**LONG** at {buys} → hold until \~{hold_str}")
            active_longs.append(date)

        # SHORT entry (on High days)
        if cls == "High" and sorted_high:
            exit_d = next_low.get(date)
            exit_str = exit_d.strftime("%b %d") if exit_d else "—"
            shorts = ", ".join(sorted_high)
            if shorts:
                sig_parts.append(f"**SHORT** at {shorts} → exit \~{exit_str}")
                active_shorts[date] = exit_d

        # EXIT LONG (when we hit a High day)
        if cls == "High" and active_longs:
            from_dates = ", ".join([d.strftime("%b %d") for d in set(active_longs)])
            sig_parts.append(f"**EXIT LONG** from {from_dates}")
            active_longs = []

        # EXIT SHORT (when we hit the planned Low day)
        exiting = [e for e, ex in active_shorts.items() if ex == date]
        if exiting and sorted_dip:
            from_dates = ", ".join([e.strftime("%b %d") for e in exiting])
            dips = ", ".join(sorted_dip)
            sig_parts.append(f"**EXIT SHORT** from {from_dates} at {dips}")
            for e in exiting:
                active_shorts.pop(e, None)

        signal = " | ".join(sig_parts) if sig_parts else "— no signal —"

        lines.append(f"**{data['str']}**")
        lines.append(f"→ {signal}")
        lines.append("")

    return "\n".join(lines)

# ────────────────────────────────────────────────
#               STREAMLIT UI
# ────────────────────────────────────────────────

st.title("₿ #CRYPTOSIGN #STOCKSIGN Signals")
st.caption("Version 2.2")

st.markdown("""
**Legend**  
🟢 **LONG**  → entry windows + suggested hold  
🔴 **SHORT** → entry windows + suggested exit  
**EXIT**    → close previous position(s)
""")

col1, col2 = st.columns(2)

with col1:
    default_start = datetime.now().date() - timedelta(days=10)
    start_input = st.date_input(
        "Start date",
        value=default_start,
        min_value=datetime(2009, 1, 4).date(),
        max_value=datetime.now().date()
    )

with col2:
    default_end = datetime.now().date() + timedelta(days=30)
    end_input = st.date_input(
        "End date",
        value=default_end,
        min_value=start_input,
        max_value=datetime(2031, 12, 31).date()
    )

if start_input > end_input:
    st.error("End date must be after start date.")
    st.stop()

if st.button("Generate Signals", type="primary", use_container_width=True):
    with st.spinner("Calculating BTC-anchored bombcode signals..."):
        output = generate_signals(start_input, end_input)

    st.markdown("### Signals")
    st.markdown(output)

    st.download_button(
        label="Download as .txt",
        data=output,
        file_name=f"bombcode_{start_input}_to_{end_input}.txt",
        mime="text/plain"
    )
