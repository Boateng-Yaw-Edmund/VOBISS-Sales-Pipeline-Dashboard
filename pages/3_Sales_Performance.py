import streamlit as st
import pandas as pd
import plotly.express as px
from src.filtering import apply_filters, get_map_data

st.title("Sales Performance Dashboard")

df = pd.read_csv("data/processed/clean_sales_pipeline.csv")

st.set_page_config(
    page_title="Sales Performance",
    layout="wide"
)

# BANDWIDTH PREP
# -----------------------------
df["Bandwidth (MBPS)"] = pd.to_numeric(
    df["Bandwidth (MBPS)"], errors="coerce"
).fillna(0)

# cap extreme outliers for stability
df["Bandwidth (MBPS)"] = df["Bandwidth (MBPS)"].clip(upper=10000)

# create bandwidth tiers
df["bandwidth_band"] = pd.cut(
    df["Bandwidth (MBPS)"],
    bins=[-1, 10, 50, 150, 500, 2000, float("inf")],
    labels=[
        "Very Low (0-10)",
        "Low (10-50)",
        "Lower-Mid (50-150)",
        "Upper-Mid (150-500)",
        "High (500-2Gb)",
        "Extreme (2Gb+)"
    ]
)
#sidebar filters
st.sidebar.header("Filters")

regions = sorted(df["Region"].dropna().unique())
services = sorted(df["Service"].dropna().unique())

select_all_regions = st.sidebar.checkbox("Select All Regions", value=True)
region_filter = regions if select_all_regions else st.sidebar.multiselect("Region", regions)

select_all_services = st.sidebar.checkbox("Select All Services", value=True)
service_filter = services if select_all_services else st.sidebar.multiselect("Service", services)

#bandwidth filter
bands = sorted(df["bandwidth_band"].dropna().unique())

select_all_bands = st.sidebar.checkbox("Select All Bandwidth Tiers", value=True)

if select_all_bands:
    bandwidth_filter = bands
else:
    bandwidth_filter = st.sidebar.multiselect(
        "Bandwidth Tier",
        options=bands
    )

status_options = ["All", "Open Pipeline", "Closed Won"]
status_filter = st.sidebar.selectbox("Deal Status", status_options)

min_rev, max_rev = st.sidebar.slider(
    "Revenue (GHS)",
    0,
    int(df["TCV (GHS)"].max()),
    (0, int(df["TCV (GHS)"].max()))
)

min_dist, max_dist = st.sidebar.slider(
    "Distance (m)",
    0,
    int(df["Distance (m)"].max()),
    (0, int(df["Distance (m)"].max()))
)

# Safety
if not region_filter or not service_filter:
    st.warning("Select at least one region and service")
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

# apply bandwidth filter
if bandwidth_filter:
    filtered_df = filtered_df[
        filtered_df["bandwidth_band"].isin(bandwidth_filter)
    ]

# ================================
# MoM CALCULATIONS (FIXED)
# ================================

df_time = filtered_df.copy()

# Ensure date is clean
df_time["date"] = pd.to_datetime(df_time["date"], errors="coerce")

# Create proper monthly bucket (datetime, not string)
df_time["year_month"] = df_time["date"].dt.to_period("M")

# Aggregate
monthly_perf = df_time.groupby("year_month").agg(
    revenue=("expected_revenue", "sum"),
    deals=("expected_revenue", "size")  # better than count
).reset_index()

# Convert to timestamp for correct sorting
monthly_perf["year_month"] = monthly_perf["year_month"].dt.to_timestamp()
monthly_perf = monthly_perf.sort_values("year_month")

# Previous values
monthly_perf["revenue_prev"] = monthly_perf["revenue"].shift(1)
monthly_perf["deals_prev"] = monthly_perf["deals"].shift(1)

# Safe division function
def safe_pct_change(current, previous):
    if pd.isna(previous) or previous == 0:
        return 0
    return ((current - previous) / previous) * 100

# Apply safely
monthly_perf["revenue_mom_pct"] = monthly_perf.apply(
    lambda row: safe_pct_change(row["revenue"], row["revenue_prev"]),
    axis=1
)

monthly_perf["deals_mom_pct"] = monthly_perf.apply(
    lambda row: safe_pct_change(row["deals"], row["deals_prev"]),
    axis=1
)

# Get latest valid row (avoid first row issue)
latest = monthly_perf.iloc[-1]

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

#kpi metrics
col1, col2, col3, col4, col5, col6, col7 = st.columns(7)

col1.metric("Total Revenue", f"GHS {format_currency(filtered_df['TCV (GHS)'].sum())}")
col2.metric("Expected Revenue", f"GHS {format_currency(filtered_df['expected_revenue'].sum())}")
col3.metric("Avg Deal Size", f"GHS {format_currency(filtered_df['TCV (GHS)'].mean())}")
col4.metric("Rev / Mbps", f"{format_currency(filtered_df['revenue_per_mbps'].mean())}")
col5.metric("Payback (Months)", f"{filtered_df['payback_months'].mean():.1f}")
col6.metric("MoM Revenue Change", f"{latest['revenue_mom_pct']:.1f}%")
col7.metric("MoM Deal Change", f"{latest['deals_mom_pct']:.1f}%")

tab1, tab2 = st.tabs([
    "Service Performance", "Account Manager Performance"])

with tab1:
    st.subheader("Revenue Contribution by Service")

    service_perf = (
        filtered_df
        .dropna(subset=["Service"])
        .groupby("Service", as_index=False)
        .agg({
            "TCV (GHS)": "sum",
            "expected_revenue": "sum"
        })
        .sort_values("TCV (GHS)", ascending=False)
    )

    fig_service = px.bar(
        service_perf,
        x="Service",
        y="TCV (GHS)",
        color="expected_revenue",
        text="TCV (GHS)"  
    )

    fig_service.update_traces(
        texttemplate="GHS %{text:,.0f}"  
        #textposition="outside"
    )

    fig_service.update_layout(
        uniformtext_minsize=8,
        uniformtext_mode="hide"
    )

    st.plotly_chart(fig_service, use_container_width=True)


   

    #deal size
    st.subheader("Deal Size Distribution")

    # convert to millions for better readability
    filtered_df["Revenue_M"] = filtered_df["TCV (GHS)"] #/ 1_000_000

    fig_size = px.histogram(
        filtered_df,
        x="Revenue_M",
        nbins=30,
        text_auto=True,  
        labels={
            "Revenue_M": "Deal Value (Millions GHS)",
            "count": "Number of Deals"
        },
        title="Distribution of Deal Sizes"
    )

    fig_size.update_layout(
        xaxis_title="Deal Value (Millions GHS)",
        yaxis_title="Number of Deals"
    )

    st.plotly_chart(fig_size, use_container_width=True)

    #expected vs actual revenue
    st.subheader("Expected vs Actual Revenue")

    plot_df = filtered_df.copy()

    plot_df["Probability"] = pd.to_numeric(plot_df["Probability"], errors="coerce").fillna(0)

    fig_expect = px.scatter(
        plot_df,
        x="TCV (GHS)",
        y="expected_revenue",
        color="bandwidth_band",  
        size="Probability",
        opacity=0.6
    )

    st.plotly_chart(fig_expect, use_container_width=True)

    #revenue vs bandwidth
    st.subheader("Revenue vs Bandwidth")

    plot_df["Bandwidth (MBPS)"] = pd.to_numeric(plot_df["Bandwidth (MBPS)"], errors="coerce").fillna(0)

    fig_mbps = px.scatter(
        plot_df,
        x="Bandwidth (MBPS)",
        y="TCV (GHS)",
        color="bandwidth_band",   
        size="TCV (GHS)",
        opacity=0.6
    )

    st.plotly_chart(fig_mbps, use_container_width=True)

    st.write(df["bandwidth_band"].value_counts())


with tab2:

 #account manager performance
    st.subheader("Account Manager Performance")

    manager_perf = (
        filtered_df
        .dropna(subset=["Account Manager"])
        .groupby("Account Manager", as_index=False)
        .agg({
            "TCV (GHS)": ["sum", "mean"],
            "expected_revenue": "sum"
        })
    )

    # flatten columns
    manager_perf.columns = [
        "Account Manager",
        "Total Revenue",
        "Avg Deal Size",
        "Expected Revenue"
    ]

    # correct sorting
    manager_perf = manager_perf.sort_values("Total Revenue", ascending=False)

    # convert to millions for cleaner display
    manager_perf["Revenue_M"] = manager_perf["Total Revenue"] / 1_000_000

    fig_manager = px.bar(
        manager_perf,
        x="Account Manager",
        y="Revenue_M",
        color="Expected Revenue",
        text="Revenue_M" 
    )
    fig_manager.update_traces(
        texttemplate="GHS %{text:.2f}M"
        #textposition="outside"
    )

    fig_manager.update_layout(
        xaxis_title="Account Manager",
        yaxis_title="Revenue (Millions GHS)",
        xaxis_tickangle=-30,
        uniformtext_minsize=8,
        uniformtext_mode="hide"
    )

    st.plotly_chart(fig_manager, use_container_width=True)

    # -----------------------------
    # MANAGER AGGREGATION
    # -----------------------------
    manager_perf = (
        filtered_df.groupby("Account Manager")
        .agg(
            total_revenue=("expected_revenue", "sum"),
            avg_score=("deal_score", "mean"),
            deal_count=("deal_score", "count"),
            high_quality_pct=("deal_category", lambda x: (x == "High Quality").mean() * 100),
            high_risk_pct=("deal_category", lambda x: (x == "High Risk").mean() * 100)
        )
        .reset_index()
    )

    # -----------------------------
    # NORMALIZATION (SAFE)
    # -----------------------------
    def normalize(series):
        if series.max() == series.min():
            return pd.Series([0.5] * len(series))
        return (series - series.min()) / (series.max() - series.min())

    manager_perf["rev_norm"] = normalize(manager_perf["total_revenue"])
    manager_perf["score_norm"] = normalize(manager_perf["avg_score"])

    # -----------------------------
    # COMBINED SCORE
    # -----------------------------
    manager_perf["manager_score"] = (
        manager_perf["rev_norm"] * 0.6 +
        manager_perf["score_norm"] * 0.4
    )

    manager_perf = manager_perf.sort_values(by="manager_score", ascending=False)

    # -----------------------------
    # DISPLAY TABLE
    # -----------------------------
    st.subheader("Manager Performance (Revenue + Quality)")
    st.dataframe(manager_perf)

    # -----------------------------
    # TOP vs WORST
    # -----------------------------
    top_manager = manager_perf.iloc[0]["Account Manager"]
    worst_manager = manager_perf.iloc[-1]["Account Manager"]

    best = manager_perf.iloc[0]
    worst = manager_perf.iloc[-1]

    st.success(
        f"{top_manager} drives stronger business value, combining higher revenue with better deal quality."
    )

    st.warning(
        f"{worst_manager} delivers lower-quality deals and/or weaker revenue impact, indicating inefficiencies in deal structuring."
    )

    # -----------------------------
    # WHY ANALYSIS (CRITICAL)
    # -----------------------------
    st.markdown("### Key Driver Comparison")

    comparison = pd.DataFrame({
        "Metric": ["Avg Deal Score", "High Quality %", "High Risk %"],
        top_manager: [
            round(best["avg_score"], 2),
            round(best["high_quality_pct"], 2),
            round(best["high_risk_pct"], 2)
        ],
        worst_manager: [
            round(worst["avg_score"], 2),
            round(worst["high_quality_pct"], 2),
            round(worst["high_risk_pct"], 2)
        ]
    })

    st.dataframe(comparison)

    # Insight trigger
    if worst["high_risk_pct"] > best["high_risk_pct"]:
        st.warning(
            f"{worst_manager} has a significantly higher proportion of risky deals, which is likely driving lower overall performance."
        )

    # -----------------------------
    # SCATTER PLOT
    # -----------------------------
    st.markdown("### Manager Performance: Revenue vs Deal Quality")

    st.caption(
        "Each point represents an account manager. Top-right indicates strong performance (high revenue + high quality). "
        "Bottom-right suggests revenue driven by lower-quality deals."
    )

    fig = px.scatter(
        manager_perf,
        x="total_revenue",
        y="avg_score",
        size="deal_count",
        color="manager_score",
        hover_name="Account Manager"
    )

    st.plotly_chart(fig, use_container_width=True)