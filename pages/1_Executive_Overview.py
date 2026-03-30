import streamlit as st
import pandas as pd
import plotly.express as px
from sympy import series
from src.filtering import apply_filters, get_map_data, prepare_base

#wide page config
st.set_page_config(
    page_title="Executive Overview",
    layout="wide"
)

st.title("Executive Overview")

#data load
df = pd.read_csv("data/processed/clean_sales_pipeline.csv")

#reset button

if st.sidebar.button("Reset All Filters"):
    st.session_state.clear()
    st.rerun()

st.sidebar.header("Filters")

df_ui = prepare_base(df)
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

#region filter
regions = sorted(df_ui["Region"].dropna().unique())

select_all_regions = st.sidebar.checkbox("Select All Regions", value=True)

if select_all_regions:
    region_filter = regions
else:
    region_filter = st.sidebar.multiselect("Region", options=regions)

#service filter
services = sorted(df["Service"].dropna().unique())

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

#apply global filters

filtered_df, filtered_time_df  = apply_filters(
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
total_pipeline = filtered_df["TCV (GHS)"].sum()
expected_revenue = filtered_df["expected_revenue"].sum()
avg_payback = filtered_df["payback_months"].mean()
deal_count = filtered_df.shape[0]
missing_pct = filtered_df["date_missing_flag"].mean() * 100
high_quality_pct = (filtered_df["deal_category"] == "High Quality").mean() * 100
risky_pct = (filtered_df["deal_category"] == "High Risk").mean() * 100



col1, col2, col3, col4, col5, col6, col7 = st.columns(7)

col1.metric("Total Pipeline Value", f"GHS {format_currency(total_pipeline)}")
col2.metric("Expected Revenue", f"GHS {format_currency(expected_revenue)}")
col3.metric("Avg Payback Months", f"{avg_payback:.1f}")
col4.metric("Deal Count", deal_count)
col5.metric("Deals Missing Timeline (%)", f"{missing_pct:.1f}%")
col6.metric("High Quality Deals (%)", f"{high_quality_pct:.1f}%")
col7.metric("Risky Deals (%)", f"{risky_pct:.1f}%")


analysis_df = filtered_df.copy()

#Standardize columns for analysis
analysis_df = analysis_df.rename(columns={
    "Site[End User]": "deal_name",
    "ISP": "customer",
    "Build Cost (GHS)": "build_cost"
})

#Clean data for analysis ---
analysis_df = analysis_df.drop_duplicates(subset=["deal_name", "customer"])
analysis_df["build_cost"] = analysis_df["build_cost"].fillna(0)
analysis_df["payback_months"] = analysis_df["payback_months"].replace(0, 1)

# Cost floor to prevent extreme efficiency scores
MIN_COST = 5000
analysis_df["adjusted_build_cost"] = analysis_df["build_cost"].apply(lambda x: max(x, MIN_COST))

#Efficiency
analysis_df["efficiency"] = (
    analysis_df["expected_revenue"] * analysis_df["Probability"]
) / analysis_df["adjusted_build_cost"]

analysis_df["adjusted_efficiency"] = (
    analysis_df["efficiency"] / analysis_df["payback_months"]
)

#Key Decisions

st.markdown("## Key Decisions")

# Revenue concentration 
top_pct = 0.2
top_n = max(1, int(len(analysis_df) * top_pct))

top_deals = analysis_df.sort_values(
    by="expected_revenue", ascending=False
).head(top_n)

top_rev = top_deals["expected_revenue"].sum()
total_rev = analysis_df["expected_revenue"].sum()

contribution_pct = (top_rev / total_rev) * 100 if total_rev > 0 else 0

#Stage leakage 
stage_group = analysis_df.groupby("Current Period Stage").agg(
    deal_count=("deal_name", "count"),
    total_revenue=("expected_revenue", "sum")
).reset_index()

stage_group["deal_share"] = stage_group["deal_count"] / stage_group["deal_count"].sum()
stage_group["revenue_share"] = stage_group["total_revenue"] / stage_group["total_revenue"].sum()
stage_group["leakage"] = stage_group["deal_share"] - stage_group["revenue_share"]

worst_stage = stage_group.sort_values(by="leakage", ascending=False).iloc[0]

# Efficiency misallocation
high_value = analysis_df[
    analysis_df["expected_revenue"] > analysis_df["expected_revenue"].median()
]

low_efficiency = high_value[
    high_value["adjusted_efficiency"] < analysis_df["adjusted_efficiency"].median()
]

misalloc_pct = (
    (len(low_efficiency) / len(high_value)) * 100
    if len(high_value) > 0 else 0
)


col1, col2, col3 = st.columns(3)

with col1:
    st.success(
        f"Top 20% of deals contribute {contribution_pct:.1f}% of expected revenue"
    )

with col2:
    st.warning(
        f"{worst_stage['Current Period Stage']} stage shows the highest leakage. Reduce deal volume entering this stage or improve conversion efficiency to prevent value erosion."
    )

with col3:
    st.info(
        f"{misalloc_pct:.1f}% of high-value deals are inefficient. Reallocate focus to higher-efficiency opportunities."
    )

st.divider()

tab1, tab2, tab3 = st.tabs([
    "Overview",
    "Deal Quality",
    "Pipeline Composition"
])

with tab1:
    ##INVESMENT model

    HIGH_VALUE_THRESHOLD = analysis_df["expected_revenue"].quantile(0.7)
    MIN_STRATEGIC_COST = 10000

    #Strategic deals (high revenue, significant cost)
    strategic_deals = analysis_df[
        (analysis_df["expected_revenue"] >= HIGH_VALUE_THRESHOLD) &
        (analysis_df["build_cost"] >= MIN_STRATEGIC_COST)
    ].sort_values(by="adjusted_efficiency", ascending=False).head(5)

    #Quick wins (low cost, fast return)
    quick_wins = analysis_df[
        (analysis_df["expected_revenue"] < HIGH_VALUE_THRESHOLD)
    ].sort_values(by="adjusted_efficiency", ascending=False).head(5)

    ##Top deal contribution

    TOP_N = 10

    top_n_eff = analysis_df.sort_values(
        by="adjusted_efficiency", ascending=False
    ).head(TOP_N)

    top_n_revenue = top_n_eff["expected_revenue"].sum()
    total_revenue = analysis_df["expected_revenue"].sum()

    eff_contribution_pct = (
        (top_n_revenue / total_revenue) * 100
        if total_revenue > 0 else 0
    )
    st.markdown("## Revenue Concentration")

    st.metric(
        label=f"Top {TOP_N} Deals Contribution",
        value=f"{eff_contribution_pct:.1f}% of Expected Revenue"
    )

    if eff_contribution_pct > 60:
        st.warning("High dependency on a small number of deals. Risky concentration.")
    elif eff_contribution_pct > 40:
        st.info("Moderate concentration. Monitor dependency levels.")
    else:
        st.success(f"Pipeline is dominated by low-value deals, with top 10 opportunities contributing only {eff_contribution_pct:.1f}% of expected revenue. "
    "Increase focus on acquiring and prioritizing high-impact deals to improve revenue leverage and reduce dependency on volume-driven growth.")
    st.markdown("## Where We Should Invest")

    # Strategic
    st.markdown("###  Strategic Bets (High Revenue Impact)")
    st.markdown(
    "These deals represent the highest revenue opportunities with meaningful investment requirements and strong efficiency.")
    st.dataframe(
        strategic_deals[[
            "deal_name", "customer", "expected_revenue",
            "build_cost", "adjusted_efficiency"
        ]],
        use_container_width=True
    )

    # Quick Wins
    st.markdown("### Quick Wins (Low Cost, Fast Return)")
    st.markdown(
    "These are low-cost, fast-return opportunities that can be executed quickly with minimal resource commitment.")
    st.dataframe(
        quick_wins[[
            "deal_name", "customer", "expected_revenue",
            "build_cost", "adjusted_efficiency"
        ]],
        use_container_width=True
    )

    #prep data for visualization
    plot_df = analysis_df.copy()
    plot_df = plot_df.dropna(subset=["Probability"])

    # Create deal type for coloring
    plot_df["deal_type"] = "Quick Win"
    plot_df.loc[
        (plot_df["expected_revenue"] >= HIGH_VALUE_THRESHOLD) &
        (plot_df["build_cost"] >= MIN_STRATEGIC_COST),
        "deal_type"
    ] = "Strategic Bet"

    fig = px.scatter(
        plot_df,
        x="build_cost",
        y="expected_revenue",
        size="Probability",
        color="deal_type",
        color_discrete_map={
        "Strategic Bet": "#8B5CF6",   
        "Quick Win": "#F59E0B"        
    },
        hover_data=[
            "deal_name",
            "customer",
            "adjusted_efficiency"
        ],
        title="Investment Efficiency Landscape"
    )

    fig.update_layout(
        xaxis_title="Build Cost (GHS)",
        yaxis_title="Expected Revenue (GHS)",
        legend_title="Deal Type"
    )
    fig.update_traces(marker=dict(line=dict(width=1, color='white')))
    st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("###  What This Means")

    st.info(
    "Pipeline is dominated by low-cost, low-revenue deals. Increase deal size or bundle opportunities to improve overall revenue impact."
    )

    st.warning(
        "High-cost deals require strict efficiency validation before approval. Prioritize only those with strong return potential."
    )

    st.success(
        "Low-cost, moderate-revenue deals should be executed aggressively to generate quick wins and improve short-term revenue performance."
    )
    # Revenue by Service

    st.subheader("Revenue by Service")

    service_chart = (
        filtered_df
        .groupby("Service")["TCV (GHS)"]
        .sum()
        .reset_index()
        .sort_values("TCV (GHS)", ascending=False)
    )

    # convert to millions for clean display
    service_chart["Revenue_M"] = service_chart["TCV (GHS)"] / 1_000_000

    fig_service = px.bar(
        service_chart,
        x="Service",
        y="Revenue_M",
        color="Service",
        text="Revenue_M"
    )

    fig_service.update_traces(
        texttemplate="GHS %{text:.2f}M",
        textposition="outside"
    )

    fig_service.update_layout(
        yaxis_title="Revenue (Millions GHS)",
        xaxis_title="Service",
        showlegend=False,
        uniformtext_minsize=8,
        uniformtext_mode="hide"
    )

    st.plotly_chart(fig_service, use_container_width=True)


    col3, col4 = st.columns(2)

    # pipeline funnel
    with col3:

        st.subheader("Pipeline Funnel")

        funnel_data = (
            filtered_df
            .groupby("Current Period Stage")["TCV (GHS)"]
            .sum()
            .reset_index()
        )

        fig_funnel = px.funnel(
            funnel_data,
            y="Current Period Stage",
            x="TCV (GHS)"
        )

        st.plotly_chart(fig_funnel, use_container_width=True)

    # Deal Size Distribution
    with col4:

        st.subheader("Deal Size Distribution")

        fig_hist = px.histogram(
            filtered_df,
            x="TCV (GHS)",
            nbins=30
        )

        st.plotly_chart(fig_hist, use_container_width=True)

with tab2:

    revenue_at_risk = filtered_df[filtered_df["deal_category"] == "High Risk"]["expected_revenue"].sum()

    st.metric("Revenue at Risk (GHS)", f"{revenue_at_risk:,.0f}")


    fig = px.pie(
        filtered_df,
        names="deal_category",
        title="Deal Quality Distribution"
    )

    st.plotly_chart(fig, use_container_width=True)

    score_breakdown = filtered_df[[
        "rev_score",
        "payback_score",
        "distance_score",
        "prob_score"
    ]].mean().reset_index()

    score_breakdown.columns = ["Factor", "Average Score"]

    st.dataframe(score_breakdown)

    good = filtered_df[filtered_df["deal_category"] == "High Quality"]
    bad = filtered_df[filtered_df["deal_category"] == "High Risk"]

    comparison = pd.DataFrame({
        "Good Deals": good[["rev_score", "payback_score", "distance_score", "prob_score"]].mean(),
        "Bad Deals": bad[["rev_score", "payback_score", "distance_score", "prob_score"]].mean()
    })

    st.dataframe(comparison)


with tab3:

    st.subheader("Pipeline Composition Analysis")

    df_funnel = filtered_df.copy()

    # -----------------------------
    # STAGE ORDERING
    # -----------------------------
    df_funnel["stage_order"] = (
        df_funnel["Current Period Stage"]
        .str.extract(r"(\d+)")
        .astype(float)
    )

    df_funnel["stage_name"] = df_funnel["Current Period Stage"]

    # Aggregate and sort
    stage_dist = (
        df_funnel.groupby(["stage_order", "stage_name"])
        .agg(
            deal_count=("stage_name", "count"),
            total_revenue=("expected_revenue", "sum")
        )
        .reset_index()
        .sort_values("stage_order")
    )

   #share calculations
    total_deals = stage_dist["deal_count"].sum()
    total_revenue = stage_dist["total_revenue"].sum()

    stage_dist["stage_share_%"] = (
        stage_dist["deal_count"] / total_deals
    ) * 100

    stage_dist["revenue_share_%"] = (
        stage_dist["total_revenue"] / total_revenue
    ) * 100

    #table
    st.markdown("### Pipeline Composition (Volume & Value)")

    display_df = stage_dist[[
        "stage_name",
        "deal_count",
        "stage_share_%",
        "total_revenue",
        "revenue_share_%"
    ]].copy()

    # Optional formatting
    display_df["stage_share_%"] = display_df["stage_share_%"].round(2)
    display_df["revenue_share_%"] = display_df["revenue_share_%"].round(2)

    st.dataframe(display_df)

    import plotly.express as px

    fig1 = px.bar(
        stage_dist,
        x="stage_name",
        y="deal_count",
        title="Deal Distribution by Stage",
        text="deal_count"
    )
    fig1.update_traces(textposition="outside")
    fig1.update_layout(uniformtext_minsize=8, uniformtext_mode="hide")


    st.plotly_chart(fig1, use_container_width=True)

    stage_dist["total_revenue_M"] = stage_dist["total_revenue"] / 1_000_000
  #revenue distribution by stage
    fig2 = px.bar(
        stage_dist,
        x="stage_name",
        y="total_revenue_M",
        title="Revenue Distribution by Stage",
        text="total_revenue_M"
    )
    fig2.update_traces(texttemplate="GHS %{text:.2f}M",textposition="outside")
    fig2.update_layout(
            yaxis_title="Revenue (Millions GHS)",
            xaxis_title="Stage Name",
            showlegend=False,
            uniformtext_minsize=8,
            uniformtext_mode="hide"
    )
    st.plotly_chart(fig2, use_container_width=True)

    #insights
    largest_stage = stage_dist.sort_values(
        "stage_share_%", ascending=False
    ).iloc[0]["stage_name"]

    highest_value_stage = stage_dist.sort_values(
        "revenue_share_%", ascending=False
    ).iloc[0]["stage_name"]

    st.info(
        f"Most deals are concentrated in {largest_stage}, while the highest revenue contribution comes from {highest_value_stage}."
    )

    mismatch_stage = stage_dist.iloc[
        (stage_dist["stage_share_%"] - stage_dist["revenue_share_%"]).abs().idxmax()
    ]["stage_name"]

    st.warning(
        f"{mismatch_stage} shows the largest mismatch between deal volume and revenue contribution, indicating potential inefficiency or low-value deal concentration."
    )

    st.markdown("### Revenue Leakage Analysis")
    st.warning(
        "Positive leakage indicates stages that consume more deal volume than the revenue they generate, while negative leakage suggests stages that are more efficient at generating revenue relative to their deal volume."
    )


    # Leakage calculation
    stage_dist["leakage"] = stage_dist["stage_share_%"] - stage_dist["revenue_share_%"]

    # Format for display
    leakage_df = stage_dist[[
        "stage_name",
        "stage_share_%",
        "revenue_share_%",
        "leakage"
    ]].copy()

    st.dataframe(leakage_df)

    #visualization
    fig_leakage = px.bar(
        leakage_df,
        x="stage_name",
        y="leakage",
        title="Revenue Leakage by Stage",
        color="leakage",
        color_continuous_scale="RdYlGn_r"  # red = bad, green = good
    )

    st.plotly_chart(fig_leakage, use_container_width=True)

    #insights

    worst_stage = leakage_df.sort_values("leakage", ascending=False).iloc[0]
    best_stage = leakage_df.sort_values("leakage").iloc[0]

    st.warning(
        f"{worst_stage['stage_name']} has the highest leakage, meaning it consumes more deal volume than the revenue it generates."
    )

    st.success(
        f"{best_stage['stage_name']} is highly efficient, contributing more revenue relative to its deal volume."
    )

#EXECUTIVE RECOMMENDATION

st.markdown("## Executive Recommendation")

# signals
top_concentration_pct = round(top_rev, 1)
inefficiency_pct = round(misalloc_pct, 1)

# Build recommendation logic
recommendations = []

# Concentration driven action
if top_concentration_pct < 30:
    recommendations.append(
        "Increase focus on developing high-impact deals, as revenue is currently too distributed across low-value opportunities."
    )
else:
    recommendations.append(
        "Protect and prioritize top-performing deals, as a significant portion of revenue is concentrated in a few opportunities."
    )

#Efficiency reallocation
if inefficiency_pct > 20:
    recommendations.append(
        "Reallocate resources away from inefficient high-value deals toward opportunities with stronger return on investment."
    )
else:
    recommendations.append(
        "Maintain focus on current high-value deals, as efficiency levels are within acceptable range."
    )

#Leakage control
recommendations.append(
    f"Reduce deal volume or improve conversion performance in {worst_stage}, as it is the primary source of value leakage."
)

# Quick wins strategy
recommendations.append(
    "Accelerate execution of low-cost, high-efficiency deals to drive short-term revenue while larger deals mature."
)


for rec in recommendations:
    st.success(rec)