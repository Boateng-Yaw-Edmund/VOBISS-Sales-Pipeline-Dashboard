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


st.title("Customer Intelligence")

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

df = filtered_df.copy()

# Clean numeric columns
df["expected_revenue"] = pd.to_numeric(df["expected_revenue"], errors="coerce")
df["Probability"] = pd.to_numeric(df["Probability"], errors="coerce")
df["Build Cost (GHS)"] = pd.to_numeric(df["Build Cost (GHS)"], errors="coerce")
df["payback_months"] = pd.to_numeric(df["payback_months"], errors="coerce").replace(0, 1)

# Rename for consistency
df = df.rename(columns={
    "ISP": "customer"
})

# ================================
# CUSTOMER AGGREGATION
# ================================

customer_df = df.groupby("customer").agg(
    total_revenue=("expected_revenue", "sum"),
    deal_count=("customer", "count"),
    avg_probability=("Probability", "mean"),
    avg_payback=("payback_months", "mean"),
    total_build_cost=("Build Cost (GHS)", "sum")
).reset_index()

# Efficiency
customer_df["efficiency"] = (
    customer_df["total_revenue"] * customer_df["avg_probability"]
) / customer_df["total_build_cost"].replace(0, 1)

# Ranking
customer_df["rank"] = customer_df["total_revenue"].rank(ascending=False)

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


# ================================
# KPI SECTION
# ================================

st.subheader("Customer Overview")

col1, col2, col3, col4, col5 = st.columns(5)

col1.metric("Total Customers", customer_df["customer"].nunique())
col2.metric("Top Customer Revenue", f"GHS{format_currency(customer_df['total_revenue'].max())}")
col3.metric("Avg Revenue per Customer", f"GHS{format_currency(customer_df['total_revenue'].mean())}")
col4.metric("MoM Revenue Change", f"{latest['revenue_mom_pct']:.1f}%")
col5.metric("MoM Deal Change", f"{latest['deals_mom_pct']:.1f}%")

st.divider()

tab1, tab2 = st.tabs([
    "Customer Performance",
    "Customer Behavior"
    ])

with tab1:
    # ================================
    # 🎯 TOP CUSTOMERS TO FOCUS ON
    # ================================

    st.subheader("Customers to Focus On")

    # Score customers using revenue + efficiency
    customer_df["focus_score"] = (
        customer_df["total_revenue"] * customer_df["efficiency"]
    )

    top_focus = customer_df.sort_values(
        by="focus_score", ascending=False
    ).head(3)

    for i, row in top_focus.iterrows():
        st.success(
            f"{row['customer']} → High revenue ({row['total_revenue']:,.0f}) "
            f"with strong efficiency. Prioritize for expansion and upselling."
        )

    # ================================
    # ⚠️ CUSTOMERS TO WATCH
    # ================================

    st.subheader("Customers Requiring Attention")

    risk_customers = customer_df[
        customer_df["efficiency"] < customer_df["efficiency"].median()
    ].sort_values(by="efficiency").head(3)

    for i, row in risk_customers.iterrows():
        st.warning(
            f"{row['customer']} → Low efficiency despite revenue. Review deal structure or reduce resource allocation."
        )

    # ================================
    # TOP CUSTOMERS
    # ================================

    st.subheader("Top Customers by Revenue")

    top_customers = customer_df.sort_values(
        by="total_revenue", ascending=False
    ).head(10)

    st.dataframe(top_customers, use_container_width=True)

    # ================================
    # CUSTOMER CONCENTRATION
    # ================================

    total_revenue = customer_df["total_revenue"].sum()
    top_5_revenue = top_customers.head(5)["total_revenue"].sum()

    concentration_pct = (top_5_revenue / total_revenue) * 100 if total_revenue > 0 else 0

    st.metric(
        "Top 5 Customers Contribution",
        f"{concentration_pct:.1f}% of Revenue"
    )

    # ================================
    # VISUAL: CUSTOMER REVENUE
    # ================================
    top_customers["total_revenue_M"] = top_customers["total_revenue"] / 1_000_000
    fig = px.bar(
        top_customers,
        x="customer",
        y="total_revenue_M",
        color="customer",
        title="Top Customers by Revenue",
        text="total_revenue_M"
    )
    fig.update_traces(texttemplate="GHS %{text:.2f}M")
    fig.update_layout(uniformtext_minsize=8, uniformtext_mode="hide")
    st.plotly_chart(fig, use_container_width=True)

    # ================================
    # CUSTOMER EFFICIENCY SCATTER
    # ================================

    fig2 = px.scatter(
        customer_df,
        x="total_build_cost",
        y="total_revenue",
        size="deal_count",
        color="efficiency",
        hover_data=["customer"],
        title="Customer Investment vs Return"
    )

    st.plotly_chart(fig2, use_container_width=True)

    # ================================
    # UNDERPERFORMING CUSTOMERS
    # ================================

    st.subheader("⚠️ Underperforming Customers")

    low_perf = customer_df[
        customer_df["efficiency"] < customer_df["efficiency"].median()
    ].sort_values(by="efficiency")

    st.dataframe(low_perf.head(10), use_container_width=True)

    # ================================
    # INSIGHT BLOCK
    # ================================

    st.subheader("📌 What This Means")

    if concentration_pct > 60:
        st.warning(
            f"Revenue is highly concentrated. Top customers contribute {concentration_pct:.1f}% of total revenue. Reduce dependency risk."
        )
    else:
        st.info(
            f"Revenue is moderately distributed. Continue developing high-value customers."
        )

    st.success(
        "Prioritize high-efficiency customers and expand relationships through upselling or additional services."
    )

    st.warning(
        "Reduce focus on low-efficiency customers that consume resources without strong returns."
    )


with tab2:

    # ================================
    # TIME PREPARATION (USE FILTERED DATA)
    # ================================

    df_time = filtered_df.copy()

    df_time["date"] = pd.to_datetime(df_time["date"], errors="coerce")
    df_time = df_time.dropna(subset=["date"])

    df_time["year_month"] = df_time["date"].dt.to_period("M").astype(str)

    # ================================
    # MONTHLY PIPELINE TREND (GLOBAL)
    # ================================

    df_time = df_time.rename(columns={
    "Site[End User]": "deal_name"
    })

    monthly_trend = df_time.groupby("year_month").agg(
        revenue=("expected_revenue", "sum"),
        deals=("deal_name", "count")
    ).reset_index().sort_values("year_month")

    st.subheader("Monthly Pipeline Trend")

    fig0 = px.line(
        monthly_trend,
        x="year_month",
        y="revenue",
        markers=True,
        title="Total Expected Revenue Over Time"
    )

    st.plotly_chart(fig0, use_container_width=True)

    # ------------------------------
    # Growth Logic (FIXED)
    # ------------------------------

    monthly_trend["prev_revenue"] = monthly_trend["revenue"].shift(1)

    monthly_trend["growth"] = (
        (monthly_trend["revenue"] - monthly_trend["prev_revenue"]) /
        monthly_trend["prev_revenue"]
    )

    latest = monthly_trend.iloc[-1]

    if pd.isna(latest["growth"]) or latest["prev_revenue"] == 0:
        st.info("Latest period has insufficient data for growth calculation.")
    else:
        if latest["growth"] < -0.3:
            st.error("Revenue is declining sharply. Investigate pipeline slowdown.")
        elif latest["growth"] < 0:
            st.warning("Revenue shows a downward trend.")
        else:
            st.success("Revenue is growing steadily.")

    # ================================
    # DEAL VOLUME TREND
    # ================================

    st.subheader("Monthly Deal Volume")

    fig_vol = px.bar(
        monthly_trend,
        x="year_month",
        y="deals",
        title="Number of Deals per Month",
            text="deals"
    )

    st.plotly_chart(fig_vol, use_container_width=True)

    # ================================
    # CUSTOMER REVENUE TREND
    # ================================
    # ================================
    # CUSTOMER TREND (ROBUST VERSION)
    # ================================

    # Detect correct column
    customer_col = "customer" if "customer" in df_time.columns else "ISP"

    # Group properly
    customer_trend = df_time.groupby(["year_month", customer_col]).agg(
        revenue=("expected_revenue", "sum")
    ).reset_index()

    st.subheader("Customer Performance Over Time")

    # Dropdown
    customers = sorted(customer_trend[customer_col].dropna().unique())

    selected_customer = st.selectbox(
        "Select Customer",
        options=customers
    )

    # Filter
    customer_view = customer_trend[
        customer_trend[customer_col] == selected_customer
    ].sort_values("year_month")

    # Plot
    fig = px.line(
        customer_view,
        x="year_month",
        y="revenue",
        markers=True,
        title=f"{selected_customer} Revenue Trend"
    )

    st.plotly_chart(fig, use_container_width=True)

    # ------------------------------
    # SMART CHANGE DETECTION (FIXED)
    # ------------------------------

    customer_view["prev_revenue"] = customer_view["revenue"].shift(1)

    customer_view["change_pct"] = (
        (customer_view["revenue"] - customer_view["prev_revenue"]) /
        customer_view["prev_revenue"]
    )

    latest = customer_view.iloc[-1]

    if pd.isna(latest["change_pct"]) or latest["prev_revenue"] == 0:
        st.info("Insufficient data to evaluate recent change.")
    else:
        if latest["change_pct"] < -0.3:
            st.error("Customer revenue is dropping sharply. Immediate attention required.")
        elif latest["change_pct"] < 0:
            st.warning("Customer revenue is declining.")
        elif latest["change_pct"] > 0.3:
            st.success("Customer revenue is growing strongly.")
        else:
            st.info("Customer revenue is relatively stable.")

    # ================================
    # TOP CUSTOMERS TREND
    # ================================

    st.subheader("Top Customers Trend Comparison")

    # Detect correct column
    customer_col = "customer" if "customer" in df_time.columns else "ISP"

    # Get top 5 customers by revenue
    top_customers = (
        df_time.groupby(customer_col)["expected_revenue"]
        .sum()
        .nlargest(5)
        .index
    )

    # Filter trend data
    top_trend = customer_trend[
        customer_trend[customer_col].isin(top_customers)
    ]

    # Plot
    fig2 = px.line(
        top_trend,
        x="year_month",
        y="revenue",
        color=customer_col,
        markers=True,
        title="Top 5 Customers Revenue Trend"
    )

    st.plotly_chart(fig2, use_container_width=True)

    # ================================
    # CUSTOMER STABILITY (ADVANCED)
    # ================================

    #st.subheader("Customer Revenue Stability")

    #customer_volatility = (
    #top_trend.groupby(customer_col)["revenue"]
    #.agg(["mean", "std"])
    #.reset_index()
    #)

    #customer_volatility["volatility_ratio"] = (
    #    customer_volatility["std"] / customer_volatility["mean"]
    #)

    #customer_volatility = customer_volatility.rename(
    #    columns={"volatility_ratio": "volatility"}
    #)

    #stable_customers = customer_volatility[
    #customer_volatility["volatility"] < 0.5
    #]

    #unstable_customers = customer_volatility[
    #    customer_volatility["volatility"] > 1
    #]


    #st.success(
    #f"{len(stable_customers)} customers show stable revenue patterns and can be relied on for forecasting."
    #)

    #st.error(
    #    f"{len(unstable_customers)} key customers show high revenue volatility, introducing forecasting risk."
    #)

    #st.dataframe(
    #    customer_volatility.sort_values(by="volatility", ascending=False),
    #    use_container_width=True
    #)