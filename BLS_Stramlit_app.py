
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="BLS Dashboard", layout="wide")

GITHUB_CSV_URL = "https://raw.githubusercontent.com/Ellerbee14/BLS_Dashboard_Final/main/bls_data.csv"

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
    ("Total Nonfarm Employment", "Total Nonfarm Employment", "#2ECC71"),]

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
    elif timeframe == "Monthly":
        out = df.set_index("DATE")[value_cols].resample("M").mean()
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
                f"{delta:+,.2f} ({delta_pct:+.2f}%)"
                if is_rate else f"{delta:+,.0f} ({delta_pct:+.2f}%)")

            st.metric(title, val_str, delta=delta_str)
            chart_df = s.to_frame(name=column)
            if timeframe == "Quarterly":
                chart_df.index = chart_df.index.astype(str)
            if chart_type == "Bar":
                st.bar_chart(chart_df, y=column, color=color, height=150)
            else:
                st.area_chart(chart_df, y=column, color=color, height=150)

@st.cache_data
def fetch_and_process_bls(series_ids, startyear: int, endyear: int):
    path = "bls_data.csv"
    if not os.path.exists(path):
        return None, None
    df = pd.read_csv(path, parse_dates=["DATE"])
    df = df.sort_values("DATE")
    df = df[
        (df["DATE"].dt.year >= startyear) &
        (df["DATE"].dt.year <= endyear)]

    if df.empty:
        return None, None

    dfs = {}
    for sid, name in SERIES_NAMES.items():
        if name not in df.columns:
            raise ValueError(f"Missing column in CSV: {name}")
        dfs[sid] = df[["DATE", name]].copy()

    return df.reset_index(drop=True), dfs

st.title("BLS Dashboard")

today_year = datetime.now().year
default_start_year = 2014
default_end_year = min(today_year, 2026)

with st.sidebar:
    start_year = st.number_input("Start year", 1900, today_year, default_start_year)
    end_year = st.number_input("End year", 1900, today_year, default_end_year)
    time_frame = st.selectbox("Select time frame", ("Daily", "Weekly", "Monthly", "Quarterly"))
    chart_selection = st.selectbox("Select chart type", ("Bar", "Area"))

combined_df, dataframes_dict = fetch_and_process_bls(SERIES_IDS, start_year, end_year)

df_display = aggregate_for_timeframe(combined_df, time_frame)

st.subheader("All Data: Current and Change")
cols = st.columns(len(METRICS))
for col, (title, column, color) in zip(cols, METRICS):
    metric_card(col, title, df_display, column, color, chart_selection, time_frame)

st.markdown("### Combined Data Table")
st.dataframe(combined_df, use_container_width=True)
