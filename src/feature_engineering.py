import numpy as np
import pandas as pd

# Expected revenue
def add_expected_revenue(df):

    df["expected_revenue"] = (
        df["TCV (GHS)"].fillna(0) *
        df["Probability"].fillna(0)
    )

    return df

# Distance category
def add_distance_category(df):

    bins = [
        0,
        500,
        5000,
        50000,
        float("inf")
    ]

    labels = [
        "Last Mile (<500m)",
        "Access (0.5-5km)",
        "Metro (5-50km)",
        "Backhaul (50km+)"
    ]

    df["distance_category"] = pd.cut(
        df["Distance (m)"],
        bins=bins,
        labels=labels
    )

    return df

# Revenue per meter
def add_revenue_per_meter(df):

    df["revenue_per_meter"] = (
    df["TCV (GHS)"] /
    df["Distance (m)"].replace(0, np.nan)
)

    df["revenue_per_meter"] = df["revenue_per_meter"].replace(
        [np.inf, -np.inf], np.nan
    )

    return df


# Build cost ratio
def add_build_cost_ratio(df):

    df["build_cost_ratio"] = (
        df["Build Cost (GHS)"] /
        df["TCV (GHS)"]
    )

    return df


# Payback period (months)
def add_payback_months(df):

    df["payback_months"] = (
        df["Build Cost (GHS)"] /
        df["MRC (GHS)"].replace(0, np.nan)
    )

    return df

# Revenue per Mbps
def add_revenue_per_mbps(df):

    df["revenue_per_mbps"] = (
        df["MRC (GHS)"] /
        df["Bandwidth (MBPS)"].replace(0, np.nan)
    )

    return df

# Deal size category
def add_deal_size_category(df):

    bins = [
        0,
        10000,
        50000,
        200000,
        1000000,
        float("inf")
    ]

    labels = [
        "Micro",
        "Small",
        "Medium",
        "Large",
        "Enterprise"
    ]

    df["deal_size"] = pd.cut(
        df["TCV (GHS)"],
        bins=bins,
        labels=labels
    )

    return df



# Monthly revenue per meter
def add_monthly_revenue_per_meter(df):

    df["monthly_revenue_per_meter"] = (
        df["MRC (GHS)"] /
        df["Distance (m)"].replace(0, np.nan)
    )

    return df

# Distance missing flag
def add_distance_zero_flag(df):

    df["distance_zero_flag"] = df["Distance (m)"] == 0

    return df

# TCV missing flag
def add_tcv_zero_flag(df):

    df["tcv_zero_flag"] = df["TCV (GHS)"].fillna(0) == 0

    return df

# Invalid recovery period
def add_invalid_recovery_flag(df):

    df["invalid_recovery_flag"] = df["Recovery Rate (Mths)"] < 0

    return df

# Deal status classification
# -----------------------------
def add_deal_status(df):

    df["deal_status"] = df["Current Period Stage"].apply(
        lambda x: "Closed Won"
        if "Closed Won" in str(x)
        else "Open Pipeline"
    )
  
    return df

# Deal age in days
def add_deal_age(df):

    today = pd.Timestamp.today()

    df["Initial Request Date"] = pd.to_datetime(
        df["Initial Request Date"],
        errors="coerce"
    )

    df["deal_age_days"] = (
        today - df["Initial Request Date"]
    ).dt.days

    return df

def add_deal_score(df):

    df = df.copy()

    # -----------------------------
    # SAFETY CLEANING
    # -----------------------------
    df["expected_revenue"] = pd.to_numeric(df["expected_revenue"], errors="coerce")
    df["payback_months"] = pd.to_numeric(df["payback_months"], errors="coerce")
    df["Distance (m)"] = pd.to_numeric(df["Distance (m)"], errors="coerce")
    df["Probability"] = pd.to_numeric(df["Probability"], errors="coerce")

    # Replace invalid values
    df["payback_months"] = df["payback_months"].replace(0, None)
    df["Distance (m)"] = df["Distance (m)"].replace(0, None)

    # -----------------------------
    # NORMALIZATION (0–1)
    # -----------------------------
    def normalize(series):
        return (series - series.min()) / (series.max() - series.min())

    # Revenue (higher is better)
    df["rev_score"] = np.log1p(df["expected_revenue"])
    df["rev_score"] = (
        (df["rev_score"] - df["rev_score"].min()) /
        (df["rev_score"].max() - df["rev_score"].min())
    )

    # Probability (higher is better)
    df["prob_score"] = normalize(df["Probability"])

    # Payback (lower is better → invert)
    def compute_payback_score(x):
        if pd.isna(x):
            return None
        elif x <= 12:
            return 1
        elif x <= 24:
            return 0.8
        elif x <= 48:
            return 0.5
        else:
            return 0.2
    df["payback_score"] = df["payback_months"].apply(compute_payback_score)

    # Distance (lower is better → invert)
    def compute_distance_score(x):
        if pd.isna(x):
            return 0
        elif x <= 500:
            return 1
        elif x <= 5000:
            return 0.7
        elif x <= 20000:
            return 0.4
        else:
            return 0.1


    df["distance_score"] = df["Distance (m)"].apply(compute_distance_score)

    # -----------------------------
    # WEIGHTED SCORE
    # -----------------------------
    df["deal_score"] = (
        df["rev_score"] * 0.3 +
        df["payback_score"] * 0.35 +
        df["distance_score"] * 0.25 +
        df["prob_score"] * 0.1
    ) * 100

    # -----------------------------
    # CATEGORIZATION
    # -----------------------------
    def categorize(score):
        if score >= 75:
            return "High Quality"
        elif score >= 50:
            return "Moderate"
        elif score >= 30:
            return "Low Quality"
        else:
            return "High Risk"

    df["deal_category"] = df["deal_score"].apply(categorize)

    return df