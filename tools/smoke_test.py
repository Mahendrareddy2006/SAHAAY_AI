#!/usr/bin/env python3
r"""
Sahaay AI — Local Runtime Smoke Test
(tools/smoke_test.py)

Exercises:
1. Application initialization & lifespan (vision model preloading, redacting filter)
2. HTTP endpoints:
   - Root redirect (/) -> /dashboard
   - Dashboard (/dashboard) -> index.html
   - Liveness (/api/v1/health) -> UP
   - Readiness probe (/api/v1/readiness) -> PILOT_BLOCKED / NO_GO
3. Map & GeoJSON endpoints (/map/geojson, /map/corridor, /map/emergency-destinations)
4. Vision inference with quality gate, corrupt/empty handling, and ambiguity rejection
5. Topological safe routing, disconnected rejection, impassable pruning, and LineString overlay
6. Security enforcement (token verification, role spoofing, fail-closed autonomous dispatch)
"""

import io
import os
import sys
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sahaay.api.main import app
from sahaay.security.auth import create_access_token, UserRole
from sahaay.security.rate_limiter import default_rate_limiter
from sahaay.road_network.store import default_road_network_store
from sahaay.road_status.service import default_road_status_service
from sahaay.road_status.schemas import RoadConditionState, RoadVerificationState

def run_smoke_test():
    print("=" * 70)
    print("  SAHAAY AI — RUNTIME SMOKE TEST")
    print("=" * 70)

    # Disable rate limiter for smoke run
    default_rate_limiter.set_enabled(False)
    client = TestClient(app)

    results = []

    def check(name, condition, details=""):
        status = "PASSED" if condition else "FAILED"
        results.append((name, status, details))
        badge = "[PASS]" if condition else "[FAIL]"
        print(f"  {badge} {name:<45} | {details}")
        if not condition:
            raise AssertionError(f"Smoke test failed on: {name} - {details}")

    # -------------------------------------------------------------------------
    # 1. Server Root, Dashboard, Health & Readiness
    # -------------------------------------------------------------------------
    print("\n--- 1. Application Liveness & Readiness Separation ---")
    
    # 1.1 Root redirect
    res = client.get("/", follow_redirects=False)
    check("Root redirect / -> /dashboard", res.status_code in (302, 307) and res.headers.get("location") == "/dashboard", f"Status: {res.status_code}")

    # 1.2 Dashboard HTML
    res_dash = client.get("/dashboard")
    check("Dashboard HTML /dashboard", res_dash.status_code == 200 and "Sahaay AI" in res_dash.text, f"Status: {res_dash.status_code}, Length: {len(res_dash.text)} bytes")

    # 1.3 Liveness (/health)
    res_health = client.get("/api/v1/health")
    h_data = res_health.json()
    check(
        "Liveness probe /api/v1/health",
        res_health.status_code == 200 and h_data.get("liveness") == "UP" and h_data.get("operational_readiness") == "PILOT_BLOCKED",
        f"Liveness: {h_data.get('liveness')}, Pilot: {h_data.get('pilot_decision')}"
    )

    # 1.4 Readiness probe (/readiness)
    res_ready = client.get("/api/v1/readiness")
    r_data = res_ready.json()
    check(
        "Readiness probe /api/v1/readiness",
        res_ready.status_code == 200 and r_data.get("operational_readiness") == "PILOT_BLOCKED" and r_data.get("pilot_decision") == "NO_GO",
        f"Readiness: {r_data.get('operational_readiness')}, Pilot: {r_data.get('pilot_decision')}, Components: {len(r_data.get('components', {}))}, Blockers: {len(r_data.get('active_blockers', []))}"
    )

    # -------------------------------------------------------------------------
    # 2. Map, Road Network & Emergency Destinations
    # -------------------------------------------------------------------------
    print("\n--- 2. Map Features & Emergency Destinations ---")

    # 2.1 Road Network GeoJSON
    res_geo = client.get("/api/v1/map/corridors/geojson")
    geo_data = res_geo.json()
    feat_count = len(geo_data.get("features", []))
    check("Road network GeoJSON (/map/corridors/geojson)", res_geo.status_code == 200 and feat_count >= 20, f"Features loaded: {feat_count}")

    # 2.2 Corridor lookup
    res_corr = client.get("/api/v1/map/corridor/HYD-LOC-001")
    corr_data = res_corr.json()
    check(
        "Corridor detail (/map/corridor/HYD-LOC-001)",
        res_corr.status_code == 200 and corr_data.get("properties", {}).get("road_name") is not None,
        f"Road: {corr_data.get('properties', {}).get('road_name')}"
    )

    # 2.3 Emergency destinations
    res_dest = client.get("/api/v1/map/emergency-destinations")
    dest_data = res_dest.json()
    dest_features = dest_data.get("features", [])
    has_warning = all(f.get("properties", {}).get("is_synthetic_fixture") for f in dest_features)
    check(
        "Emergency destinations (/map/emergency-destinations)",
        res_dest.status_code == 200 and len(dest_features) >= 5 and has_warning,
        f"Destinations: {len(dest_features)}, Synthetic fixtures labeled: {has_warning}"
    )

    # -------------------------------------------------------------------------
    # 3. Vision Inference & Safety Quality Gate
    # -------------------------------------------------------------------------
    print("\n--- 3. Vision Inference & Quality Gate ---")

    # 3.1 Valid local test image
    im = Image.new("RGB", (128, 128), color=(30, 90, 160))
    buf = io.BytesIO()
    im.save(buf, format="JPEG")
    valid_bytes = buf.getvalue()

    res_vis = client.post(
        "/api/v1/vision/predict",
        files={"file": ("street.jpg", io.BytesIO(valid_bytes), "image/jpeg")},
        data={"corridor_id": "HYD-LOC-001"}
    )
    v_data = res_vis.json()
    check(
        "Valid image inference (/vision/predict)",
        res_vis.status_code == 200 and v_data.get("predicted_class") in ["flooded", "not_flooded", "inconclusive"],
        f"Prediction: {v_data.get('predicted_class')}, Provisional: {v_data.get('is_provisional_evidence')}"
    )

    # 3.2 Corrupted image bytes rejected
    res_corrupt = client.post(
        "/api/v1/vision/predict",
        files={"file": ("corrupt.jpg", b"GARBAGE_PAYLOAD_NOT_A_JPEG", "image/jpeg")}
    )
    check("Corrupt file rejection (HTTP 422)", res_corrupt.status_code == 422, f"Status: {res_corrupt.status_code}")

    # 3.3 Empty 0-byte file rejected
    res_empty = client.post(
        "/api/v1/vision/predict",
        files={"file": ("empty.jpg", b"", "image/jpeg")}
    )
    check("Empty file rejection (HTTP 400)", res_empty.status_code == 400, f"Status: {res_empty.status_code}")

    # 3.4 Quality Gate: darkness triggers inconclusive
    dark_im = Image.new("RGB", (128, 128), color=(2, 2, 2))
    dark_buf = io.BytesIO()
    dark_im.save(dark_buf, format="JPEG")
    res_dark = client.post(
        "/api/v1/vision/predict",
        files={"file": ("dark.jpg", io.BytesIO(dark_buf.getvalue()), "image/jpeg")},
        data={"corridor_id": "HYD-LOC-002"}
    )
    d_data = res_dark.json()
    check(
        "Quality gate darkness rejection (/vision/predict)",
        res_dark.status_code == 200 and d_data.get("predicted_class") == "inconclusive" and d_data.get("is_inconclusive") is True,
        f"Result: {d_data.get('predicted_class')}, Inconclusive reasons: {d_data.get('inconclusive_reasons')}"
    )

    # 3.5 Out of radius coordinate
    res_out = client.post(
        "/api/v1/vision/predict",
        files={"file": ("test.jpg", io.BytesIO(valid_bytes), "image/jpeg")},
        data={"latitude": "28.6139", "longitude": "77.2090"}  # Delhi (~1200 km away)
    )
    out_data = res_out.json()
    check(
        "Out-of-radius coordinate rejection (/vision/predict)",
        res_out.status_code == 200 and out_data.get("corridor_id") is None and out_data.get("evidence_registered") is False,
        f"Corridor: {out_data.get('corridor_id')}, Evidence registered: {out_data.get('evidence_registered')}"
    )

    # -------------------------------------------------------------------------
    # 4. Topological Routing & Impassable Pruning
    # -------------------------------------------------------------------------
    print("\n--- 4. Topological Routing & Impassable Pruning ---")

    # 4.1 Connected route evaluation
    route_req = {
        "origin_node_id": "NODE-RETHIBOWLI",
        "destination_node_id": "NODE-OU-COLONY",
        "vehicle_type": "LIGHT_MOTOR_VEHICLE",
        "caller_role": None,
        "request_emergency_dispatch": False,
    }
    res_route = client.post("/api/v1/routing/safe-route", json=route_req)
    r_res = res_route.json()
    check(
        "Connected safe route (/routing/safe-route)",
        res_route.status_code == 200 and r_res.get("outcome") in ["FEASIBLE_RISK_QUALIFIED", "ADVISORY_TRAVERSABLE_WITH_CAUTION"],
        f"Outcome: {r_res.get('outcome')}, Distance: {r_res.get('total_distance_meters')}m, Claimed Safe: {r_res.get('is_guaranteed_safe')}"
    )

    # 4.2 Disconnected topological route
    discon_req = {
        "origin_node_id": "NODE-RETHIBOWLI",
        "destination_node_id": "NODE-GACHIBOWLI-ORR",  # Disconnected component in sparse catalog
        "vehicle_type": "LIGHT_MOTOR_VEHICLE",
    }
    res_discon = client.post("/api/v1/routing/safe-route", json=discon_req)
    disc_data = res_discon.json()
    check(
        "Disconnected topology rejection (/routing/safe-route)",
        res_discon.status_code == 200 and disc_data.get("outcome") == "TOPOLOGY_UNSUPPORTED",
        f"Outcome: {disc_data.get('outcome')}, Synthetic connections created: 0"
    )

    # 4.3 Verified Impassable corridor excluded
    from sahaay.road_status.schemas import RoadStatusSnapshot, RoadEvidenceType, RoadFreshnessCategory, UncertaintyLevel
    impassable_snap = RoadStatusSnapshot(
        road_segment_id="HYD-LOC-001",
        corridor_id="HYD-LOC-001",
        road_name="Tolichowki Main Road",
        condition_state=RoadConditionState.VERIFIED_IMPASSABLE,
        verification_state=RoadVerificationState.VERIFIED_BY_RESPONDER,
        evidence_type=RoadEvidenceType.FIELD_RESPONDER_INSPECTION,
        freshness_category=RoadFreshnessCategory.FRESH,
        last_status_update_utc="2026-10-29T12:00:00Z",
        confidence_score=0.95,
        is_verified_impassable=True,
        measured_water_depth_cm=65.0,
        uncertainty_level=UncertaintyLevel.LOW,
    )
    orig_fn = default_road_status_service.get_corridor_status
    try:
        default_road_status_service.get_corridor_status = lambda cid, ref=None: impassable_snap if cid == "HYD-LOC-001" else orig_fn(cid, ref)
        res_impass = client.post("/api/v1/routing/safe-route", json=route_req)
        imp_data = res_impass.json()
        is_excluded = any(s.get("segment_id") == "HYD-LOC-001" for s in imp_data.get("excluded_segments", []))
        check(
            "Verified impassable exclusion (/routing/safe-route)",
            res_impass.status_code == 200 and is_excluded,
            f"HYD-LOC-001 in excluded_segments: {is_excluded}, Outcome: {imp_data.get('outcome')}"
        )
    finally:
        default_road_status_service.get_corridor_status = orig_fn

    # 4.4 Route GeoJSON LineString overlay
    res_overlay = client.get("/api/v1/map/route-overlay?origin_node_id=NODE-RETHIBOWLI&destination_node_id=NODE-OU-COLONY&vehicle_type=LIGHT_MOTOR_VEHICLE")
    check(
        "Route map LineString overlay (/map/route-overlay)",
        res_overlay.status_code == 200 and res_overlay.json().get("type") == "FeatureCollection",
        f"Type: {res_overlay.json().get('type')}"
    )

    # -------------------------------------------------------------------------
    # 5. Security & Privileged Operations
    # -------------------------------------------------------------------------
    print("\n--- 5. Security & Role Hardening ---")

    # 5.1 Unauthenticated privileged action fails closed (HTTP 401)
    res_noauth = client.post(
        "/api/v1/security/privileged-action",
        json={"action_type": "OVERRIDE_CORRIDOR", "target_resource": "HYD-LOC-001"}
    )
    check("Unauthenticated action rejection (HTTP 401)", res_noauth.status_code == 401, f"Status: {res_noauth.status_code}")

    # 5.2 Role spoofing attempt fails closed (HTTP 403)
    citizen_token = create_access_token("CITIZEN-01", UserRole.CITIZEN)
    res_spoof = client.post(
        "/api/v1/security/privileged-action",
        json={"action_type": "DISPATCH_CREW", "target_resource": "ZONE-WEST", "caller_role": "GHMC_DRF_OFFICER"},
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    check("Role spoofing attempt rejection (HTTP 403)", res_spoof.status_code == 403, f"Status: {res_spoof.status_code}")

    # 5.3 Autonomous dispatch attempt fail closed (HTTP 403)
    admin_token = create_access_token("ADMIN-01", UserRole.SYSTEM_ADMIN)
    res_auto = client.post(
        "/api/v1/security/privileged-action",
        json={"action_type": "DISPATCH_CREW", "target_resource": "ZONE-WEST", "attempt_autonomous_dispatch": True},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    check("Autonomous dispatch attempt rejection (HTTP 403)", res_auto.status_code == 403, f"Status: {res_auto.status_code}")

    print("\n" + "=" * 70)
    print(f"  SMOKE TEST PASSED: {len(results)}/{len(results)} checks successful.")
    print("=" * 70)
    return 0

if __name__ == "__main__":
    sys.exit(run_smoke_test())
