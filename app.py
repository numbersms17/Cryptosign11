# app.py
import streamlit as st
from datetime import datetime, timedelta

st.set_page_config(
    page_title="Crypto/Stock Numerology Signals",
    page_icon="📈",
    layout="wide"
)

# ────────────────────────────────────────────────
#   HOUR VALUES (0-23 → numerology vibration)
# ────────────────────────────────────────────────
HOUR_VALUES = {
    0:12, 1:1,  2:2,  3:3,  4:4,  5:5,  6:6,
    7:7,  8:8,  9:9, 10:10, 11:11,
   12:12,13:1, 14:2, 15:3, 16:4, 17:5, 18:6,
   19:7, 20:8, 21:9, 22:10,23:11
}

# ────────────────────────────────────────────────
#   === YOUR SECRET TUNING === (do NOT expose these)
# ────────────────────────────────────────────────
HIGH_DAY_UD = {1, 3, 5, 6, 7, 9}       # Short / high energy days
LOW_DAY_UD  = {2, 4, 6, 8, 11, 22}     # Buy / long / dip days

HIGH_UH = {1, 9}     # SHORT targets
LOW_UH  = {8, 9}     # LONG / BUY targets
# ────────────────────────────────────────────────

def reduce(n: int) -> int:
    while n > 9 and n not in {11, 22}:
        n = sum(int(c) for c in str(n))
    return n

def universal_day_number(date: datetime.date) -> int:
    total = date.day + date.month + date.year
    return reduce(total)

def universal_hour_number(hour: int, ud: int) -> int:
    total = ud + HOUR_VALUES[hour]
    return total if total in {11, 22} else reduce(total)

def fmt_hour(h: int) -> str:
    ampm = 'am' if h < 12 else 'pm'
    hour12 = h % 12 or 12
    return f"{hour12}{ampm}"

def classify_day(ud: int) -> str:
    if ud in HIGH_DAY_UD:
        return "High"
    if ud in LOW_DAY_UD:
        return "Low"
    return "None"

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
            uh = universal_hour_number(hour, ud)
            time_label = fmt_hour(hour)

            if uh in HIGH_UH:
                high_times.append((hour, time_label))
            if uh in LOW_UH:
                low_times.append((hour, time_label))

        daily[d] = {
            'str': d.strftime("%A, %B %d, %Y"),
            'ud': ud,
            'day_type': day_type,
            'high_times': high_times,
            'low_times': low_times,
        }

        current += timedelta(days=1)

    # Prepare display lines
    lines = []

    for date in sorted(daily.keys()):
        data = daily[date]
        day_type = data['day_type']

        sorted_low  = [t for _, t in sorted(data['low_times'])]
        sorted_high = [t for _, t in sorted(data['high_times'])]

        parts = []
        if day_type == "Low" and sorted_low:
            parts.append(f"**LONG** at {', '.join(sorted_low)}")
        elif day_type == "High" and sorted_high:
            parts.append(f"**SHORT** at {', '.join(sorted_high)}")

        signal = " | ".join(parts) if parts else "— no signal —"

        lines.append(f"**{data['str']}**  (UD: {data['ud']})")
        lines.append(f"→ {signal}")
        lines.append("")

    return "\n".join(lines)

# ────────────────────────────────────────────────
#               STREAMLIT UI
# ────────────────────────────────────────────────

st.title("📈 Numerology Trading Signals")
st.caption("Version 1.1 – based on Universal Day & Hour vibrations")

st.markdown("""
**Legend**  
🟢 **LONG** → potential buy / dip / accumulation hours  
🔴 **SHORT** → potential high / reversal / distribution hours
""")

col1, col2 = st.columns([1,1])

with col1:
    default_start = datetime.now().date() - timedelta(days=10)
    start_input = st.date_input(
        "Start date",
        value=default_start,
        min_value=datetime(2000,1,1).date(),
        max_value=datetime.now().date()
    )

with col2:
    default_end = datetime.now().date() + timedelta(days=14)
    end_input = st.date_input(
        "End date",
        value=default_end,
        min_value=start_input,
        max_value=datetime(2030,12,31).date()
    )

if start_input > end_input:
    st.error("End date must be after start date.")
    st.stop()

if st.button("Generate Signals", type="primary", use_container_width=True):
    with st.spinner("Calculating universal days & hours..."):
        output = generate_signals(start_input, end_input)

    st.markdown("### Signals")
    st.markdown(output)

    st.download_button(
        label="Download as .txt",
        data=output,
        file_name=f"signals_{start_input}_to_{end_input}.txt",
        mime="text/plain"
    )

# ────────────────────────────────────────────────
#   No more exposed sets / rules below this line
# ────────────────────────────────────────────────
