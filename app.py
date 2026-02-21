# app.py
import streamlit as st
from datetime import datetime, timedelta

st.set_page_config(
    page_title="#CRYPTOSIGN #STOCKSIGN Signals",
    page_icon="₿",
    layout="wide"
)

# ────────────────────────────────────────────────
#   === HOUR VALUES ===
# ────────────────────────────────────────────────
HOUR_VALUES = {
    0:12,1:1,2:2,3:3,4:4,5:5,6:6,7:7,8:8,9:9,10:10,11:11,
    12:12,13:1,14:2,15:3,16:4,17:5,18:6,19:7,20:8,21:9,22:10,23:11
}

# ────────────────────────────────────────────────
#   === YOUR SECRET TUNING === (never shown to users)
# ────────────────────────────────────────────────
BTC_BIRTH = datetime(2009, 1, 3, 18, 15)

HIGH_PH = {3,6,9}            # SHORT direction
LOW_PH  = {7,11}              # LONG / BUY direction

HIGH_DAY_UD = {1,3, 5, 6, 7, 9}  # Only allow SHORT on these days
LOW_DAY_UD  = {2, 4,6,22,11, 8}        # Only allow LONG on these days
# ────────────────────────────────────────────────

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
    total = pd + HOUR_VALUES[h]
    return total if total in {11, 22} else reduce(total)

def universal_day_number(date: datetime.date) -> int:
    total = date.day + date.month + date.year
    return reduce(total)

def classify_day(ud: int) -> str:
    if ud in HIGH_DAY_UD:
        return "High"
    if ud in LOW_DAY_UD:
        return "Low"
    return "None"

def fmt_hour(h: int) -> str:
    ampm = 'am' if h < 12 else 'pm'
    hour12 = h % 12 or 12
    return f"{hour12}{ampm}"

# ────────────────────────────────────────────────
def generate_signals(start_date: datetime.date, end_date: datetime.date):
    daily = {}
    current = datetime(start_date.year, start_date.month, start_date.day)

    while current.date() <= end_date:
        d = current.date()
        ud = universal_day_number(d)
        day_type = classify_day(ud)

        high_times = []
        low_times  = []

        for hour in range(24):
            ts = datetime(d.year, d.month, d.day, hour)
            pd = get_pd(ts)
            ph = get_ph(hour, pd)
            time_str = fmt_hour(hour)

            if ph in HIGH_PH:
                high_times.append((hour, time_str))
            if ph in LOW_PH:
                low_times.append((hour, time_str))

        daily[d] = {
            'str': d.strftime("%A, %B %d, %Y"),
            'day_type': day_type,
            'high_times': high_times,
            'low_times': low_times,
        }

        current += timedelta(days=1)

    # ── Build clean output (no internals shown) ────────────────
    lines = []

    for date in sorted(daily.keys()):
        data = daily[date]

        sorted_low  = [t for _, t in sorted(data['low_times'])]
        sorted_high = [t for _, t in sorted(data['high_times'])]

        parts = []
        if data['day_type'] == "Low" and sorted_low:
            parts.append(f"**LONG** at {', '.join(sorted_low)}")
        elif data['day_type'] == "High" and sorted_high:
            parts.append(f"**SHORT** at {', '.join(sorted_high)}")

        signal = " | ".join(parts) if parts else "— no signal —"

        lines.append(f"**{data['str']}**")
        lines.append(f"→ {signal}")
        lines.append("")

    return "\n".join(lines)

# ────────────────────────────────────────────────
#               STREAMLIT UI
# ────────────────────────────────────────────────

st.title("₿ BTC-Anchored Trading Signals")
st.caption("Version 1.0")

st.markdown("""
**Legend**  
🟢 **LONG** → potential buy / accumulation windows  
🔴 **SHORT** → potential high / distribution windows
""")

col1, col2 = st.columns(2)

with col1:
    default_start = datetime.now().date() - timedelta(days=7)
    start_input = st.date_input(
        "Start date",
        value=default_start,
        min_value=datetime(2009,1,4).date(),   # after BTC birth
        max_value=datetime.now().date()
    )

with col2:
    default_end = datetime.now().date() + timedelta(days=21)
    end_input = st.date_input(
        "End date",
        value=default_end,
        min_value=start_input,
        max_value=datetime(2031,12,31).date()
    )

if start_input > end_input:
    st.error("End date must be after start date.")
    st.stop()

if st.button("Generate Signals", type="primary", use_container_width=True):
    with st.spinner("Calculating BTC-anchored signals..."):
        output = generate_signals(start_input, end_input)

    st.markdown("### Signals")
    st.markdown(output)

    st.download_button(
        label="Download results (.txt)",
        data=output,
        file_name=f"btc_signals_{start_input}_to_{end_input}.txt",
        mime="text/plain"
    )

# ────────────────────────────────────────────────
#   Nothing explanatory below this line
# ────────────────────────────────────────────────
