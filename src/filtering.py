import pandas as pd
import streamlit as st


# clean base numeric fields and region
def prepare_base(df):

    df = df.copy()

    cols = [
        "TCV (GHS)",
        "expected_revenue",
        "Distance (m)",
        "payback_months",
        "build_cost_ratio"
    ]

    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # normalize distance
    if "Distance (m)" in df.columns:
        df["Distance (m)"] = df["Distance (m)"].astype(int)

    # prevent region issues
    if "Region" in df.columns:
        df["Region"] = df["Region"].fillna("Unknown")

    return df


# apply filters (UPDATED)
def apply_filters(
    df,
    region=None,
    service=None,
    status="All",
    min_rev=0,
    max_rev=None,
    min_dist=0,
    max_dist=None
    ):

    # ================================
    # DATE PREPARATION (ONCE)
    # ================================
    df = prepare_base(df)

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    valid_dates = df["date"].dropna()

    if valid_dates.empty:
        st.sidebar.warning("No valid dates available")
        start_date, end_date = None, None

    else:
        from datetime import timedelta

        min_date = valid_dates.min().date()
        max_date = valid_dates.max().date()

        st.sidebar.subheader("Date Filter")

        preset = st.sidebar.selectbox(
            "Quick Date Filter",
            ["All Time", "Last 7 Days", "Last 30 Days", "This Month", "Custom"]
        )

        # -----------------------------
        # PRESET LOGIC
        # -----------------------------
        if preset == "All Time":
            start_date, end_date = min_date, max_date

        elif preset == "Last 7 Days":
            start_date = max_date - timedelta(days=7)
            end_date = max_date

        elif preset == "Last 30 Days":
            start_date = max_date - timedelta(days=30)
            end_date = max_date

        elif preset == "This Month":
            start_date = max_date.replace(day=1)
            end_date = max_date

        # -----------------------------
        # CUSTOM LOGIC (CONTROLLED)
        # -----------------------------
        else:
            default_start = min_date
            default_end = max_date

            raw_range = st.sidebar.date_input(
                "Select Date Range",
                value=(default_start, default_end),
                min_value=min_date,
                max_value=max_date
            )

            # Normalize input
            if isinstance(raw_range, tuple):
                if len(raw_range) == 2:
                    raw_start, raw_end = raw_range
                else:
                    raw_start = raw_range[0]
                    raw_end = raw_range[0]
            else:
                raw_start = raw_range
                raw_end = raw_range

            # -----------------------------
            # HARD CLAMP + WARN
            # -----------------------------
            start_date = max(raw_start, min_date)
            end_date = min(raw_end, max_date)

            if raw_start < min_date:
                st.sidebar.warning(f"Start date adjusted to {min_date}")

            if raw_end > max_date:
                st.sidebar.warning(f"End date adjusted to {max_date}")

        # -----------------------------
        # FINAL CONVERSION (ONCE)
        # -----------------------------
        start_date = pd.to_datetime(start_date)
        end_date = pd.to_datetime(end_date)

        year_filter = st.sidebar.multiselect(
            "Year",
            options=sorted(df["date"].dt.year.dropna().unique()),
            default=[]
        )

        month_filter = st.sidebar.multiselect(
            "Month",
            options=list(range(1, 13)),
            default=[]
        )

        # -----------------------------
        # APPLY FILTER
        # -----------------------------
        if preset == "All Time":
            # DO NOT filter anything
            filtered_df = df.copy()

        else:
            filtered_df = df[
                (df["date"].notna()) &
                (df["date"] >= start_date) &
                (df["date"] <= end_date)
            ]
        df = filtered_df.copy()

        if year_filter:
            df = df[df["date"].dt.year.isin(year_filter)]

        if month_filter:
            df = df[df["date"].dt.month.isin(month_filter)]
                # -----------------------------
        # CONTEXT DISPLAY (TRUTH LAYER)
        # -----------------------------
        st.sidebar.caption(f"Data available: {min_date} → {max_date}")
        st.sidebar.caption(f"Active filter: {start_date.date()} → {end_date.date()}")

        if start_date == end_date:
            st.sidebar.warning("Single day selected. Trends may be unstable.")

    # -----------------------------
    # ACCOUNT MANAGER FILTER
    # -----------------------------
    if "Account Manager" in df.columns:
        managers = st.sidebar.multiselect(
            "Account Manager",
            sorted(df["Account Manager"].dropna().unique())
        )

        if managers:
            df = df[df["Account Manager"].isin(managers)]

    # -----------------------------
    # CUSTOMER FILTER (ISP)
    # -----------------------------
    if "ISP" in df.columns:
        customers = st.sidebar.multiselect(
            "Customer (ISP)",
            sorted(df["ISP"].dropna().unique())
        )

        if customers:
            df = df[df["ISP"].isin(customers)]

    # -----------------------------
    # EXISTING FILTERS (UNCHANGED)
    # -----------------------------

    if max_rev is None:
        max_rev = df["TCV (GHS)"].max()

    if max_dist is None:
        max_dist = df["Distance (m)"].max()

    # region filter
    if region:
        if isinstance(region, list):
            df = df[df["Region"].isin(region)]
        elif region != "All":
            df = df[df["Region"] == region]

    # service filter
    if service:
        if isinstance(service, list):
            df = df[df["Service"].isin(service)]
        elif service != "All":
            df = df[df["Service"] == service]

    # status filter
    if status != "All":
        df = df[df["deal_status"] == status]

    # numeric filters
    df = df[
        (df["TCV (GHS)"] >= min_rev) &
        (df["TCV (GHS)"] <= max_rev + 10) &
        (df["Distance (m)"] >= min_dist) &
        (df["Distance (m)"] <= max_dist + 1000)
    ]

    # -----------------------------
    # CREATE TIME-SAFE DATASET
    # -----------------------------
    if "date" in df.columns:
        df_time_filtered = df[df["date"].notna()].copy()
    else:
        df_time_filtered = df.copy()

    return df, df_time_filtered


# map data extraction (unchanged)
def get_map_data(df):

    map_df = df.dropna(subset=["lat_final", "lon_final"]).copy()

    # Ghana bounds
    map_df = map_df[
        (map_df["lat_final"].between(4, 11)) &
        (map_df["lon_final"].between(-3, 2))
    ]

    return map_df