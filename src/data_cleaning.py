import pandas as pd
import re
import numpy as np
import os
from openlocationcode import openlocationcode

from feature_engineering import *



def load_raw_data(path):
    return pd.read_excel(path, sheet_name="pipeline_2026")


#basic cleaning functions
def clean_text_columns(df):

    df["Service"] = df["Service"].astype(str).str.strip().str.upper().replace("-", "UNKNOWN")
    df["Industry"] = df["Industry"].fillna("Unknown").astype(str).str.strip().str.title()

    for col in ["Site[End User]", "Town", "Region", "Industry"]:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace("Â", "", regex=False)
                .str.replace("Ã", "", regex=False)
                .str.strip()
            )

    return df


def clean_dates(df):

    cols = [
        "Initial Request Date",
        "Service Request Date",
        "Date of Last Action",
        "Date of Next Action"
    ]

    for col in cols:
        if col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                df[col] = pd.to_datetime(df[col], origin="1899-12-30", unit="D", errors="coerce")
            else:
                df[col] = pd.to_datetime(df[col], format="%d/%m/%Y", errors="coerce")
    return df


def clean_numeric(df):

    cols = [
        "NRC (GHS)", "MRC (GHS)", "ACV (GHS)", "TCV (GHS)",
        "Bandwidth (MBPS)", "Build Cost (GHS)", "Distance (m)",
        "Probability", "Weighted Forecast"
    ]

    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df

def add_master_date(df):
    import pandas as pd

    # -----------------------------
    # STEP 1: Clean raw date columns
    # -----------------------------
    date_cols = [
        "Initial Request Date",
        "Service Request Date",
        "Date of Last Action"
    ]

    today = pd.Timestamp.today().normalize()

    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
            df.loc[df[col] > today, col] = pd.NaT   # remove future garbage

    # -----------------------------
    # STEP 2: Build master date
    # -----------------------------
    df["date"] = df["Initial Request Date"]
    df["date"] = df["date"].fillna(df["Service Request Date"])
    df["date"] = df["date"].fillna(df["Date of Last Action"])

    # Ensure datetime
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # -----------------------------
    # STEP 3: Date source tracking
    # -----------------------------
    df["date_source"] = "Missing"

    df.loc[df["Initial Request Date"].notna(), "date_source"] = "Initial"

    df.loc[
        df["Initial Request Date"].isna() &
        df["Service Request Date"].notna(),
        "date_source"
    ] = "Service"

    df.loc[
        df["Initial Request Date"].isna() &
        df["Service Request Date"].isna() &
        df["Date of Last Action"].notna(),
        "date_source"
    ] = "Last Action"

    # -----------------------------
    # STEP 4: Missing flag
    # -----------------------------
    df["date_missing_flag"] = df["date"].isna()

    # -----------------------------
    # STEP 5: Time features
    # -----------------------------
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["week"] = df["date"].dt.isocalendar().week

    # -----------------------------
    # STEP 6: Deal age (fixed)
    # -----------------------------
    today = pd.Timestamp.today()

    df["deal_age_days"] = (today - df["date"]).dt.days

    # Remove negative values
    df.loc[df["deal_age_days"] < 0, "deal_age_days"] = None
    df = df[df["date"].isna() | (df["date"] <= pd.Timestamp.today().normalize())]

    # -----------------------------
    # DEBUG (remove later)
    # -----------------------------
    print("DATE DTYPE:", df["date"].dtype)
    print("NULL %:", df["date"].isna().mean())
    print("DATE RANGE:", df["date"].min(), "→", df["date"].max())
    print("\nDATE SOURCE DISTRIBUTION:")
    print(df["date_source"].value_counts(normalize=True))

    return df


def normalize_region(df):

    if "Region" not in df.columns:
        return df

    df = df.copy()

    # Convert to string safely
    df["Region"] = df["Region"].astype(str).str.strip()

    # Replace bad values BEFORE title case
    df["Region"] = df["Region"].replace(
        ["nan", "NaN", "None", "", "Null"],
        np.nan
    )

    # Standardize casing
    df["Region"] = df["Region"].str.title()

    # Fix known inconsistencies
    region_map = {
        "Greater Acc": "Greater Accra",
        "Grea Accra": "Greater Accra",
        "Greater Accra Region": "Greater Accra",

        "Brong Ahafo": "Ahafo",

        "Upper Eas": "Upper East",
        "Uppe East": "Upper East",

        "Western Region": "Western"
    }

    df["Region"] = df["Region"].replace(region_map)

    #remove junk regions
    df = df[~df["Region"].isin(["Aggregation"])]

    return df

def normalize_stage(df):

    if "Current Period Stage" not in df.columns:
        return df

    df["Current Period Stage"] = (
        df["Current Period Stage"]
        .astype(str)
        .str.strip()
    )

    stage_map = {
        "04-Solution Validation Satge": "04-Solution Validation Stage",
        "04 - Solution Validation Stage": "04-Solution Validation Stage",
        "04 Solution Validation Stage": "04-Solution Validation Stage",
    }

    df["Current Period Stage"] = df["Current Period Stage"].replace(stage_map)

    return df

def drop_unused(df):

    return df.drop(columns=[
        "Website", "Name", "Position", "Email", "Mobile"
    ], errors="ignore")

def extract_gps_code(text):

    text = str(text).upper()

    # clean noise
    text = re.sub(r'[^A-Z0-9\- ]', ' ', text)
    text = re.sub(r'\s+', ' ', text)

    # fix broken prefixes
    text = re.sub(r'\bG[- ]', 'GE-', text)

    match = re.search(
        r'\b([A-Z]{1,2})[- ]?(\d{3,4})[- ]?(\d{3,4})\b',
        text
    )

    if match:
        prefix, p1, p2 = match.groups()
        return f"{prefix}-{p1.zfill(3)}-{p2.zfill(4)}"

    return None

#coord preprocessing
def preprocess_coordinate_text(text):

    text = str(text)

    text = re.sub(r'([NSEW])(\d)', r'\1 \2', text)
    text = re.sub(r'(\d)([NSEW])', r'\1 \2', text)

    text = re.sub(r'[^\dNSEW\.\,\-\s°\'"]+', ' ', text)
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


def normalize_coords(df):

    for col in ["Latitude", "Longitude", "What Is Next"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace("\xa0", " ").str.strip()

    return df

def detect_gps(df):

    combined = (
        df.get("Latitude", pd.Series("", index=df.index)).astype(str) + " " +
        df.get("Longitude", pd.Series("", index=df.index)).astype(str) + " " +
        df.get("What Is Next", pd.Series("", index=df.index)).astype(str) + " " +
        df.get("What Is Done So Far", pd.Series("", index=df.index)).astype(str) + " " +
        df.get("Site[End User]", pd.Series("", index=df.index)).astype(str)
    )

    df["gps_code"] = combined.apply(extract_gps_code)

    return df

#gps extraction
def extract_dms(text):

    text = str(text)
    text = text.replace("°", " ").replace("'", " ").replace('"', " ")
    # normalize spacing issues
    text = re.sub(r'([NSEW])(\d)', r'\1 \2', text)
    text = re.sub(r'(\d)([NSEW])', r'\1 \2', text)
    text = re.sub(r'\s+', ' ', text)

    pattern = re.search(
        r'(\d{1,3})[° ]\s*(\d{1,2})[\' ]\s*(\d+(?:\.\d+)?)"?\s*([NS])'
        r'.*?'
        r'(\d{1,3})[° ]\s*(\d{1,2})[\' ]\s*(\d+(?:\.\d+)?)"?\s*([EW])',
        text
    )

    if not pattern:
        return np.nan, np.nan

    lat = float(pattern.group(1)) + float(pattern.group(2))/60 + float(pattern.group(3))/3600
    lon = float(pattern.group(5)) + float(pattern.group(6))/60 + float(pattern.group(7))/3600

    if pattern.group(4) == "S":
        lat *= -1
    if pattern.group(8) == "W":
        lon *= -1

    return lat, lon

#coord parsing
def extract_decimal(text):

    nums = re.findall(r'-?\d+(?:\.\d+)?', text)
    return (float(nums[0]), float(nums[1])) if len(nums) >= 2 else (np.nan, np.nan)


def extract_dms(text):

    match = re.search(
        r'(\d{1,3})°\s*(\d{1,2})\'\s*(\d+(?:\.\d+)?)"?\s*([NS])'
        r'\s*'
        r'(\d{1,3})°\s*(\d{1,2})\'\s*(\d+(?:\.\d+)?)"?\s*([EW])',
        text
    )

    if not match:
        return np.nan, np.nan

    lat = float(match.group(1)) + float(match.group(2))/60 + float(match.group(3))/3600
    lon = float(match.group(5)) + float(match.group(6))/60 + float(match.group(7))/3600

    if match.group(4) == "S": lat *= -1
    if match.group(8) == "W": lon *= -1

    return lat, lon


def extract_plus(text):

    try:
        match = re.search(r"[23456789CFGHJMPQRVWX]{4,}\+[23456789CFGHJMPQRVWX]{2,}", text)
        if match:
            dec = openlocationcode.decode(match.group())
            return dec.latitudeCenter, dec.longitudeCenter
    except:
        pass

    return np.nan, np.nan


#clean coords
def clean_coordinates(df):

    lat_list, lon_list = [], []

    for _, row in df.iterrows():

        combined = (
            f"{row.get('Latitude','')} "
            f"{row.get('Longitude','')} "
            f"{row.get('What Is Next','')} "
            f"{row.get('What Is Done So Far','')} "
            f"{row.get('Site[End User]','')}"
        )

        combined = preprocess_coordinate_text(combined)

        lat, lon = extract_decimal(combined)

        if pd.isna(lat):
            lat, lon = extract_dms(combined)

        if pd.isna(lat):
            lat, lon = extract_plus(combined)

        lat_list.append(lat)
        lon_list.append(lon)

    df["latitude_clean"] = lat_list
    df["longitude_clean"] = lon_list

    return df


#gps resolution
def normalize_gps(code):

    if pd.isna(code):
        return code

    return re.sub(r'[^A-Z0-9]', '', str(code).upper())


def resolve_gps(df):

    #guarantee gps_code exists
    if "gps_code" not in df.columns:
        df["gps_code"] = None

    path = "data/lookup/gps_lookup.csv"
    if not os.path.exists(path):
        return df

    lookup = pd.read_csv(path)
    lookup.columns = lookup.columns.str.lower()

    lookup.rename(columns={
        "lat": "latitude_gps",
        "lng": "longitude_gps"
    }, inplace=True)

    df["gps_code_norm"] = df["gps_code"].apply(normalize_gps)
    lookup["gps_code_norm"] = lookup["gps_code"].apply(normalize_gps)

    lookup = lookup.drop(columns=["gps_code"], errors="ignore")

    df = df.merge(lookup, on="gps_code_norm", how="left")

    df["latitude_clean"] = df["latitude_clean"].fillna(df["latitude_gps"])
    df["longitude_clean"] = df["longitude_clean"].fillna(df["longitude_gps"])

    return df


#finalize coords
def finalize_coords(df):

    df["lat_final"] = df["latitude_gps"].combine_first(df["latitude_clean"])
    df["lon_final"] = df["longitude_gps"].combine_first(df["longitude_clean"])

    return df

def tag_coordinate_quality(df):

    df["coord_status"] = "invalid"

    df.loc[df["latitude_clean"].notna(), "coord_status"] = "parsed"
    df.loc[df["latitude_gps"].notna(), "coord_status"] = "gps"

    return df


#diagnostics
def coord_stats(df):

    total = len(df)

    gps_col = "gps_code" if "gps_code" in df.columns else "gps_code_x"
    gps_found = df[gps_col].notna().sum()
    gps_matched = df["latitude_gps"].notna().sum() if "latitude_gps" in df.columns else 0
    parsed = df["latitude_clean"].notna().sum() if "latitude_clean" in df.columns else 0
    final = df["lat_final"].notna().sum() if "lat_final" in df.columns else 0

   # print("\n--- COORD STATS ---")
   # print(f"Total: {total}")
   # print(f"Parsed: {parsed}")
   # print(f"GPS codes found: {gps_found}")
   # print(f"GPS matched: {gps_matched}")
    #print(f"Final usable: {final}")
   # print(f"Coverage: {(final/total)*100:.2f}%")

    return df


def clean_pipeline_data(path):

    # -----------------------------
    # 1. LOAD
    # -----------------------------
    df = load_raw_data(path)

    # -----------------------------
    # 2. CLEANING (raw → usable)
    # -----------------------------
    df = clean_text_columns(df)
    df = clean_dates(df)
    df = clean_numeric(df)

    df = normalize_region(df)
    df = normalize_stage(df)

    df = normalize_coords(df)
    df = detect_gps(df)

    df = clean_coordinates(df)
    df = resolve_gps(df)

    df = finalize_coords(df)
    df = tag_coordinate_quality(df)

    df = drop_unused(df)

    # -----------------------------
    # 3. CORE MODEL FEATURES (foundation)
    # -----------------------------
    df = add_master_date(df)   # ← MOVE IT HERE

    # -----------------------------
    # 4. FEATURE ENGINEERING (analytics layer)
    # -----------------------------
    df = add_expected_revenue(df)
    df = add_revenue_per_meter(df)
    df = add_build_cost_ratio(df)
    df = add_payback_months(df)
    df = add_revenue_per_mbps(df)

    df = add_deal_size_category(df)
    df = add_distance_category(df)

    df = add_monthly_revenue_per_meter(df)

    df = add_distance_zero_flag(df)
    df = add_tcv_zero_flag(df)
    df = add_invalid_recovery_flag(df)

    df = add_deal_status(df)
    df = add_deal_age(df)
    df = add_deal_score(df) 
    
    # -----------------------------
    # 5. DATA QUALITY SUMMARY (optional but smart)
    # -----------------------------
    df = coord_stats(df)

    return df



#run
if __name__ == "__main__":

    df = clean_pipeline_data("data/raw/Sales Pipeline.xlsx")
    df.to_csv("data/processed/clean_sales_pipeline.csv", index=False, encoding="utf-8-sig")