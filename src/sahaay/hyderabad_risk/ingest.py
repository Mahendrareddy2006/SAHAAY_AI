"""
Sahaay AI - Hyderabad Geospatial & Rainfall Risk AI Data Ingest Module
Handles loading, parsing, and structured extraction of KML, GeoJSON, and CSV datasets.
"""

import csv
import json
import logging
import math
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from sahaay.hyderabad_risk.schemas import (
    DrainLine,
    FloodingHotspot,
    TelemetryRainfallRecord,
    WaterBody,
)

logger = logging.getLogger(__name__)

# KML Namespace
KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}


def parse_flooding_hotspots(kml_path: Path) -> List[FloodingHotspot]:
    """
    Parses OpenCity/TRAC Hyderabad waterlogging hotspots KML.
    Extracts 23 known chronic waterlogging locations.
    Note: In KML, coordinates are formatted as: lon,lat,alt.
    """
    kml_path = Path(kml_path)
    if not kml_path.exists():
        raise FileNotFoundError(f"Flooding hotspots KML not found at: {kml_path}")

    tree = ET.parse(kml_path)
    root = tree.getroot()

    hotspots: List[FloodingHotspot] = []
    # Search for Placemarks
    for idx, placemark in enumerate(root.iter("{http://www.opengis.net/kml/2.2}Placemark")):
        name_elem = placemark.find("kml:name", KML_NS)
        name = name_elem.text.strip() if name_elem is not None and name_elem.text else f"Hotspot_{idx+1}"

        coord_elem = placemark.find(".//kml:Point/kml:coordinates", KML_NS)
        if coord_elem is None or not coord_elem.text:
            continue

        raw_coords = coord_elem.text.strip().split(",")
        if len(raw_coords) >= 2:
            try:
                lon = float(raw_coords[0])
                lat = float(raw_coords[1])
                hotspots.append(
                    FloodingHotspot(
                        hotspot_id=f"HOTSPOT-{idx+1:03d}",
                        name=name,
                        latitude=lat,
                        longitude=lon,
                        source="TRAC_GHMC_OpenCity",
                    )
                )
            except ValueError as e:
                logger.warning(f"Skipping malformed coordinate in {name}: {raw_coords} - {e}")

    logger.info(f"Successfully ingested {len(hotspots)} flooding hotspots from {kml_path.name}")
    return hotspots


def parse_drains_kml(kml_path: Path) -> List[DrainLine]:
    """
    Parses GHMC major drains and nala networks KML.
    Extracts LineString geometries as lists of (latitude, longitude) tuples.
    """
    kml_path = Path(kml_path)
    if not kml_path.exists():
        raise FileNotFoundError(f"Drains KML not found at: {kml_path}")

    tree = ET.parse(kml_path)
    root = tree.getroot()

    drains: List[DrainLine] = []
    for idx, placemark in enumerate(root.iter("{http://www.opengis.net/kml/2.2}Placemark")):
        name_elem = placemark.find(".//kml:SimpleData[@name='Nala_Name']", KML_NS)
        id_elem = placemark.find(".//kml:SimpleData[@name='Nala_ID']", KML_NS)
        
        nala_name = name_elem.text.strip() if name_elem is not None and name_elem.text else f"Nala_{idx+1}"
        nala_id = id_elem.text.strip() if id_elem is not None and id_elem.text else f"NALA-{idx+1:03d}"

        # Find LineString coordinates
        coords_elements = placemark.findall(".//kml:LineString/kml:coordinates", KML_NS)
        for c_elem in coords_elements:
            if not c_elem.text:
                continue
            point_tuples: List[Tuple[float, float]] = []
            for token in c_elem.text.strip().split():
                parts = token.split(",")
                if len(parts) >= 2:
                    try:
                        lon = float(parts[0])
                        lat = float(parts[1])
                        point_tuples.append((lat, lon))
                    except ValueError:
                        continue
            if len(point_tuples) >= 2:
                drains.append(
                    DrainLine(
                        drain_id=f"{nala_id}_{len(drains)+1}",
                        name=nala_name,
                        coordinates=point_tuples,
                        point_count=len(point_tuples),
                    )
                )

    logger.info(f"Successfully ingested {len(drains)} drain segments from {kml_path.name}")
    return drains


def parse_waterbodies_geojson(geojson_path: Path, max_features: Optional[int] = None) -> List[WaterBody]:
    """
    Parses Greater Hyderabad water bodies and lake boundaries GeoJSON.
    Extracts polygon features, computes centroids and areas.
    """
    geojson_path = Path(geojson_path)
    if not geojson_path.exists():
        raise FileNotFoundError(f"Waterbodies GeoJSON not found at: {geojson_path}")

    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    waterbodies: List[WaterBody] = []
    features = data.get("features", [])
    if max_features:
        features = features[:max_features]

    for idx, feat in enumerate(features):
        props = feat.get("properties", {})
        geom = feat.get("geometry", {})
        
        name = props.get("Tank_Name", "").strip() or props.get("DMV_N", "").strip() or f"Waterbody_{idx+1}"
        wb_id = f"WB-{props.get('OBJECTID', idx+1)}"
        area = float(props.get("Shape_Area", 0.0) or 0.0)

        # Compute centroid from coordinates
        coords = geom.get("coordinates", [])
        geom_type = geom.get("type", "")
        
        all_lats: List[float] = []
        all_lons: List[float] = []
        
        if geom_type == "Polygon" and coords:
            for ring in coords:
                for pt in ring:
                    if len(pt) >= 2:
                        all_lons.append(pt[0])
                        all_lats.append(pt[1])
        elif geom_type == "MultiPolygon" and coords:
            for poly in coords:
                for ring in poly:
                    for pt in ring:
                        if len(pt) >= 2:
                            all_lons.append(pt[0])
                            all_lats.append(pt[1])

        if all_lats and all_lons:
            c_lat = sum(all_lats) / len(all_lats)
            c_lon = sum(all_lons) / len(all_lons)
            waterbodies.append(
                WaterBody(
                    waterbody_id=wb_id,
                    name=name,
                    centroid_lat=c_lat,
                    centroid_lon=c_lon,
                    area_sq_m=area,
                )
            )

    logger.info(f"Successfully ingested {len(waterbodies)} waterbody polygons from {geojson_path.name}")
    return waterbodies


def load_monthly_rainfall(csv_path: Path) -> pd.DataFrame:
    """
    Loads IMD Hyderabad 121-year monthly rainfall series (1901-2021).
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Monthly rainfall CSV not found at: {csv_path}")

    df = pd.read_csv(csv_path)
    required_cols = ["Year", "Jan", "Feb", "Mar", "April", "May", "June", "July", "Aug", "Sept", "Oct", "Nov", "Dec", "Total"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Monthly rainfall CSV missing columns: {missing}")

    logger.info(f"Successfully loaded {len(df)} years of monthly rainfall from {csv_path.name}")
    return df


def load_telemetry_rainfall(csv_path: Path) -> pd.DataFrame:
    """
    Loads National Water Data Portal / Telangana Surface Water telemetry rainfall CSV.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Telemetry rainfall CSV not found at: {csv_path}")

    df = pd.read_csv(csv_path)
    expected_cols = ["Station", "District", "Latitude", "Longitude", "Data Acquisition Time", "Telemetry Hourly Rainfall (mm)"]
    for col in expected_cols:
        if col not in df.columns:
            raise ValueError(f"Telemetry rainfall CSV missing expected column: {col}")

    logger.info(f"Successfully loaded {len(df)} raw telemetry rainfall rows from {csv_path.name}")
    return df
