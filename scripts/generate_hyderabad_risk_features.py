"""
Sahaay AI - Generate Hyderabad Geospatial & Hydrological Risk Features
Computes multi-source feature vectors for 20 candidate Hyderabad road corridors,
evaluates explainable baseline risk engines, and outputs derived CSV and manifest.
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# Ensure 'src' is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from sahaay.hyderabad_risk.features import (
    compute_drain_proximity,
    compute_hotspot_proximity,
    compute_rolling_rainfall,
    compute_waterbody_proximity,
    find_nearest_telemetry_station,
    get_climatological_baseline,
)
from sahaay.hyderabad_risk.ingest import (
    load_monthly_rainfall,
    load_telemetry_rainfall,
    parse_drains_kml,
    parse_flooding_hotspots,
    parse_waterbodies_geojson,
)
from sahaay.hyderabad_risk.rainfall_engine import evaluate_rainfall_risk_engine
from sahaay.hyderabad_risk.schemas import GeospatialRiskFeatureVector
from sahaay.hyderabad_risk.validate import validate_telemetry_rainfall
from sahaay.hyderabad_risk.vulnerability_engine import evaluate_road_vulnerability_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_features")

# 20 Candidate Corridors from Phase 2 / Phase 3 Acquisition Architecture
CANDIDATE_CORRIDORS = [
    {"id": "HYD-LOC-001", "name": "Tolichowki Flyover Underpass", "lat": 17.4023, "lon": 78.4112, "zone": "West Zone"},
    {"id": "HYD-LOC-002", "name": "Shaikpet Nala Road", "lat": 17.4095, "lon": 78.3986, "zone": "West Zone"},
    {"id": "HYD-LOC-003", "name": "Begumpet Rasoolpura Underpass", "lat": 17.4419, "lon": 78.4728, "zone": "North Zone"},
    {"id": "HYD-LOC-004", "name": "Khairatabad Flyover Junction", "lat": 17.4116, "lon": 78.4611, "zone": "Central Zone"},
    {"id": "HYD-LOC-005", "name": "Malakpet Railway Underbridge", "lat": 17.3768, "lon": 78.4975, "zone": "South Zone"},
    {"id": "HYD-LOC-006", "name": "Panjagutta Underpass & Nagarjuna Circle", "lat": 17.4262, "lon": 78.4518, "zone": "Central Zone"},
    {"id": "HYD-LOC-007", "name": "Gachibowli Bio-Diversity Junction", "lat": 17.4428, "lon": 78.3654, "zone": "West Zone"},
    {"id": "HYD-LOC-008", "name": "Lakdikapul Junction & Railway Bridge", "lat": 17.4042, "lon": 78.4651, "zone": "Central Zone"},
    {"id": "HYD-LOC-009", "name": "Secunderabad Clock Tower Subway", "lat": 17.4431, "lon": 78.4998, "zone": "North Zone"},
    {"id": "HYD-LOC-010", "name": "Musarambagh Bridge Causeway", "lat": 17.3712, "lon": 78.5085, "zone": "East Zone"},
    {"id": "HYD-LOC-011", "name": "Madhapur Cyber Towers Corridor", "lat": 17.4504, "lon": 78.3808, "zone": "West Zone"},
    {"id": "HYD-LOC-012", "name": "Dilsukhnagar Bus Depot Main Road", "lat": 17.3688, "lon": 78.5247, "zone": "East Zone"},
    {"id": "HYD-LOC-013", "name": "Ameerpet Metro Junction", "lat": 17.4375, "lon": 78.4482, "zone": "Central Zone"},
    {"id": "HYD-LOC-014", "name": "Moosarambagh to Amberpet Nala Link", "lat": 17.3821, "lon": 78.5142, "zone": "Central Zone"},
    {"id": "HYD-LOC-015", "name": "Miyapur Allwyn Junction", "lat": 17.4965, "lon": 78.3548, "zone": "West Zone"},
    {"id": "HYD-LOC-016", "name": "Uppal Ring Road Junction", "lat": 17.4018, "lon": 78.5602, "zone": "East Zone"},
    {"id": "HYD-LOC-017", "name": "Bowenpally Check Post", "lat": 17.4725, "lon": 78.4764, "zone": "North Zone"},
    {"id": "HYD-LOC-018", "name": "Mehdipatnam Rythu Bazaar Road", "lat": 17.3916, "lon": 78.4402, "zone": "Central Zone"},
    {"id": "HYD-LOC-019", "name": "Balanagar Narasapur Cross Road", "lat": 17.4691, "lon": 78.4468, "zone": "North Zone"},
    {"id": "HYD-LOC-020", "name": "Alwal Rythu Bazaar Low-Lying Area", "lat": 17.5024, "lon": 78.5031, "zone": "North Zone"},
]


def generate_corridor_features(
    raw_dir: Path,
    output_dir: Path,
    target_dt: Optional[datetime] = None
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Main feature extraction pipeline.
    """
    raw_dir = Path(raw_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if target_dt is None:
        # Benchmark active rainfall event at nearest Hyderabad telemetry station (Kondapochamma Reservoir)
        target_dt = datetime(2023, 12, 1, 19, 0)

    logger.info("Step 1: Ingesting raw geospatial & hydrological datasets...")
    hotspots = parse_flooding_hotspots(raw_dir / "flooding_locations.kml")
    drains = parse_drains_kml(raw_dir / "hyderabad_drains.kml")
    waterbodies = parse_waterbodies_geojson(raw_dir / "greater_hyderabad_waterbodies.geojson")
    monthly_df = load_monthly_rainfall(raw_dir / "hyderabad_monthly_rainfall_1901_2021.csv")
    telemetry_raw_df = load_telemetry_rainfall(raw_dir / "telangana_hourly_telemetry_rainfall_2021_2025.csv")

    logger.info("Step 2: Validating telemetry rainfall...")
    telemetry_clean_df, qc_report = validate_telemetry_rainfall(telemetry_raw_df)

    stations_df = telemetry_clean_df[["Station", "District", "Latitude", "Longitude"]].drop_duplicates()

    logger.info("Step 3: Deriving multi-source feature vectors for 20 corridors...")
    features_list: List[Dict[str, Any]] = []

    # Historical climatological baseline for monsoon month (July/August)
    hist_mean_mm, hist_p90_mm = get_climatological_baseline(month=7, monthly_df=monthly_df)

    now_iso = datetime.utcnow().isoformat() + "Z"

    for c in CANDIDATE_CORRIDORS:
        loc_id = c["id"]
        name = c["name"]
        lat = c["lat"]
        lon = c["lon"]

        # Geospatial proximity
        dist_hotspot_m, nearest_hotspot = compute_hotspot_proximity(lat, lon, hotspots)
        dist_drain_m = compute_drain_proximity(lat, lon, drains)
        dist_wb_m, nearest_wb = compute_waterbody_proximity(lat, lon, waterbodies)

        # Nearest telemetry station
        st_id, st_dist_km = find_nearest_telemetry_station(lat, lon, stations_df)

        # Rolling rainfall
        rolling = compute_rolling_rainfall(st_id, target_dt, telemetry_clean_df)

        # Evaluate Road Vulnerability Engine (Static)
        vuln_res = evaluate_road_vulnerability_engine(
            location_id=loc_id,
            road_name=name,
            dist_to_hotspot_m=dist_hotspot_m,
            nearest_hotspot_name=nearest_hotspot,
            dist_to_drain_m=dist_drain_m,
            dist_to_waterbody_m=dist_wb_m,
            nearest_waterbody_name=nearest_wb,
        )

        # Evaluate Rainfall Risk Engine (Dynamic)
        rain_res = evaluate_rainfall_risk_engine(
            location_id=loc_id,
            rain_1h_mm=rolling.get("rain_1h_mm"),
            rain_3h_mm=rolling.get("rain_3h_mm"),
            rain_6h_mm=rolling.get("rain_6h_mm"),
            rain_24h_mm=rolling.get("rain_24h_mm"),
            station_dist_km=st_dist_km,
            data_freshness_hours=rolling.get("freshness_hours") if rolling.get("freshness_hours") is not None else 99.0,
            data_timestamp=target_dt.isoformat() + "Z",
            historical_month_p90_mm=hist_p90_mm,
        )

        row = {
            "location_id": loc_id,
            "corridor_name": name,
            "zone": c["zone"],
            "latitude": lat,
            "longitude": lon,
            "dist_to_flood_hotspot_m": dist_hotspot_m,
            "nearest_hotspot_name": nearest_hotspot,
            "dist_to_nearest_drain_m": dist_drain_m,
            "dist_to_nearest_waterbody_m": dist_wb_m,
            "nearest_waterbody_name": nearest_wb,
            "nearest_telemetry_station": st_id,
            "nearest_station_dist_km": st_dist_km,
            "telemetry_freshness_hours": rolling.get("freshness_hours"),
            "rain_1h_mm": rolling.get("rain_1h_mm"),
            "rain_3h_mm": rolling.get("rain_3h_mm"),
            "rain_6h_mm": rolling.get("rain_6h_mm"),
            "rain_24h_mm": rolling.get("rain_24h_mm"),
            "hist_month_mean_mm": hist_mean_mm,
            "hist_month_p90_mm": hist_p90_mm,
            "vulnerability_index": vuln_res.vulnerability_index,
            "vulnerability_category": vuln_res.vulnerability_category,
            "rainfall_risk_score": rain_res.risk_score,
            "rainfall_risk_category": rain_res.risk_category,
            "confidence_score": rain_res.confidence,
            "generated_at_utc": now_iso,
        }
        features_list.append(row)

    df_out = pd.DataFrame(features_list)
    csv_path = output_dir / "hyderabad_risk_features.csv"
    df_out.to_csv(csv_path, index=False)
    logger.info(f"Successfully exported {len(df_out)} feature vectors to {csv_path}")

    # Generate Manifest
    manifest = {
        "manifest_name": "Sahaay AI Phase 4 - Hyderabad Risk Features Manifest",
        "generated_at_utc": now_iso,
        "corridors_analyzed": len(df_out),
        "target_timestamp": target_dt.isoformat() + "Z",
        "source_datasets": [
            "data/hyderabad_risk/raw/flooding_locations.kml",
            "data/hyderabad_risk/raw/hyderabad_drains.kml",
            "data/hyderabad_risk/raw/greater_hyderabad_waterbodies.geojson",
            "data/hyderabad_risk/raw/hyderabad_monthly_rainfall_1901_2021.csv",
            "data/hyderabad_risk/raw/telangana_hourly_telemetry_rainfall_2021_2025.csv"
        ],
        "derived_files": {
            "features_csv": str(csv_path),
            "rows": len(df_out),
            "columns": list(df_out.columns)
        },
        "vulnerability_distribution": df_out["vulnerability_category"].value_counts().to_dict(),
        "rainfall_risk_distribution": df_out["rainfall_risk_category"].value_counts().to_dict(),
        "mean_vulnerability_index": round(float(df_out["vulnerability_index"].mean()), 3),
        "mean_confidence_score": round(float(df_out["confidence_score"].mean()), 2),
    }

    manifest_path = output_dir / "feature_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    logger.info(f"Successfully exported feature manifest to {manifest_path}")
    return df_out, manifest


if __name__ == "__main__":
    generate_corridor_features(
        raw_dir=Path("data/hyderabad_risk/raw"),
        output_dir=Path("data/hyderabad_risk/derived")
    )
