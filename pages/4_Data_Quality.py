import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from src.filtering import apply_filters, get_map_data, prepare_base


df = pd.read_csv("data/processed/clean_sales_pipeline.csv")

# Final coordinates
df["lat_final"] = df["latitude_gps"].combine_first(df["latitude_clean"])
df["lon_final"] = df["longitude_gps"].combine_first(df["longitude_clean"])

st.set_page_config(
    page_title="Data Quality",
    layout="wide"
)


st.title("Data Quality & Reliability")

def format_currency(value):

    if pd.isna(value):
        return "0"

    if value >= 1_000_000_000:
        return f"{value/1_000_000_000:.1f}B"
    elif value >= 1_000_000:
        return f"{value/1_000_000:.1f}M"
    elif value >= 1_000:
        return f"{value/1_000:.1f}K"
    else:
        return f"{value:.0f}"

#sidebar filters
#prepare base for filters
df_ui = prepare_base(df)

st.sidebar.header("Filters")

#sliders
min_rev, max_rev = st.sidebar.slider(
    "Revenue (GHS)",
    0,
    int(df_ui["TCV (GHS)"].max()),
    (0, int(df_ui["TCV (GHS)"].max()))
)

st.sidebar.caption(
    f"Selected: {format_currency(min_rev)} → {format_currency(max_rev)}"
)

min_dist, max_dist = st.sidebar.slider(
    "Distance (m)",
    0,
    int(df_ui["Distance (m)"].max()),
    (0, int(df_ui["Distance (m)"].max()))
)

st.sidebar.caption(
    f"Selected: {format_currency(min_dist)}m → {format_currency(max_dist)}m"
)


##region filter
regions = sorted(df_ui["Region"].dropna().unique())

select_all_regions = st.sidebar.checkbox("Select All Regions", value=True)

if select_all_regions:
    region_filter = regions
else:
    region_filter = st.sidebar.multiselect("Region", options=regions)

#service filter
services = sorted(df_ui["Service"].dropna().unique())

select_all_services = st.sidebar.checkbox("Select All Services", value=True)

if select_all_services:
    service_filter = services
else:
    service_filter = st.sidebar.multiselect("Service", options=services)

#deal status filter
status_options = ["All", "Open Pipeline", "Closed Won"]

status_filter = st.sidebar.selectbox(
    "Deal Status",
    options=status_options
)

#validation checks
if not region_filter:
    st.warning("Select at least one region")
    st.stop()

if not service_filter:
    st.warning("Select at least one service")
    st.stop()
#apply global filters
filtered_df, filtered_time_df = apply_filters(
    df,
    region=region_filter,
    service=service_filter,
    status=status_filter,
    min_rev=min_rev,
    max_rev=max_rev,
    min_dist=min_dist,
    max_dist=max_dist
)

# ================================
# DATA QUALITY LOGIC
# ================================

df = filtered_df.copy()

# Ensure numeric types
df["lat_final"] = pd.to_numeric(df["lat_final"], errors="coerce")
df["lon_final"] = pd.to_numeric(df["lon_final"], errors="coerce")
df["Build Cost (GHS)"] = pd.to_numeric(df["Build Cost (GHS)"], errors="coerce")
df["expected_revenue"] = pd.to_numeric(df["expected_revenue"], errors="coerce")
df["Probability"] = pd.to_numeric(df["Probability"], errors="coerce")
df["payback_months"] = pd.to_numeric(df["payback_months"], errors="coerce")


# ================================
# COORDINATE QUALITY RULES
# ================================

missing_coords = df["lat_final"].isna() | df["lon_final"].isna()

invalid_coords = (
    (df["lat_final"] == 0) |
    (df["lon_final"] == 0) |
    (df["lat_final"].abs() > 90) |
    (df["lon_final"].abs() > 180)
)

out_of_bounds = (
    (df["lat_final"] < 4.5) | (df["lat_final"] > 11.5) |
    (df["lon_final"] < -3.5) | (df["lon_final"] > 1.5)
)

df["coord_issue"] = "Valid"
df.loc[missing_coords, "coord_issue"] = "Missing"
df.loc[invalid_coords, "coord_issue"] = "Invalid"
df.loc[out_of_bounds, "coord_issue"] = "Out of Bounds"


# ================================
# BUSINESS DATA QUALITY RULES
# ================================

df["data_issue"] = "Clean"

df.loc[df["Build Cost (GHS)"].isna(), "data_issue"] = "Missing Build Cost"
df.loc[df["Build Cost (GHS)"] == 0, "data_issue"] = "Zero Build Cost"
df.loc[df["expected_revenue"].isna(), "data_issue"] = "Missing Revenue"
df.loc[df["Probability"].isna(), "data_issue"] = "Missing Probability"
df.loc[df["payback_months"] <= 0, "data_issue"] = "Invalid Payback"


# ================================
# SUMMARY METRICS (FILTER-AWARE)
# ================================

total_records = len(df)

valid_coords = (df["coord_issue"] == "Valid").sum()
invalid_coords_count = total_records - valid_coords

valid_pct = (valid_coords / total_records) * 100 if total_records > 0 else 0
invalid_pct = 100 - valid_pct

data_reliability_score = valid_pct


# ================================
# KPI DISPLAY
# ================================

st.subheader("Data Quality Overview")

col1, col2, col3, col4 = st.columns(4)

col1.metric("Total Records", total_records)
col2.metric("Valid Coordinates (%)", f"{valid_pct:.1f}%")
col3.metric("Invalid Coordinates (%)", f"{invalid_pct:.1f}%")
col4.metric("Data Reliability Score", f"{data_reliability_score:.1f}%")


# ================================
# COORDINATE ISSUE BREAKDOWN
# ================================

st.subheader("Coordinate Issues Breakdown")

coord_summary = (
    df["coord_issue"]
    .value_counts()
    .reset_index()
)

coord_summary.columns = ["Issue Type", "Count"]

fig1 = px.bar(
    coord_summary,
    x="Issue Type",
    y="Count",
    color="Issue Type",
    title="Coordinate Issue Distribution",
    text="Count"
)
#fig1.update_traces(textposition="outside")
fig1.update_layout(uniformtext_minsize=8, uniformtext_mode="hide")
st.plotly_chart(fig1, use_container_width=True)
st.dataframe(coord_summary, use_container_width=True)


# ================================
# DATA ISSUE BREAKDOWN
# ================================

st.subheader("Business Data Issues")

data_issue_summary = (
    df["data_issue"]
    .value_counts()
    .reset_index()
)

data_issue_summary.columns = ["Issue Type", "Count"]

fig2 = px.bar(
    data_issue_summary,
    x="Issue Type",
    y="Count",
    color="Issue Type",
    title="Business Data Issues",
    text="Count"
)
#fig2.update_traces(textposition="outside")
fig2.update_layout(uniformtext_minsize=8, uniformtext_mode="hide")
st.plotly_chart(fig2, use_container_width=True)
st.dataframe(data_issue_summary, use_container_width=True)


# ================================
# PROBLEM RECORDS
# ================================

st.subheader("Flagged Problem Records")

problem_df = df[
    (df["coord_issue"] != "Valid") |
    (df["data_issue"] != "Clean")
]

st.dataframe(
    problem_df[
        [
            "Site[End User]",
            "ISP",
            "Region",
            "Town",
            "lat_final",
            "lon_final",
            "coord_issue",
            "data_issue",
            "Build Cost (GHS)",
            "expected_revenue",
            "Probability",
            "payback_months"
        ]
    ],
    use_container_width=True
)


# ================================
# DOWNLOAD FOR ENGINEERING TEAM
# ================================

st.download_button(
    label="⬇️ Download Problem Records",
    data=problem_df.to_csv(index=False),
    file_name="data_quality_issues.csv",
    mime="text/csv"
)


# ================================
# EXECUTIVE INTERPRETATION
# ================================

st.subheader("What This Means")

if invalid_pct > 20:
    st.error(
        f"{invalid_pct:.1f}% of records contain coordinate issues. Location-based insights are unreliable and require immediate correction."
    )
elif invalid_pct > 10:
    st.warning(
        f"{invalid_pct:.1f}% of records contain coordinate issues. Data quality improvement is recommended."
    )
else:
    st.success(
        "Coordinate data is reliable. Location-based insights can be trusted."
    )


# ================================
# ENGINEERING ACTION BLOCK
# ================================

st.subheader("Recommended Actions")

st.info(
    """
    • Fix out-of-bounds coordinates (likely incorrect mapping or data entry)
    • Investigate missing GPS values at source
    • Validate zero or missing build cost entries
    • Correct invalid payback values (<= 0)
    • Implement validation rules at data entry level
    • Schedule weekly data quality audits
    """
)