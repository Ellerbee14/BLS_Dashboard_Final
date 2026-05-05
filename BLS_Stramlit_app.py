import streamlit as st
import pandas as pd
import os
import inspect
from datetime import datetime

st.set_page_config(page_title="BLS Dashboard", layout="wide")

GITHUB_CSV_URL = ("https://raw.githubusercontent.com/Ellerbee14/BLS_Dashboard_Final/main/bls_data.csv")

SERIES_NAMES = {
    "LNS11000000": "Civilian Labor Force",
    "LNS13000000": "Civilian Unemployment",
    "LNS14000000": "Unemployment Rate",
    "LNS12000000": "Civilian Employment",
    "CES0000000001": "Total Nonfarm Employment",}

METRICS = [
    ("Civilian Labor Force", "Civilian Labor Force", "#29b5e8"),
    ("Civilian Unemployment", "Civilian Unemployment", "#FF9F36"),
    ("Unemployment Rate", "Unemployment Rate", "#D45B90"),
    ("Civilian Employment", "Civilian Employment", "#7D44CF"),
    ("Total Nonfarm Employment", "Total Nonfarm Employment", "#2ECC71"), ]

_CONTAINER_SUPPORTS_BORDER = "border" in inspect.signature(st.container).parameters

def _container_kwargs():
    return {"border": True} if _CONTAINER_SUPPORTS_BORDER else {}

def safe_bar_chart(df, *, y=None, color=None, height=150):
    try:
        st.bar_chart(df, y=y, color=color, height=height)
    except TypeError:
        st.bar_chart(df, y=y, height=height)

def safe_area_chart(df, *, y=None, color=None, height=150):
    try:
        st.area_chart(df, y=y, color=color, height=height)
    except TypeError:
        st.area_chart(df, y=y, height=height)

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
        else 4).to_numpy()
    y_adj = y.copy()
    y_adj[m == 1] -= 1
    return pd.PeriodIndex(
        [f"{yy}Q{qq}" for yy, qq in zip(y_adj, q)], freq="Q")

def aggregate_for_timeframe(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    value_cols = list(SERIES_NAMES.values())

    if timeframe == "Daily":
        out = df.set_index("date")[value_cols]
    elif timeframe == "Weekly":
        out = (
            df.set_index("date")[value_cols]
              .resample("W-MON", label="left", closed="left")
              .mean())
    elif timeframe == "Monthly":
        out = df.set_index("date")[value_cols].resample("M").mean()
    elif timeframe == "Quarterly":
        df["CUSTOM_Q"] = custom_quarter_period(df["date"])
        out = df.groupby("CUSTOM_Q")[value_cols].mean()
    else:
        raise ValueError("Unknown timeframe")
    return out.sort_index()

def metric_card(col, title, df_idxed, column, color, chart_type, timeframe):
    with col:
        with st.container(**_container_kwargs()):
            s = df_idxed[column]
            last_val = s.dropna().iloc[-1] if s.dropna().size else None
            delta, delta_pct = calc_delta(s)
            is_rate = "Rate" in column
            val_str = format_with_commas(
                last_val, decimals=2 if is_rate else 0)
            delta_str = (
                f"{delta:+,.2f} ({delta_pct:+.2f}%)"
                if is_rate
                else f"{delta:+,.0f} ({delta_pct:+.2f}%)" )
            st.metric(title, val_str, delta=delta_str)

            chart_df = s.to_frame(name=column)
            if timeframe == "Quarterly":
                chart_df.index = chart_df.index.astype(str)
            if chart_type == "Bar":
                safe_bar_chart(chart_df, y=column, color=color, height=150)
            else:
                safe_area_chart(chart_df, y=column, color=color, height=150)

@st.cache_data(show_spinner="Loading BLS data…")
def fetch_and_process_bls(startyear: int, endyear: int):
    errors = []
    try:
        df = pd.read_csv(GITHUB_CSV_URL, parse_dates=["date"])
    except Exception as e:
        errors.append(f"GitHub load failed: {e}")
        return None, errors

    df = (
        df.pivot(index="date", columns="series_name", values="value")
          .reset_index())

    df = df.sort_values("date")
    df = df[
        (df["date"].dt.year >= startyear) &
        (df["date"].dt.year <= endyear)]

    if df.empty:
        return None, [f"No rows found between {startyear} and {endyear}"]
    for name in SERIES_NAMES.values():
        if name not in df.columns:
            errors.append(f"Missing column after pivot: {name}")

    return df.reset_index(drop=True), errors

st.title("BLS Dashboard")
today_year = datetime.now().year

with st.sidebar:
    start_year = st.number_input(
        "Start year", 1900, today_year, 2014)
    end_year = st.number_input(
        "End year", 1900, today_year, today_year)
    time_frame = st.selectbox(
        "Select time frame",
        ("Daily", "Weekly", "Monthly", "Quarterly"),)
    chart_selection = st.selectbox(
        "Select chart type", ("Bar", "Area"))

combined_df, load_errors = fetch_and_process_bls(start_year, end_year)

if load_errors:
    with st.expander("Data load diagnostics"):
        for err in load_errors:
            st.write(err)

if combined_df is None or combined_df.empty:
    st.error("No data available.")
    st.stop()

df_display = aggregate_for_timeframe(combined_df, time_frame)

st.subheader("All Data: Current and Change")
cols = st.columns(len(METRICS))
for col, (title, column, color) in zip(cols, METRICS):
    metric_card(
        col,
        title,
        df_display,
        column,
        color,
        chart_selection,
        time_frame,)

st.markdown("### Combined Data Table")
st.dataframe(combined_df, use_container_width=True)
