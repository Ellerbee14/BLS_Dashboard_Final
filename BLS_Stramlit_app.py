import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

st.set_page_config(page_title="BLS Dashboard", layout="wide")

BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
HEADERS = {"Content-type": "application/json"}

SERIES_NAMES = {
    "LNS11000000": "Civilian Labor Force",
    "LNS13000000": "Civilian Unemployment",
    "LNS14000000": "Unemployment Rate",
    "LNS12000000": "Civilian Employment",
    "CES0000000001": "Total Nonfarm Employment",}
SERIES_IDS = list(SERIES_NAMES.keys())

METRICS = [
    ("Civilian Labor Force", "Civilian Labor Force", "#29b5e8"),
    ("Civilian Unemployment", "Civilian Unemployment", "#FF9F36"),
    ("Unemployment Rate", "Unemployment Rate", "#D45B90"),
    ("Civilian Employment", "Civilian Employment", "#7D44CF"),
    ("Total Nonfarm Employment", "Total Nonarm Employment", "#2ECC71"),]
METRICS[-1] = ("Total Nonfarm Employment", "Total Nonfarm Employment", "#2ECC71")

def format_with_commas(x, decimals=None):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "—"
    if decimals is None:
        return f"{x:,.0f}"
    return f"{x:,.{decimals}f}"

def calc_delta(series: pd.Series):
    s = series.ffill()
    if len(s) < 2:
        return 0.0, 0.0
    cur = s.iloc[-1]
    prev = s.iloc[-2]
    delta = cur - prev
    delta_pct = (delta / prev) * 100 if prev != 0 else 0.0
    return float(delta), float(delta_pct)

def custom_quarter_period(dts: pd.Series) -> pd.PeriodIndex:
    dt = pd.to_datetime(dts)
    y = dt.dt.year.to_numpy()
    m = dt.dt.month.to_numpy()

    q = pd.Series(m).map(
        lambda mm: 1 if mm in (2, 3, 4)
        else 2 if mm in (5, 6, 7)
        else 3 if mm in (8, 9, 10)
        else 4
    ).to_numpy()
    y_adj = y.copy()
    y_adj[m == 1] = y_adj[m == 1] - 1

    return pd.PeriodIndex([f"{yy}Q{qq}" for yy, qq in zip(y_adj, q)], freq="Q")

def aggregate_for_timeframe(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    df = df.copy()
    df["DATE"] = pd.to_datetime(df["DATE"])
    df = df.sort_values("DATE")

    value_cols = list(SERIES_NAMES.values())
    if timeframe == "Daily":
        out = df.set_index("DATE")[value_cols]

    elif timeframe == "Weekly":
        out = (
            df.set_index("DATE")[value_cols]
              .resample("W-MON", label="left", closed="left")
              .mean())

    elif timeframe == "Quarterly":
        df["CUSTOM_Q"] = custom_quarter_period(df["DATE"])
        out = df.groupby("CUSTOM_Q")[value_cols].mean()
    else:
        raise ValueError("Unknown timeframe")
    return out

def metric_card(col, title, df_idxed, column, color, chart_type, timeframe):
    with col:
        with st.container(border=True):
            s = df_idxed[column]
            last_val = s.dropna().iloc[-1] if s.dropna().size else None
            delta, delta_pct = calc_delta(s)

            is_rate = "Rate" in column
            val_str = format_with_commas(last_val, decimals=2 if is_rate else 0)

            delta_str = (
                f"{delta:+,.2f} ({delta_pct:+.2f}%)" if is_rate
                else f"{delta:+,.0f} ({delta_pct:+.2f}%)")
            st.metric(title, val_str, delta=delta_str)
            chart_df = s.to_frame(name=column)

            if timeframe == "Quarterly":
                chart_df = chart_df.copy()
                chart_df.index = chart_df.index.astype(str)

            if chart_type == "Bar":
                st.bar_chart(chart_df, y=column, color=color, height=150)
            else:
                st.area_chart(chart_df, y=column, color=color, height=150)


def metric_card(col, title, df_idxed, column, color, chart_type, timeframe):
    with col:
        with st.container(border=True):
            s = df_idxed[column]
            last_val = s.dropna().iloc[-1] if s.dropna().size else None
            delta, delta_pct = calc_delta(s)

            is_rate = "Rate" in column
            val_str = format_with_commas(last_val, decimals=2 if is_rate else 0)

            delta_str = (
                f"{delta:+,.2f} ({delta_pct:+.2f}%)" if is_rate
                else f"{delta:+,.0f} ({delta_pct:+.2f}%)" )
            st.metric(title, val_str, delta=delta_str)
            chart_df = s.to_frame(name=column)

            if timeframe == "Quarterly":
                chart_df = chart_df.copy()
                chart_df.index = chart_df.index.astype(str)

            if chart_type == "Bar":
                st.bar_chart(chart_df, y=column, color=color, height=150)
            else:
                st.area_chart(chart_df, y=column, color=color, height=150)

@st.cache_data(ttl="1d")
def fetch_and_process_bls(series_ids, startyear: int, endyear: int):
    payload = {
        "seriesid": series_ids,
        "startyear": str(startyear),
        "endyear": str(endyear),}

    r = requests.post(
        BLS_URL,
        headers=HEADERS,
        json=payload,      
        timeout=30)
    r.raise_for_status()
    js = r.json()

    if js.get("status") != "REQUEST_SUCCEEDED":
        msg = js.get("message", ["Unknown error"])
        raise RuntimeError(f"BLS API error: {msg}")

    rows = []
    for series in js["Results"]["series"]:
        sid = series["seriesID"]
        for item in series["data"]:
            period = item.get("period", "")
            if not (period.startswith("M") and period[1:].isdigit()):
                continue
            month = int(period[1:])
            if month < 1 or month > 12:
                continue

            year = int(item["year"])
            value = float(item["value"])
            date = pd.Timestamp(year=year, month=month, day=1)

            rows.append({"DATE": date, "seriesID": sid, "value": value})

    long_df = pd.DataFrame(rows)
    if long_df.empty:
        raise RuntimeError("No monthly data returned from BLS API.")

    wide = (
        long_df.pivot_table(index="DATE", columns="seriesID", values="value", aggfunc="mean")
               .rename(columns=SERIES_NAMES)
               .sort_index()
               .reset_index())
    dfs = {}
    for sid, name in SERIES_NAMES.items():
        tmp = long_df[long_df["seriesID"] == sid][["DATE", "value"]].copy()
        tmp = tmp.sort_values("DATE").rename(columns={"value": name})
        dfs[sid] = tmp

    return wide, dfs

st.title("BLS Dashboard")
st.write("Labor statistics collected from the BLS Public Data API.")
st.write("Civilian Labor Force, Civilian Unemploment, Civilian Employment, and Nonfarm Employment listed in thousands.")
today_year = datetime.now().year
default_start_year = 2014
default_end_year = min(today_year, 2026)

with st.sidebar:
    st.title("BLS Dashboard")
    st.header("Settings")

    start_year = st.number_input("Start year", min_value=1900, max_value=today_year, value=default_start_year, step=1)
    end_year = st.number_input("End year", min_value=1900, max_value=today_year, value=default_end_year, step=1)
    time_frame = st.selectbox("Select time frame", ("Daily", "Weekly", "Monthly", "Quarterly"))
    chart_selection = st.selectbox("Select chart type", ("Bar", "Area"))

combined_df, dataframes_dict = fetch_and_process_bls(SERIES_IDS, int(start_year), int(end_year))

df = combined_df.copy()
min_date = df["DATE"].min().date()
max_date = df["DATE"].max().date()

with st.sidebar:
    default_start_date = max(max_date - timedelta(days=365), min_date)
    default_end_date = max_date

    start_date = st.date_input("Start date", default_start_date, min_value=min_date, max_value=max_date)
    end_date = st.date_input("End date", default_end_date, min_value=min_date, max_value=max_date)

if start_date > end_date:
    start_date, end_date = end_date, start_date

df_display = aggregate_for_timeframe(df, time_frame)

st.subheader("All Data: Current and Change")

cols = st.columns(len(METRICS))
for col, (title, column, color) in zip(cols, METRICS):
    metric_card(col, title, df_display, column, color, chart_selection, time_frame)

st.subheader("Filtered Tenors")

if time_frame == "Quarterly":
    start_q = custom_quarter_period(pd.Series([pd.Timestamp(start_date)])).iloc[0]
    end_q = custom_quarter_period(pd.Series([pd.Timestamp(end_date)])).iloc[0]
    mask = (df_display.index >= start_q) & (df_display.index <= end_q)

elif time_frame == "Monthly":
    start_m = pd.Timestamp(start_date).to_period("M").to_timestamp("M")
    end_m = pd.Timestamp(end_date).to_period("M").to_timestamp("M")
    mask = (df_display.index >= start_m) & (df_display.index <= end_m)
else:
    mask = (df_display.index >= pd.Timestamp(start_date)) & (df_display.index <= pd.Timestamp(end_date))

df_filtered = df_display.loc[mask]

cols = st.columns(len(METRICS))
for col, (title, column, color) in zip(cols, METRICS):
    with col:
        with st.container(border=True):
            s = df_filtered[column].dropna()
            avg_val = s.mean() if not s.empty else None
            is_rate = "Rate" in column
            st.metric(f"{title} (avg)", format_with_commas(avg_val, decimals=2 if is_rate else 0))
            chart_df = df_filtered[[column]].copy()
            if time_frame == "Quarterly":
                chart_df.index = chart_df.index.astype(str)
            if chart_selection == "Bar":
                st.bar_chart(chart_df, y=column, color=color, height=150)
            else:
                st.area_chart(chart_df, y=column, color=color, height=150)

with st.expander("See DataFrame (selected time frame)"):
    st.dataframe(df_filtered.reset_index().rename(columns={"index": "PERIOD"}), use_container_width=True)

st.markdown("### Combined Data Table")
st.dataframe(combined_df, height=500, use_container_width=True)

@st.cache_data(ttl="1d")
def to_csv_bytes(df_):
    return df_.to_csv(index=False).encode("utf-8")

st.markdown("### Download Data as CSV")

st.download_button(
    label="Download Combined Data",
    data=to_csv_bytes(combined_df),
    file_name="complete_bls_data.csv",
    mime="text/csv",)

st.subheader("Individual Data Series")
for series_id, df_one in dataframes_dict.items():
    st.download_button(
        label=f"Download {SERIES_NAMES[series_id]}",
        data=to_csv_bytes(df_one),
        file_name=f"{SERIES_NAMES[series_id].replace(' ', '_').lower()}.csv",
        mime="text/csv",)

with st.expander("Raw Data Tables"):
    for series_id, df_one in dataframes_dict.items():
        st.subheader(SERIES_NAMES[series_id])
        st.dataframe(df_one, use_container_width=True)
