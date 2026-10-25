"""
Sahaay AI - Phase 4 Hyderabad Risk Data Acquisition Script

Downloads authentic, unmodified public datasets from OpenCity and the National Water Data Portal:
1. Hyderabad Flooding Locations (KML) - GHMC / TRAC via OpenCity
2. Hyderabad Canals, Drains and Nalas (KML) - GHMC via OpenCity
3. Greater Hyderabad Waterbodies (GeoJSON) - TRAC via OpenCity
4. Hyderabad Monthly Rainfall 1901-2021 (CSV) - IMD via OpenCity
5. Telangana Hourly Telemetry Rainfall (CSV) - NWIC / Telangana SW Dept
"""

import os
import sys
import time
import hashlib
import json
import urllib.request

DATA_SOURCES = {
    "flooding_locations_kml": {
        "url": "https://data.opencity.in/dataset/fbc0cf2e-2c10-4d9a-8dfd-0b1c24c6f279/resource/8ab584c9-19ca-4c1b-945f-f19fe1db5de5/download/d6d078ca-7330-4efe-8a5f-0c74cb6a0a70.kml",
        "dest": "data/hyderabad_risk/raw/flooding_locations.kml",
        "publisher": "TRAC Telangana / GHMC via OpenCity",
        "license": "Public Domain / Open Data",
        "description": "Spatial points of recurring inundation hotspots in Hyderabad"
    },
    "hyderabad_drains_kml": {
        "url": "https://data.opencity.in/dataset/4becf994-e7f5-4da3-b201-b56b126b57f7/resource/b3b68ed3-9443-43c4-ad93-638c8dad19b9/download/20dcf709-c38e-4ed1-a4b6-e5887769f992.kml",
        "dest": "data/hyderabad_risk/raw/hyderabad_drains.kml",
        "publisher": "GHMC via OpenCity",
        "license": "Open Data / Public Domain",
        "description": "Network of canals, stormwater drains, and major nalas in GHMC"
    },
    "greater_hyderabad_waterbodies_geojson": {
        "url": "https://data.opencity.in/dataset/c662fa8e-e776-4896-a907-cb4fbad8f89d/resource/6143bd88-8830-49ca-87fd-67ea30abc2da/download/greater_hyderabad_waterbodies.geojson",
        "dest": "data/hyderabad_risk/raw/greater_hyderabad_waterbodies.geojson",
        "publisher": "TRAC Telangana via OpenCity",
        "license": "Open Data / Public Domain",
        "description": "Polygons of lakes, tanks, and water bodies across Greater Hyderabad"
    },
    "hyderabad_monthly_rainfall_csv": {
        "url": "https://data.opencity.in/dataset/fd19c4b3-4cdf-4b74-a48d-738ba01fe68a/resource/10db8dd3-5348-4dbc-ae5a-2920fd1e263e/download/3fef4882-0e8f-4400-a0ec-db7829f05997.csv",
        "dest": "data/hyderabad_risk/raw/hyderabad_monthly_rainfall_1901_2021.csv",
        "publisher": "India Meteorological Department (IMD) via OpenCity",
        "license": "Open Government Data (OGD) India",
        "description": "Historical monthly rainfall records for Hyderabad from 1901 to 2021"
    },
    "telangana_hourly_telemetry_rainfall_csv": {
        "url": "https://nwdp.nwic.gov.in/dataset/c41fc083-97c2-4aa2-b03d-4265bd245113/resource/a6587c58-664a-408e-af7b-d9080dd2f432/download/rainfall_tel_hr_telangana_sw_ts_2021_2025.csv",
        "dest": "data/hyderabad_risk/raw/telangana_hourly_telemetry_rainfall_2021_2025.csv",
        "publisher": "National Water Informatics Centre (NWIC) / Telangana SW Dept",
        "license": "Open Government Data (OGD) India / NWIC Access Terms",
        "description": "Hourly telemetry rainfall records from automated rain gauge stations across Telangana"
    }
}


def download_datasets():
    print("=" * 80)
    print("SAHAAY AI — HYDERABAD RISK DATA ACQUISITION")
    print("=" * 80)

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SahaayAI/1.0"}
    inventory_records = []

    for key, info in DATA_SOURCES.items():
        url = info["url"]
        dest = info["dest"]
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        print(f"\nFetching [{key}]...")
        print(f"  Source URL : {url}")
        print(f"  Destination: {dest}")

        start_time = time.time()
        status_code = None
        error_msg = None
        file_size_kb = 0.0
        md5_hash = ""
        sha256_hash = ""

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                status_code = resp.status
                data = resp.read()
                file_size_kb = len(data) / 1024.0

                md5_hash = hashlib.md5(data).hexdigest()
                sha256_hash = hashlib.sha256(data).hexdigest()

                with open(dest, "wb") as f:
                    f.write(data)

            elapsed = time.time() - start_time
            print(f"  [SUCCESS] Downloaded {file_size_kb:.2f} KB in {elapsed:.2f}s | MD5: {md5_hash[:10]}...")
            download_status = "SUCCESS"

        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = str(e)
            print(f"  [FAILED] {error_msg} (Elapsed: {elapsed:.2f}s)")
            download_status = "FAILED"

        inventory_records.append({
            "dataset_key": key,
            "publisher": info["publisher"],
            "license": info["license"],
            "description": info["description"],
            "source_url": url,
            "destination_path": dest,
            "download_status": download_status,
            "http_status_code": status_code,
            "error_message": error_msg,
            "file_size_kb": round(file_size_kb, 2),
            "md5": md5_hash,
            "sha256": sha256_hash,
            "download_timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

    # Save raw download summary
    summary_path = "reports/risk_ai/phase4_data_acquisition_log.json"
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(inventory_records, f, indent=2)

    print(f"\nAcquisition complete. Manifest logged to: {summary_path}")
    return inventory_records


if __name__ == "__main__":
    download_datasets()
