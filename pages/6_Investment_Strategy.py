import streamlit as st
import pandas as pd
import numpy as np

from src.filtering import apply_filters, prepare_base

# ================================
# LOAD DATA
# ================================
df = pd.read_csv("data/processed/clean_sales_pipeline.csv")
df = prepare_base(df)

st.set_page_config(page_title="Investment Strategy", layout="wide")

st.title("Investment Strategy Engine")

# ================================
# BASIC CLEANING (FIXED)
# ================================
df["expected_revenue"] = pd.to_numeric(df["expected_revenue"], errors="coerce")
df["Build Cost (GHS)"] = pd.to_numeric(df["Build Cost (GHS)"], errors="coerce")

# 🔥 FIXED PROBABILITY (NO MORE FAKE 100%)
if "Probability" in df.columns:
    df["Probability"] = pd.to_numeric(df["Probability"], errors="coerce")
else:
    df["Probability"] = np.nan

df["Probability"] = df["Probability"].fillna(0.3)  # conservative fallback

# rename safely
df = df.rename(columns={
    "ISP": "customer",
    "Site[End User]": "deal_name"
})

# drop bad rows
df = df.dropna(subset=["expected_revenue", "Build Cost (GHS)"])
df = df[df["Build Cost (GHS)"] > 0]

# ================================
# SIDEBAR FILTERS
# ================================
st.sidebar.header("Filters")

regions = sorted(df["Region"].dropna().unique())
region_filter = st.sidebar.multiselect("Region", regions, default=regions)

services = sorted(df["Service"].dropna().unique())
service_filter = st.sidebar.multiselect("Service", services, default=services)

status_options = ["All", "Open Pipeline", "Closed Won"]

status_filter = st.sidebar.selectbox(
    "Deal Status",
    options=status_options
)

# 🔥 NEW: Confidence Control
st.sidebar.subheader("Risk Controls")

min_probability = st.sidebar.slider(
    "Minimum Deal Probability",
    0.0, 1.0, 0.5, 0.05
)

min_deal_size = st.sidebar.slider(
    "Minimum Build Cost (GHS)",
    0, int(df["Build Cost (GHS)"].max()), 10000, 5000
)

max_deals = st.sidebar.slider(
    "Max Deals in Portfolio",
    5, 200, 50
)

# apply base filters
filtered_df, _ = apply_filters(
    df,
    region=region_filter,
    service=service_filter,
    status=status_filter
)

data = filtered_df.copy()

# ================================
# 🔥 PIPELINE SANITY FILTER
# ================================
if status_filter == "Open Pipeline":
    data = data[data["Probability"] >= min_probability]

# minimum size filter
data = data[data["Build Cost (GHS)"] >= min_deal_size]

# ================================
# EFFICIENCY CALCULATION
# ================================
data["adjusted_efficiency"] = (
    data["expected_revenue"] * data["Probability"]
) / data["Build Cost (GHS)"]

# ================================
# BUDGET INPUT
# ================================
st.subheader("Investment Budget")

budget = st.slider(
    "Select Investment Budget (GHS)",
    min_value=0,
    max_value=int(data["Build Cost (GHS)"].sum()) if len(data) > 0 else 1000000,
    value=20000000,
    step=1000000
)

# ================================
# 🔥 OPTIMIZATION (IMPROVED)
# ================================
data = data.sort_values(by="adjusted_efficiency", ascending=False)

# diversification: max 5 deals per customer
data = (
    data.groupby("customer", group_keys=False)
    .head(5)
)

data["cumulative_cost"] = data["Build Cost (GHS)"].cumsum()

portfolio = data[data["cumulative_cost"] <= budget]

# 🔥 portfolio cap
portfolio = portfolio.head(max_deals)

# ================================
# OUTPUT TABLE
# ================================
st.subheader("Recommended Investment Portfolio")

display_cols = [
    "deal_name",
    "customer",
    "expected_revenue",
    "Build Cost (GHS)",
    "Probability",
    "adjusted_efficiency"
]

st.dataframe(
    portfolio[display_cols].reset_index(drop=True),
    use_container_width=True
)

# ================================
# SUMMARY METRICS
# ================================
total_cost = portfolio["Build Cost (GHS)"].sum()
total_revenue = portfolio["expected_revenue"].sum()
avg_efficiency = portfolio["adjusted_efficiency"].mean()
deal_count = len(portfolio)

col1, col2, col3, col4 = st.columns(4)

col1.metric("Total Investment Used", f"GHS {total_cost:,.0f}")
col2.metric("Expected Revenue", f"GHS {total_revenue:,.0f}")
col3.metric("Avg Efficiency", f"{avg_efficiency:.2f}")
col4.metric("Deals Selected", f"{deal_count}")

# ================================
# PORTFOLIO RISK SIGNAL
# ================================
top_customer_share = (
    portfolio.groupby("customer")["expected_revenue"]
    .sum()
    .sort_values(ascending=False)
)

if len(top_customer_share) > 0:
    concentration = top_customer_share.iloc[0] / total_revenue

    if concentration > 0.5:
        st.warning("⚠️ Portfolio highly concentrated in one customer")

# ================================
# LEFTOVER BUDGET
# ================================
remaining = budget - total_cost
st.info(f"Remaining Budget: GHS {remaining:,.0f}")

# ================================
# EXECUTIVE RECOMMENDATION
# ================================
st.subheader("Executive Recommendation")

if deal_count > 0:
    st.success(
        f"Invest GHS {total_cost:,.0f} across {deal_count} high-confidence deals "
        f"to generate approximately GHS {total_revenue:,.0f} in expected revenue. "
        f"Portfolio is optimized for efficiency while controlling risk exposure."
    )
else:
    st.warning("No viable deals within selected budget and filters.")