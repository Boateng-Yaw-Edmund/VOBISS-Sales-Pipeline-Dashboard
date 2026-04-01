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
    page_title="Geographic View",
    layout="wide"
)


st.title("Geographic Intelligence")

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

st.markdown("""
<style>

/* Reduce overall padding */
.block-container {
    padding-top: 1rem;
    padding-bottom: 1rem;
}

/* KPI metric styling */
[data-testid="stMetricValue"] {
    font-size: 20px !important;
    font-weight: 600;
}

[data-testid="stMetricLabel"] {
    font-size: 12px !important;
}

/* Reduce column spacing */
div[data-testid="column"] {
    padding: 0.2rem;
}

/* Reduce header spacing */
h1, h2, h3 {
    margin-bottom: 0.5rem;
}

</style>
""", unsafe_allow_html=True)

st.sidebar.header("Filters")

#sliders
min_rev, max_rev = st.sidebar.slider(
    "Revenue (GHS)",
    0,
    int(df_ui["TCV (GHS)"].max()),
    (0, int(df_ui["TCV (GHS)"].max()))
)

st.sidebar.caption(
    f"Selected: {format_currency(min_rev)} -> {format_currency(max_rev)}"
)

min_dist, max_dist = st.sidebar.slider(
    "Distance (m)",
    0,
    int(df_ui["Distance (m)"].max()),
    (0, int(df_ui["Distance (m)"].max()))
)

st.sidebar.caption(
    f"Selected: {format_currency(min_dist)}m -> {format_currency(max_dist)}m"
)

#region filter
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


#kpi metrics
col1, col2, col3, col4 = st.columns(4)

total_revenue = filtered_df["TCV (GHS)"].sum()
expected_revenue = filtered_df["expected_revenue"].sum()
#first row of metrics
col1.metric("Revenue", f"GHS {format_currency(filtered_df['TCV (GHS)'].sum())}")
col2.metric("Expected Revenue", f"GHS {format_currency(filtered_df['expected_revenue'].sum())}")
value = filtered_df["revenue_per_meter"].mean()

col3.metric(
    "Revenue Density",
    f"GHS {value:,.0f}/m"
)
col4.metric("Avg Payback Months", f"{filtered_df['payback_months'].mean():.1f}")

#second row of metrics
col5, col6, col7 = st.columns(3)
col5.metric("Mapped %", f"{filtered_df['lat_final'].notna().mean()*100:.1f}%")

top_region = (
    filtered_df.groupby("Region")["TCV (GHS)"]
    .sum()
)

col6.metric("Top Region", top_region.idxmax() if not top_region.empty else "-")

#tabs
tab1, tab2, tab3 = st.tabs(["Map", "Performance", "Risk Analysis"])

#map tab
with tab1:

    st.subheader("Deal Distribution & Revenue Concentration")

    # Base dataset
    map_df = filtered_df.dropna(subset=["lat_final", "lon_final"]).copy()

    # Fallback if empty
    if map_df.empty:
        st.warning("No data for selected filters. Showing all locations.")
        map_df = df.dropna(subset=["lat_final", "lon_final"]).copy()

    # Ghana bounds filter
    map_df = map_df[
        (map_df["lat_final"].between(4, 11)) &
        (map_df["lon_final"].between(-3, 2))
    ]

    # Safe size column
    map_df["size_safe"] = pd.to_numeric(
        map_df["TCV (GHS)"], errors="coerce"
    ).fillna(0)

    # Remove invalid/zero values (prevents crash)
    map_df = map_df[map_df["size_safe"] > 0]

    if not map_df.empty:

        fig_map = px.scatter_mapbox(
            map_df,
            lat="lat_final",
            lon="lon_final",
            size="size_safe",  
            color="deal_status",
            hover_name="Site[End User]",
            hover_data={
                "Region": True,
                "Service": True,
                "TCV (GHS)": True,
                "Distance (m)": True,
                "payback_months": True,
                "lat_final": False,
                "lon_final": False
            },
            height=650,
            opacity=0.7
        )

        fig_map.update_layout(
            mapbox_style="carto-positron",
            mapbox=dict(
                center=dict(lat=7.9465, lon=-1.0232),
                zoom=6
            ),
            margin=dict(l=0, r=0, t=0, b=0)
        )

        st.plotly_chart(fig_map, use_container_width=True)

    else:
        st.warning("No valid Ghana coordinates available after cleaning.")

#performance tab
with tab2:

    st.subheader(" Revenue Concentration by Region")

    region_df = (
        filtered_df
        .dropna(subset=["Region"])
        .groupby("Region", as_index=False)["TCV (GHS)"]
        .sum()
        .sort_values("TCV (GHS)", ascending=False)
        .head(10)
    )

    if region_df.empty:
        st.warning("No region data available for current filters.")
    else:
        # Top region insight
        top_region = region_df.iloc[0]["Region"]
        top_value = region_df.iloc[0]["TCV (GHS)"]

        st.info(f"{top_region} leads revenue generation with GHS {top_value:,.0f}.")

        # Format values for readability
        def format_short(x):
            if x >= 1_000_000:
                return f"{x/1_000_000:.1f}M"
            elif x >= 1_000:
                return f"{x/1_000:.1f}K"
            return f"{x:.0f}"

        region_df["TCV_label"] = region_df["TCV (GHS)"].apply(format_short)

        fig_region = px.bar(
            region_df,
            x="Region",
            y="TCV (GHS)",
            text="TCV_label",  
            color="TCV (GHS)",
            color_continuous_scale="Blues"
        )

        fig_region.update_layout(
            xaxis_title="Region",
            yaxis_title="Revenue (GHS)",
            showlegend=False
        )

        fig_region.update_traces(
            textposition="outside"
        )

        st.plotly_chart(fig_region, use_container_width=True)


#risk analysis tab
with tab3:

    st.subheader("Infrastructure Efficiency")

    plot_df = filtered_df.copy()

    # SAFETY LAYER (prevents crashes)
    plot_df["TCV (GHS)"] = pd.to_numeric(plot_df["TCV (GHS)"], errors="coerce").fillna(0)
    plot_df["expected_revenue"] = pd.to_numeric(plot_df["expected_revenue"], errors="coerce").fillna(0)
    plot_df["Distance (m)"] = pd.to_numeric(plot_df["Distance (m)"], errors="coerce").fillna(0)
    plot_df["build_cost_ratio"] = pd.to_numeric(plot_df["build_cost_ratio"], errors="coerce").fillna(0)

    #Remove zero-size rows (prevents Plotly errors)
    plot_df = plot_df[plot_df["expected_revenue"] > 0]

    st.info(
        "Deals in the bottom-right (high distance, low revenue) indicate inefficient infrastructure investment and should be reviewed."
    )

    # Detect number of services in current view
    service_count = plot_df["Service"].nunique()

    # Decide scale
    if service_count > 1:
        plot_df["distance_plot"] = np.log1p(plot_df["Distance (m)"])
        x_label = "Distance (log scale)"
        st.caption("Log scale applied due to wide variation across services.")
    else:
        plot_df["distance_plot"] = plot_df["Distance (m)"]
        x_label = "Distance (m)"

    fig_efficiency = px.scatter(
        plot_df,
        x="distance_plot",
        y="TCV (GHS)",
        size="expected_revenue", 
        color="build_cost_ratio",
        hover_name="Site[End User]",
        hover_data={
            "Region": True,
            "Service": True,
            "Distance (m)": True,
            "TCV (GHS)": True,
            "payback_months": True,
            "build_cost_ratio": True
        },
        color_continuous_scale="RdYlGn_r",
        title="Infrastructure Efficiency"
    )

    fig_efficiency.update_layout(
        xaxis_title=x_label,
        yaxis_title="Revenue (GHS)"
    )

    fig_efficiency.update_traces(opacity=0.6)

    st.plotly_chart(fig_efficiency, use_container_width=True)
    

    st.subheader("Payback Risk Analysis")

    risk_df = filtered_df.copy()

    #SAFETY LAYER
    risk_df["Distance (m)"] = pd.to_numeric(risk_df["Distance (m)"], errors="coerce").fillna(0)
    risk_df["payback_months"] = pd.to_numeric(risk_df["payback_months"], errors="coerce").fillna(0)
    risk_df["TCV (GHS)"] = pd.to_numeric(risk_df["TCV (GHS)"], errors="coerce").fillna(0)

    # Remove zero-value rows
    risk_df = risk_df[risk_df["TCV (GHS)"] > 0]

    #Risk flag
    risk_df["risk_flag"] = risk_df["payback_months"] > 48

    # Insight
    high_risk_count = risk_df["risk_flag"].sum()

    st.info(
        f"{high_risk_count} deals exceed a 48-month payback period and may pose financial risk."
    )

    fig_risk = px.scatter(
        risk_df,
        x="Distance (m)",
        y="payback_months",
        size="TCV (GHS)",
        color="deal_status",
        color_discrete_map={
            "Closed Won": "#8B5CF6",
            "Open Pipeline": "yellow"
        },
        hover_name="Site[End User]",
        hover_data={
            "Region": True,
            "Service": True,
            "Distance (m)": True,
            "TCV (GHS)": True,
            "payback_months": True
        },
        title="Payback Risk Analysis"
    )

    # Add risk threshold line
    fig_risk.add_hline(
        y=48,
        line_dash="dash",
        line_color="red",
        annotation_text="Risk Threshold (48 months)",
        annotation_position="top left"
    )

    fig_risk.update_traces(opacity=0.6)

    fig_risk.update_layout(
        xaxis_title="Distance (m)",
        yaxis_title="Payback (months)"
    )

    st.plotly_chart(fig_risk, use_container_width=True)

    st.subheader("High-Risk Infrastructure Deals")

    problem_deals = filtered_df[
        (filtered_df["payback_months"] > 48) &
        (filtered_df["build_cost_ratio"] > 0.5)
    ]

    st.dataframe(problem_deals[[
        "Site[End User]",
        "Region",
        "Service",
        "TCV (GHS)",
        "Distance (m)",
        "payback_months",
        "build_cost_ratio"
    ]])

