"""
Sahaay AI — Phase 10 Data Suitability & Feature Data Dictionary Generator
Audits the raw and derived rainfall, geospatial, and telemetry datasets,
generates the official feature data dictionary CSV, and exports data_suitability.json.
"""

import os
import sys
import json
import math
import pandas as pd
import numpy as np

def generate_data_suitability_audit():
    print("Executing Phase 10 Data Suitability & Dictionary Audit...")
    os.makedirs("reports/phase10", exist_ok=True)
    os.makedirs("docs", exist_ok=True)

    # 1. Feature Data Dictionary
    dictionary_records = [
        {
            "feature_name": "location_id",
            "meaning": "Unique corridor identifier",
            "data_source": "Sahaay Phase 4 Corridor Register",
            "spatial_resolution": "Corridor line segment (~1-3 km)",
            "temporal_resolution": "Static",
            "units": "Alphanumeric string (HYD-LOC-xxx)",
            "missing_value_semantics": "Disallowed (mandatory primary key)",
            "feature_type": "derived",
            "label_availability": "None (spatial identifier)",
            "potential_leakage_pathways": "None",
            "intended_use_and_limitations": "Index key for multi-source feature alignment."
        },
        {
            "feature_name": "dist_to_flood_hotspot_m",
            "meaning": "Great-circle distance to nearest historical waterlogging recurrence placemark",
            "data_source": "TRAC Telangana / GHMC (flooding_locations.kml)",
            "spatial_resolution": "Point location (~10-50m GPS accuracy)",
            "temporal_resolution": "Static (historical compilation)",
            "units": "Meters",
            "missing_value_semantics": "Defaults to 99999.0m (UNKNOWN)",
            "feature_type": "derived",
            "label_availability": "Static recurrence points only; NO timestamps or depths",
            "potential_leakage_pathways": "Using this distance as a proxy for flood occurrence causes spatial target leakage.",
            "intended_use_and_limitations": "Static susceptibility proxy only. Cannot predict when a flood occurs."
        },
        {
            "feature_name": "dist_to_nearest_drain_m",
            "meaning": "Orthogonal distance to nearest open stormwater drain / nala line segment",
            "data_source": "GHMC via OpenCity (hyderabad_drains.kml)",
            "spatial_resolution": "Vector LineString (96 nala segments)",
            "temporal_resolution": "Static",
            "units": "Meters",
            "missing_value_semantics": "Defaults to 99999.0m (UNKNOWN)",
            "feature_type": "derived",
            "label_availability": "None",
            "potential_leakage_pathways": "None",
            "intended_use_and_limitations": "Proxy for drainage overflow proximity. Cross-sectional capacity and desilting state unrecorded."
        },
        {
            "feature_name": "dist_to_nearest_waterbody_m",
            "meaning": "Distance to nearest lake, tank, or pond polygon boundary",
            "data_source": "TRAC Telangana via OpenCity (greater_hyderabad_waterbodies.geojson)",
            "spatial_resolution": "Vector Polygon (2,324 water bodies)",
            "temporal_resolution": "Static",
            "units": "Meters",
            "missing_value_semantics": "Defaults to 99999.0m (UNKNOWN)",
            "feature_type": "derived",
            "label_availability": "None",
            "potential_leakage_pathways": "None",
            "intended_use_and_limitations": "Catchment depression proxy. Sluice gate operation and bund heights unrecorded."
        },
        {
            "feature_name": "vulnerability_index",
            "meaning": "Multi-criteria weighted static susceptibility index",
            "data_source": "Sahaay Road Vulnerability Engine",
            "spatial_resolution": "Corridor buffer",
            "temporal_resolution": "Static",
            "units": "Normalized continuous score [0.0, 1.0]",
            "missing_value_semantics": "Reverts to subscore defaults if layers missing",
            "feature_type": "heuristic",
            "label_availability": "None (heuristic formula output)",
            "potential_leakage_pathways": "Training an ML model to predict this score is rule imitation, not flood forecasting.",
            "intended_use_and_limitations": "Heuristic ranking (45% hotspot, 35% drain, 20% waterbody). Represents physical exposure, not active flooding."
        },
        {
            "feature_name": "rain_1h_mm",
            "meaning": "Observed rainfall accumulation over preceding 1-hour window",
            "data_source": "NWIC / Telangana SW Dept Telemetry",
            "spatial_resolution": "Point rain gauge (nearest regional station)",
            "temporal_resolution": "Hourly",
            "units": "Millimeters",
            "missing_value_semantics": "Explicit None -> Triggers UNKNOWN category with confidence 0.10. NEVER silently filled with 0.0mm.",
            "feature_type": "observed",
            "label_availability": "Continuous physical quantity",
            "potential_leakage_pathways": "Silently imputing 0.0mm during station outages causes underestimation leakage.",
            "intended_use_and_limitations": "Telemetry stations are 35-50km outside GHMC core. In convective storms, radar/AWS pairing required."
        },
        {
            "feature_name": "rain_3h_mm",
            "meaning": "Observed rolling 3-hour rainfall accumulation",
            "data_source": "NWIC / Telangana SW Dept Telemetry",
            "spatial_resolution": "Point rain gauge",
            "temporal_resolution": "3-hour rolling window",
            "units": "Millimeters",
            "missing_value_semantics": "Explicit None -> Excluded from multi-window surge evaluation without penalty.",
            "feature_type": "derived",
            "label_availability": "Continuous physical quantity",
            "potential_leakage_pathways": "Lookahead leakage if future hours included in rolling sum.",
            "intended_use_and_limitations": "Flash surge detector (threshold: >= 40.0mm / 3h)."
        },
        {
            "feature_name": "rain_24h_mm",
            "meaning": "Observed rolling 24-hour rainfall accumulation",
            "data_source": "NWIC / Telangana SW Dept Telemetry",
            "spatial_resolution": "Point rain gauge",
            "temporal_resolution": "24-hour rolling window",
            "units": "Millimeters",
            "missing_value_semantics": "Explicit None -> Excluded from saturation amplification.",
            "feature_type": "derived",
            "label_availability": "Continuous physical quantity",
            "potential_leakage_pathways": "Lookahead leakage if non-causal window used.",
            "intended_use_and_limitations": "Soil catchment saturation indicator (thresholds: >= 64.5mm heavy, >= 115.5mm very heavy)."
        },
        {
            "feature_name": "hist_month_mean_mm",
            "meaning": "121-year historical mean monthly precipitation for current calendar month",
            "data_source": "IMD Hyderabad Gridded Series (1901-2021)",
            "spatial_resolution": "Hyderabad coordinate centroid grid (0.25 deg)",
            "temporal_resolution": "Monthly climatology",
            "units": "Millimeters",
            "missing_value_semantics": "None",
            "feature_type": "historical",
            "label_availability": "None",
            "potential_leakage_pathways": "Using monthly historical data as a real-time forecast variable.",
            "intended_use_and_limitations": "Long-term climatological context only. Cannot be used for sub-daily flash flood forecasting."
        },
        {
            "feature_name": "hist_month_p90_mm",
            "meaning": "90th percentile historical monthly rainfall for current calendar month",
            "data_source": "IMD Hyderabad Gridded Series (1901-2021)",
            "spatial_resolution": "Hyderabad coordinate centroid grid",
            "temporal_resolution": "Monthly climatology",
            "units": "Millimeters",
            "missing_value_semantics": "None",
            "feature_type": "historical",
            "label_availability": "None",
            "potential_leakage_pathways": "None",
            "intended_use_and_limitations": "Extreme monsoonal anomaly benchmarking (e.g. 24h rain exceeding 50% of monthly p90)."
        },
        {
            "feature_name": "nearest_station_dist_km",
            "meaning": "Great-circle distance from corridor to nearest reporting telemetry station",
            "data_source": "Derived from NWIC station coordinates",
            "spatial_resolution": "Kilometers",
            "temporal_resolution": "Static per station pairing",
            "units": "Kilometers",
            "missing_value_semantics": "Defaults to 50.0km",
            "feature_type": "derived",
            "label_availability": "None",
            "potential_leakage_pathways": "None",
            "intended_use_and_limitations": "Quality-discounting penalty (stations > 15km lose confidence up to -0.35)."
        },
        {
            "feature_name": "telemetry_freshness_hours",
            "meaning": "Elapsed time since last valid telemetry transmission",
            "data_source": "Telemetry stream timestamp difference",
            "spatial_resolution": "Station level",
            "temporal_resolution": "Dynamic observation age",
            "units": "Hours",
            "missing_value_semantics": "Defaults to 999.0h (stale)",
            "feature_type": "derived",
            "label_availability": "None",
            "potential_leakage_pathways": "None",
            "intended_use_and_limitations": "Quality-discounting penalty (telemetry > 1.5h old loses confidence up to -0.40)."
        },
        {
            "feature_name": "rainfall_risk_score",
            "meaning": "Calculated continuous rainfall intensity and accumulation risk score",
            "data_source": "Sahaay Rainfall Risk Engine",
            "spatial_resolution": "Corridor buffer",
            "temporal_resolution": "Dynamic",
            "units": "Normalized continuous score [0.0, 1.0]",
            "missing_value_semantics": "0.0 if rain_1h_mm is missing (with category=UNKNOWN)",
            "feature_type": "heuristic",
            "label_availability": "None (formula output)",
            "potential_leakage_pathways": "Supervised training to predict this score is rule distillation.",
            "intended_use_and_limitations": "Advisory intensity ranking calibrated against IMD thresholds."
        },
        {
            "feature_name": "rainfall_risk_category",
            "meaning": "Categorical rainfall risk tier (LOW, MEDIUM, HIGH, CRITICAL, UNKNOWN)",
            "data_source": "Sahaay Rainfall Risk Engine",
            "spatial_resolution": "Corridor buffer",
            "temporal_resolution": "Dynamic",
            "units": "Enum string",
            "missing_value_semantics": "UNKNOWN when rain_1h_mm is None",
            "feature_type": "heuristic",
            "label_availability": "None (discrete rule binning)",
            "potential_leakage_pathways": "Rule imitation.",
            "intended_use_and_limitations": "Operational threshold triggers for Decision Engine."
        }
    ]

    dict_df = pd.DataFrame(dictionary_records)
    dict_csv_path = "reports/phase10/feature_data_dictionary.csv"
    dict_df.to_csv(dict_csv_path, index=False)
    print(f"Saved {dict_csv_path}")

    # 2. Telemetry and Data Suitability Forensic Audit
    telemetry_path = "data/hyderabad_risk/raw/telangana_hourly_telemetry_rainfall_2021_2025.csv"
    telemetry_df = pd.read_csv(telemetry_path)
    total_telemetry_records = len(telemetry_df)
    unique_stations = int(telemetry_df['Station'].nunique())
    unique_districts = list(telemetry_df['District'].dropna().unique())

    rain_vals = telemetry_df['Telemetry Hourly Rainfall (mm)']
    negative_glitches = int((rain_vals < 0).sum())
    accumulator_anomalies = int((rain_vals > 250).sum())
    accumulator_percentage = round((accumulator_anomalies / total_telemetry_records) * 100.0, 2)

    # Station-specific temporal continuity
    station_continuity = {}
    for st_name in ["AKBR", "Kondapochamma Resrvoir", "Boggulawagu", "Ghanpur Lake_1"]:
        st = telemetry_df[telemetry_df['Station'] == st_name].copy()
        st['dt'] = pd.to_datetime(st['Data Acquisition Time'], format='%d-%m-%Y %H:%M', errors='coerce')
        st = st.sort_values('dt').dropna(subset=['dt'])
        diffs = st['dt'].diff()
        
        station_continuity[st_name] = {
            "record_count": len(st),
            "start_time": st['dt'].min().isoformat() if not st.empty else None,
            "end_time": st['dt'].max().isoformat() if not st.empty else None,
            "duplicate_zero_diff_timestamps": int((diffs == pd.Timedelta(0)).sum()),
            "hourly_steps_count": int((diffs == pd.Timedelta(hours=1)).sum()),
            "max_gap_days": round(diffs.max().total_seconds() / 86400.0, 1) if not diffs.empty and pd.notna(diffs.max()) else None,
            "effective_temporal_coverage_pct": round((len(st) / (st['dt'].max() - st['dt'].min()).total_seconds() * 3600.0) * 100.0, 2) if len(st) > 1 else 0.0
        }

    # Task Suitability Matrix
    task_suitability = {
        "task_a_rainfall_forecasting": {
            "task_title": "Short-Term Hourly Rainfall Forecasting",
            "is_supervised_ml_feasible": False,
            "experiment_status": "NOT_RUN",
            "blocking_reasons": [
                "Telemetry reporting exhibits massive temporal missingness (> 90% missing hours).",
                "Extreme transmission gaps (up to 141.6 consecutive days with zero records).",
                "Over 50.8% of records reflect seasonal bucket accumulator counters (> 250 mm up to 3,406 mm) rather than incremental hourly rain.",
                "Zero telemetry stations exist within the GHMC urban core; nearest station is 35-50 km away."
            ],
            "required_data_to_unlock": "Continuous 15-minute AWS telemetry with >= 98% uptime and automated accumulator counter differencing."
        },
        "task_b_flood_occurrence_prediction": {
            "task_title": "Supervised Flood Occurrence Prediction (Binary / Depth)",
            "is_supervised_ml_feasible": False,
            "experiment_status": "NOT_RUN",
            "blocking_reasons": [
                "flooding_locations.kml contains 23 static historical placemarks with ZERO timestamps, dates, or depth measurements.",
                "Real-world observation database contains exactly 0 observations (Phase 8 activation gate blocked at BLOCKED_NOT_READY_FOR_LIVE_PILOT).",
                "Labeling static hotspots as positive targets causes 100% spatial target leakage, memorizing placemarks rather than predicting flood events."
            ],
            "required_data_to_unlock": "Minimum 50 verified flood episodes (depth >= 5 cm) and 100 non-flood episodes across >= 4 storm dates."
        },
        "task_c_road_vulnerability_ranking": {
            "task_title": "Road Vulnerability Index Modeling",
            "is_supervised_ml_feasible": False,
            "experiment_status": "NOT_RUN",
            "blocking_reasons": [
                "Vulnerability index is an explainable heuristic multi-criteria formula (45% hotspot, 35% drain, 20% waterbody).",
                "Supervised training against heuristic scores is formula distillation / rule imitation, not predictive ML.",
                "No independent road inundation damage outcomes exist to validate predictive performance."
            ],
            "recommended_treatment": "Retain as an auditable, transparent rules-based baseline."
        },
        "task_d_rainfall_risk_classification": {
            "task_title": "Rainfall Risk Tier Classification (LOW/MED/HIGH/CRITICAL)",
            "is_supervised_ml_feasible": False,
            "experiment_status": "NOT_RUN",
            "blocking_reasons": [
                "Risk categories are directly mapped from deterministic IMD thresholds (7.5, 15.0, 35.0 mm/hr).",
                "Training an ML classifier on these rule outputs is rule imitation with zero generalization value."
            ],
            "recommended_treatment": "Retain deterministic rules-based engine with explicit confidence discounting."
        }
    }

    suitability_report = {
        "report_timestamp_utc": pd.Timestamp.now("UTC").isoformat(),
        "phase": "Phase 10 Data Suitability & ML Feasibility Audit",
        "raw_datasets_audited": {
            "flooding_locations_kml": {"placemarks": 23, "has_timestamps": False, "has_depths": False},
            "hyderabad_drains_kml": {"lines": 96, "has_capacity": False},
            "greater_hyderabad_waterbodies_geojson": {"polygons": 2324, "has_bund_heights": False},
            "hyderabad_monthly_rainfall_csv": {"years": 121, "start_year": 1901, "end_year": 2021, "resolution": "monthly"},
            "telangana_hourly_telemetry_rainfall_csv": {
                "total_records": total_telemetry_records,
                "stations": unique_stations,
                "districts": len(unique_districts),
                "hyderabad_district_included": False,
                "accumulator_records_gt_250mm": accumulator_anomalies,
                "accumulator_percentage": accumulator_percentage,
                "negative_sensor_glitches": negative_glitches
            }
        },
        "station_continuity_sampling": station_continuity,
        "task_suitability": task_suitability,
        "primary_conclusions": [
            "No valid timestamped ground-truth flood outcome labels exist in the repository.",
            "Static hotspot coordinates cannot be substituted for flood event labels.",
            "Regional telemetry cannot support live temporal forecasting due to >90% temporal missingness and accumulator counter confusion.",
            "Existing rules-based rainfall and road-vulnerability baselines are mathematically transparent and must be preserved as the reference standard."
        ]
    }

    suit_json_path = "reports/phase10/data_suitability.json"
    with open(suit_json_path, "w", encoding="utf-8") as f:
        json.dump(suitability_report, f, indent=2)
    print(f"Saved {suit_json_path}")

if __name__ == "__main__":
    generate_data_suitability_audit()
