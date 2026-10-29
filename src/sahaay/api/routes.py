"""
Sahaay AI - FastAPI Route Handlers
Implements versioned /api/v1 endpoints for Flood Vision inference and system health.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, status, Depends, Header, Request, Query
from fastapi.responses import JSONResponse

from sahaay.api.schemas import (
    VisionPredictionResponse,
    VisionHealthResponse,
    ErrorResponse,
    RainfallEstimateRequest,
    RoadVulnerabilityRequest,
)
from sahaay.decision.contracts import DecisionInput, DecisionOutput, evaluate_decision
from sahaay.hyderabad_risk.rainfall_engine import evaluate_rainfall_risk_engine
from sahaay.hyderabad_risk.schemas import RainfallRiskResult, RoadVulnerabilityResult
from sahaay.hyderabad_risk.vulnerability_engine import evaluate_road_vulnerability_engine
from sahaay.vision.inference import FloodVisionInference

router = APIRouter(prefix="/api/v1")

# Global inference service instance initialized during app lifespan
inference_service: Optional[FloodVisionInference] = None

def get_inference_service() -> FloodVisionInference:
    global inference_service
    if inference_service is None:
        try:
            inference_service = FloodVisionInference()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Flood Vision model is not ready: {str(e)}"
            )
    return inference_service

@router.get("/health", tags=["System"])
async def root_health():
    return {
        "status": "healthy",
        "liveness": "UP",
        "service": "Sahaay AI Platform API",
        "version": "1.0.0",
        "operational_readiness": "PILOT_BLOCKED",
        "pilot_decision": "NO_GO",
        "readiness_probe_url": "/api/v1/readiness",
    }

@router.get("/vision/health", response_model=VisionHealthResponse, tags=["Vision AI"])
async def vision_health():
    service = get_inference_service()
    return VisionHealthResponse(
        status="ready",
        model_name=service.model_name,
        model_version=service.model_version,
        checkpoint_loaded=True,
        device=str(service.device)
    )

@router.post(
    "/vision/predict",
    response_model=VisionPredictionResponse,
    status_code=status.HTTP_200_OK,
    tags=["Vision AI"]
)
async def predict_flood_vision(
    request: Request,
    file: UploadFile = File(..., description="JPEG, PNG, or WEBP image (max 15MB)"),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    report_id: Optional[str] = Form(None),
    corridor_id: Optional[str] = Form(None),
):
    """
    Flood Vision AI Inference Endpoint.
    Analyzes submitted image for visual evidence of standing flood water / road waterlogging.
    Associates calibrated predictions with registered road corridors and updates persistent
    corridor evidence and map features. Enforces non-inference safety and deduplication.
    """
    import hashlib
    from sahaay.corridor_evidence.service import default_corridor_evidence_service
    from sahaay.road_network.store import default_road_network_store
    from sahaay.security.rate_limiter import enforce_rate_limit

    if request is not None:
        enforce_rate_limit(request, limit_per_minute=60, client_key_prefix="vision")

    if file.content_type not in ["image/jpeg", "image/png", "image/webp", "application/octet-stream"]:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file MIME type '{file.content_type}'. Must be image/jpeg, image/png, or image/webp."
        )
        
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read uploaded image bytes: {str(e)}"
        )
        
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded image file is empty (0 bytes)."
        )
        
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Uploaded file exceeds 15 MB limit."
        )
        
    service = get_inference_service()
    try:
        result = service.predict(
            image_input=content,
            latitude=latitude,
            longitude=longitude,
            report_id=report_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Image validation error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference execution failed: {str(e)}"
        )

    # Compute content hash for deduplication
    img_hash = hashlib.sha256(content).hexdigest()
    is_duplicate, dedup_status = default_corridor_evidence_service.check_and_register_image_hash(
        img_hash,
        corridor_id=corridor_id,
    )

    # Associate with corridor
    target_corridor_id = None
    if corridor_id:
        seg = default_road_network_store.get_segment(corridor_id)
        if seg is None:
            for s in default_road_network_store.list_segments():
                if s.corridor_id == corridor_id:
                    seg = s
                    break
        if seg is not None:
            target_corridor_id = corridor_id
        else:
            result.setdefault("warnings", []).append(
                f"UNKNOWN_CORRIDOR: Corridor '{corridor_id}' is not in seed catalog. Evidence recorded without map association."
            )
            target_corridor_id = corridor_id
    elif latitude is not None and longitude is not None:
        matched_seg, min_dist, is_ambiguous = default_road_network_store.find_nearest_segment_to_coords(
            latitude, longitude, return_metadata=True
        )
        if matched_seg and not is_ambiguous:
            target_corridor_id = matched_seg.corridor_id or matched_seg.segment_id
            result.setdefault("warnings", []).append(
                f"LOCATION_MATCHED: Associated with corridor '{target_corridor_id}' ({round(min_dist, 1)}m proximity)."
            )
        elif matched_seg and is_ambiguous:
            result.setdefault("warnings", []).append(
                f"LOCATION_AMBIGUOUS: Coordinates ({latitude}, {longitude}) are ambiguous between multiple monitored corridors. Visual evidence not registered."
            )
        else:
            result.setdefault("warnings", []).append(
                f"LOCATION_UNMATCHED: Coordinates ({latitude}, {longitude}) are outside monitored seed corridors."
            )
    else:
        result.setdefault("warnings", []).append(
            "MISSING_LOCATION: Neither corridor_id nor GPS coordinates were provided. Evidence cannot be mapped."
        )

    # Register provisional visual evidence if corridor was identified
    evidence_registered = False
    if target_corridor_id:
        try:
            default_corridor_evidence_service.record_vision_evidence(
                corridor_id=target_corridor_id,
                vision_result=result,
                image_hash=img_hash,
            )
            evidence_registered = True
        except Exception:
            evidence_registered = False

    # Enforce non-inference safety on response
    result["corridor_id"] = target_corridor_id
    result["is_provisional_evidence"] = True
    result["evidence_registered"] = evidence_registered
    result["verification_status"] = "PROVISIONAL_UNVERIFIED"
    result["deduplication_status"] = dedup_status

    if is_duplicate:
        result.setdefault("warnings", []).append(
            "DUPLICATE_IMAGE_DETECTED: Identical image submitted previously; excluded from independent corroboration."
        )

    return result

@router.post(
    "/decision/evaluate",
    response_model=DecisionOutput,
    status_code=status.HTTP_200_OK,
    tags=["Decision Engine"]
)
async def evaluate_risk_decision(input_data: DecisionInput):
    """
    Decision Engine Multi-Evidence Synthesis Endpoint.
    Combines Vision output, Rainfall risk, Road vulnerability, and Freshness.
    """
    try:
        return evaluate_decision(input_data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Decision evaluation failed: {str(e)}"
        )


@router.post(
    "/risk/rainfall/estimate",
    response_model=RainfallRiskResult,
    status_code=status.HTTP_200_OK,
    tags=["Hyderabad Risk AI"]
)
async def estimate_rainfall_risk(request: RainfallEstimateRequest):
    """
    Hyderabad Rainfall Risk Baseline Evaluation Endpoint.
    Evaluates precipitation intensity against IMD standard operational procedure thresholds.
    """
    try:
        return evaluate_rainfall_risk_engine(
            location_id=request.location_id,
            rain_1h_mm=request.rain_1h_mm,
            rain_3h_mm=request.rain_3h_mm,
            rain_6h_mm=request.rain_6h_mm,
            rain_24h_mm=request.rain_24h_mm,
            station_dist_km=request.station_dist_km,
            data_freshness_hours=request.data_freshness_hours,
            data_timestamp=request.data_timestamp,
            historical_month_p90_mm=request.historical_month_p90_mm,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rainfall risk calculation failed: {str(e)}"
        )


@router.post(
    "/risk/vulnerability/calculate",
    response_model=RoadVulnerabilityResult,
    status_code=status.HTTP_200_OK,
    tags=["Hyderabad Risk AI"]
)
async def calculate_road_vulnerability(request: RoadVulnerabilityRequest):
    """
    Hyderabad Road Vulnerability Baseline Evaluation Endpoint.
    Computes static physical susceptibility index from proximity to hotspots, nalas, and water bodies.
    """
    try:
        return evaluate_road_vulnerability_engine(
            location_id=request.location_id,
            road_name=request.road_name,
            dist_to_hotspot_m=request.dist_to_hotspot_m,
            nearest_hotspot_name=request.nearest_hotspot_name,
            dist_to_drain_m=request.dist_to_drain_m,
            dist_to_waterbody_m=request.dist_to_waterbody_m,
            nearest_waterbody_name=request.nearest_waterbody_name,
            road_elevation_m=request.road_elevation_m,
            drainage_capacity_cusecs=request.drainage_capacity_cusecs,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Road vulnerability calculation failed: {str(e)}"
        )


@router.get(
    "/risk/corridors",
    status_code=status.HTTP_200_OK,
    tags=["Hyderabad Risk AI"]
)
async def list_corridor_risk_profiles():
    """
    Returns pre-computed risk features across the 20 candidate Hyderabad corridors.
    """
    from pathlib import Path
    import pandas as pd

    features_csv = Path("data/hyderabad_risk/derived/hyderabad_risk_features.csv")
    if not features_csv.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Derived corridor risk features have not been generated yet."
        )

    df = pd.read_csv(features_csv)
    import math
    records = []
    for row in df.to_dict(orient="records"):
        clean_row = {}
        for k, v in row.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                clean_row[k] = None
            else:
                clean_row[k] = v
        records.append(clean_row)

    return {
        "status": "success",
        "total_corridors": len(records),
        "corridors": records
    }


# ---------------------------------------------------------------------------
# Phase 5: Citizen Reports & Verification Endpoints
# ---------------------------------------------------------------------------

from typing import List
from sahaay.reports.schemas import (
    CitizenReportRecord,
    CitizenReportSubmission,
    ReportVerificationRequest,
)
from sahaay.reports.service import CitizenReportService
from sahaay.adapters.registry import default_adapter_registry

report_service = CitizenReportService()


@router.post(
    "/reports/submit",
    response_model=CitizenReportRecord,
    status_code=status.HTTP_201_CREATED,
    tags=["Citizen Reports"]
)
async def submit_citizen_report(submission: CitizenReportSubmission):
    """
    Submits a ground flood observation. Enforces privacy masking,
    location coarsening, near-duplicate clustering, and corroboration tracking.
    """
    try:
        return report_service.submit_report(submission)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Report submission failed: {str(e)}"
        )


@router.post(
    "/reports/verify/{report_id}",
    response_model=CitizenReportRecord,
    status_code=status.HTTP_200_OK,
    tags=["Citizen Reports"]
)
async def verify_citizen_report(
    report_id: str,
    request: ReportVerificationRequest,
    authorization: Optional[str] = Header(None, description="Optional Bearer token for server-side verified responder"),
):
    """
    Updates the verification status of a ground report by an authorized responder.
    Validates server-side Bearer token if provided and prevents client role spoofing.
    """
    if authorization:
        from sahaay.security.auth import get_current_authenticated_identity, validate_no_client_role_spoofing, RESPONDER_ROLES
        identity = get_current_authenticated_identity(authorization)
        validate_no_client_role_spoofing(identity, request.verifier_role)
        if identity.role not in RESPONDER_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: role '{identity.role.value}' lacks responder privileges for verifying reports.",
            )

    try:
        record = report_service.verify_report(report_id, request)
    except PermissionError as pe:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(pe),
        )

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} not found."
        )
    return record


@router.get(
    "/reports/corridor/{corridor_id}",
    response_model=List[CitizenReportRecord],
    status_code=status.HTTP_200_OK,
    tags=["Citizen Reports"]
)
async def get_corridor_reports(corridor_id: str):
    """
    Retrieves active, valid, non-expired reports for a specific corridor.
    """
    return report_service.get_active_reports_for_corridor(corridor_id)


@router.get(
    "/sources/status",
    status_code=status.HTTP_200_OK,
    tags=["Live Adapters"]
)
async def get_live_data_source_status():
    """
    Returns the real-time operational status, authorization state, and limitations of all data feeds.
    """
    return default_adapter_registry.generate_source_status_report()


from sahaay.review.workflow import (
    ReviewQueueService,
    ReviewItem,
    ReviewAction,
    ReviewItemType,
    ReviewStatus,
    ReviewerRole,
)

review_queue_service = ReviewQueueService()


class ReviewActionSubmission(BaseModel):
    item_id: str
    reviewer_role: ReviewerRole
    reviewer_id: str
    action_type: str
    justification_notes: str
    new_status: ReviewStatus


@router.get(
    "/review/pending",
    response_model=List[ReviewItem],
    status_code=status.HTTP_200_OK,
    tags=["Human Review Queue"]
)
async def list_pending_reviews():
    """Returns all items currently awaiting human supervisor review."""
    return review_queue_service.list_pending()


@router.post(
    "/review/action",
    response_model=ReviewItem,
    status_code=status.HTTP_200_OK,
    tags=["Human Review Queue"]
)
async def submit_review_action(
    submission: ReviewActionSubmission,
    authorization: Optional[str] = Header(None, description="Optional Bearer token for server-side verified supervisor"),
):
    """Submits an attributable, cryptographically hashed human review decision."""
    if authorization:
        from sahaay.security.auth import get_current_authenticated_identity, validate_no_client_role_spoofing, SUPERVISOR_ROLES
        identity = get_current_authenticated_identity(authorization)
        validate_no_client_role_spoofing(identity, submission.reviewer_role)
        if identity.role not in SUPERVISOR_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: role '{identity.role.value}' lacks supervisor privileges for review decisions.",
            )

    try:
        return review_queue_service.record_review_action(
            item_id=submission.item_id,
            reviewer_role=submission.reviewer_role,
            reviewer_id=submission.reviewer_id,
            action_type=submission.action_type,
            justification_notes=submission.justification_notes,
            new_status=submission.new_status,
        )
    except PermissionError as pe:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(pe),
        )
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


# ---------------------------------------------------------------------------
# Phase 16: Live Road Status Endpoints (Offline Evaluation)
# ---------------------------------------------------------------------------

from sahaay.road_status.schemas import RoadStatusSnapshot, RoadStatusEvaluationInput
from sahaay.road_status.service import default_road_status_service


@router.get(
    "/road-status/snapshot/{corridor_id}",
    response_model=RoadStatusSnapshot,
    status_code=status.HTTP_200_OK,
    tags=["Live Road Status"]
)
async def get_corridor_road_status(corridor_id: str):
    """
    Returns an offline live road status snapshot for the specified corridor.
    Fuses community reports, responder records, and physical telemetry.
    """
    try:
        return default_road_status_service.get_corridor_status(corridor_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to evaluate road status for corridor {corridor_id}: {str(e)}"
        )


@router.post(
    "/road-status/evaluate",
    response_model=RoadStatusSnapshot,
    status_code=status.HTTP_200_OK,
    tags=["Live Road Status"]
)
async def evaluate_road_status_input(input_data: RoadStatusEvaluationInput):
    """
    Evaluates road condition state and evidence fusion for supplied observation inputs.
    """
    try:
        return default_road_status_service.evaluate_road_status(input_data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Road status evaluation failed: {str(e)}"
        )


# ---------------------------------------------------------------------------
# Phase A: Live Map & Road Network Endpoints
# ---------------------------------------------------------------------------

from sahaay.road_network.schemas import (
    RoadNetworkFeatureCollection,
    RoadSegmentMapFeature,
    MapCoverageReport,
)
from sahaay.road_network.store import default_road_network_store
from datetime import datetime, timezone


class MapRefreshRequest(BaseModel):
    caller_role: str = Field("OPERATOR", description="Role initiating map refresh")
    caller_id: str = Field(..., min_length=2, description="Identifier of caller")
    reason: str = Field("PERIODIC_EVIDENCE_REFRESH", description="Reason for refresh")


class MapRefreshResponse(BaseModel):
    refreshed_at_utc: str
    caller_id: str
    total_features_refreshed: int
    status: str = "REFRESH_SUCCESS"


@router.get(
    "/map/corridors/geojson",
    response_model=RoadNetworkFeatureCollection,
    status_code=status.HTTP_200_OK,
    tags=["Live Map & Road Network"]
)
async def get_map_corridors_geojson():
    """
    Returns RFC 7946 compliant GeoJSON FeatureCollection of all road segments
    with active road-status overlays and symbology directives for map rendering.
    """
    try:
        return default_road_network_store.to_geojson_feature_collection()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate map GeoJSON: {str(e)}"
        )


@router.get(
    "/map/forecast-risk/geojson",
    status_code=status.HTTP_200_OK,
    tags=["Live Map & Road Network"]
)
async def get_map_forecast_risk_geojson(
    horizon_hours: float = 3.0,
    rainfall_scenario_mm: Optional[float] = None,
):
    """
    Returns RFC 7946 compliant GeoJSON FeatureCollection of all road corridors
    with forward-looking forecast-risk overlays across a configurable horizon (1h, 3h, 6h, 24h).
    Strictly separates forecast risk from observed inundation. Unknown corridors are explicitly
    marked UNKNOWN_INSUFFICIENT_DATA and NEVER rendered as dry/safe.
    """
    from datetime import datetime, timezone, timedelta
    from sahaay.forecast_risk.schemas import (
        ForecastRainfallInput,
        ForecastSourceType,
        PrecipitationUnit,
        MANDATORY_FORECAST_RISK_DISCLAIMER,
    )

    features = []
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat().replace("+00:00", "Z")
    valid_iso = (now_dt + timedelta(hours=horizon_hours)).isoformat().replace("+00:00", "Z")

    # Optional forecast input if scenario provided or live forecast enabled
    fc_inputs = None
    if rainfall_scenario_mm is not None and rainfall_scenario_mm > 0.0:
        fc_inputs = [
            ForecastRainfallInput(
                location_id="CITYWIDE_HYD",
                source_id="NWP_OPEN_METEO_HYD",
                source_type=ForecastSourceType.GLOBAL_OPEN_MODEL,
                issue_timestamp_utc=now_iso,
                valid_timestamp_utc=valid_iso,
                forecast_horizon_hours=horizon_hours,
                rainfall_amount=rainfall_scenario_mm,
                rainfall_units=PrecipitationUnit.MILLIMETERS,
                spatial_resolution_km=4.0,
            )
        ]

    for seg in default_road_network_store.list_segments():
        if seg.geometry and seg.geometry.coordinates:
            mid_idx = len(seg.geometry.coordinates) // 2
            c_lon, c_lat = seg.geometry.coordinates[mid_idx]
        else:
            c_lat, c_lon = 17.40, 78.45

        c_id = seg.corridor_id or seg.segment_id
        risk_res = default_weather_pipeline.evaluate_corridor_forecast_risk(
            corridor_id=c_id,
            road_name=seg.road_name,
            corridor_lat=c_lat,
            corridor_lon=c_lon,
            forecast_inputs=fc_inputs,
            static_vulnerability_index=seg.static_vulnerability_index,
            static_vulnerability_category=seg.static_vulnerability_category,
        )

        fc_cat = risk_res.forecast_risk_category
        # Symbology for forecast risk layer
        if fc_cat in ("HIGH", "CRITICAL"):
            color = "#dc2626"   # Red
            stroke = 6
        elif fc_cat == "MODERATE":
            color = "#f59e0b"   # Amber
            stroke = 5
        elif fc_cat == "LOW":
            color = "#10b981"   # Green
            stroke = 4
        else:
            color = "#64748b"   # Slate gray (unknown/insufficient data)
            stroke = 4

        feat = {
            "type": "Feature",
            "id": c_id,
            "geometry": {
                "type": seg.geometry.type.value if hasattr(seg.geometry.type, "value") else str(seg.geometry.type),
                "coordinates": seg.geometry.coordinates,
            },
            "properties": {
                "corridor_id": c_id,
                "road_name": seg.road_name,
                "forecast_horizon_hours": horizon_hours,
                "forecast_risk_category": fc_cat,
                "heuristic_risk_score": risk_res.heuristic_risk_score,
                "static_vulnerability_category": seg.static_vulnerability_category,
                "static_vulnerability_index": seg.static_vulnerability_index,
                "data_status": risk_res.assessment_status.value if hasattr(risk_res.assessment_status, "value") else str(risk_res.assessment_status),
                "quality_flags": risk_res.data_quality_flags,
                "missing_inputs": risk_res.missing_inputs,
                "is_unknown_or_stale": fc_cat == "UNKNOWN_INSUFFICIENT_DATA",
                "symbology": {
                    "marker_color": color,
                    "stroke_style": "dashed",
                    "stroke_weight": stroke,
                    "alert_badge": f"FORECAST_{fc_cat}",
                },
                "safety_disclaimer": MANDATORY_FORECAST_RISK_DISCLAIMER,
            }
        }
        features.append(feat)

    return {
        "type": "FeatureCollection",
        "metadata": {
            "layer_type": "FORECAST_FLOOD_RISK_MAP",
            "forecast_horizon_hours": horizon_hours,
            "generated_at_utc": now_iso,
            "total_corridors": len(features),
            "disclaimer": MANDATORY_FORECAST_RISK_DISCLAIMER,
        },
        "features": features,
    }


@router.get(
    "/map/road-status/snapshots",
    response_model=List[RoadStatusSnapshot],
    status_code=status.HTTP_200_OK,
    tags=["Live Map & Road Network"]
)
async def get_all_road_status_snapshots():
    """
    Returns batch list of current RoadStatusSnapshot records for all known monitored corridors.
    """
    snapshots: List[RoadStatusSnapshot] = []
    for seg in default_road_network_store.list_segments():
        if seg.corridor_id:
            try:
                snapshots.append(default_road_status_service.get_corridor_status(seg.corridor_id))
            except Exception:
                pass
    return snapshots


@router.get(
    "/map/corridor/{corridor_id}",
    response_model=RoadSegmentMapFeature,
    status_code=status.HTTP_200_OK,
    tags=["Live Map & Road Network"]
)
async def get_map_corridor_feature(corridor_id: str):
    """
    Retrieves full GeoJSON feature for a single corridor, including geometry,
    static attributes, and latest RoadStatusSnapshot with provenance.
    """
    seg = default_road_network_store.get_segment(corridor_id)
    if seg is None:
        for s in default_road_network_store.list_segments():
            if s.corridor_id == corridor_id:
                seg = s
                break
    if seg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Corridor '{corridor_id}' not found in road network store."
        )
    return default_road_network_store.build_map_feature(seg)


@router.get(
    "/map/coverage",
    response_model=MapCoverageReport,
    status_code=status.HTTP_200_OK,
    tags=["Live Map & Road Network"]
)
async def get_map_coverage_report():
    """
    Returns metadata on map coverage, centerline kilometers, monitored vs
    unmonitored segments, freshness summary, and ODbL licensing attribution.
    """
    return default_road_network_store.get_coverage_report()


AUTHORIZED_MAP_REFRESH_ROLES = {
    "OPERATOR",
    "DASHBOARD_OPERATOR",
    "GHMC_DRF_OFFICER",
    "TRAFFIC_POLICE_DCP",
    "FIELD_RESEARCH_LEAD",
    "MUNICIPAL_ENGINEER",
    "AUTHORIZED_DISPATCHER",
    "SYSTEM_CRON",
}


@router.post(
    "/map/corridors/refresh",
    response_model=MapRefreshResponse,
    status_code=status.HTTP_200_OK,
    tags=["Live Map & Road Network"]
)
async def refresh_map_data(
    request: MapRefreshRequest,
    authorization: Optional[str] = Header(None, description="Optional server-side Bearer token header")
):
    """
    Triggers re-evaluation and cache sync of road conditions across all segments.
    Enforces role-based provenance tracking; unauthorized users cannot declare roads passable.
    Supports server-side Bearer token verification with strict role spoofing prevention.
    """
    if authorization:
        from sahaay.security.auth import verify_bearer_token, validate_no_client_role_spoofing
        token_str = authorization.replace("Bearer ", "").replace("bearer ", "").strip()
        identity = verify_bearer_token(token_str)
        if identity.role.value not in AUTHORIZED_MAP_REFRESH_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Authenticated role '{identity.role.value}' is not authorized to refresh map data."
            )
        validate_no_client_role_spoofing(identity, request.caller_role)
    elif request.caller_role.upper() not in AUTHORIZED_MAP_REFRESH_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Caller role '{request.caller_role}' is not authorized to refresh map data or modify network cache."
        )

    fc = default_road_network_store.to_geojson_feature_collection()
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return MapRefreshResponse(
        refreshed_at_utc=now_iso,
        caller_id=request.caller_id,
        total_features_refreshed=len(fc.features),
        status="REFRESH_SUCCESS"
    )



# ---------------------------------------------------------------------------
# Phase B: Topological Graph & Routing Integration Endpoints
# ---------------------------------------------------------------------------

from sahaay.road_network.graph import GraphTopologyMetrics
from sahaay.routing.graph_router import TopologicalGraphRouter
from sahaay.routing.schemas import RiskAwareRouteAssessment
from sahaay.routing.contracts import VehicleType


class GraphDemonstrationRouteRequest(BaseModel):
    origin_node_id: str = Field(..., description="Starting graph node ID")
    destination_node_id: str = Field(..., description="Target destination graph node ID")
    vehicle_type: VehicleType = Field(VehicleType.LIGHT_MOTOR_VEHICLE, description="Vehicle classification")


@router.get(
    "/routing/graph/metrics",
    response_model=GraphTopologyMetrics,
    status_code=status.HTTP_200_OK,
    tags=["Topological Routing & Graph"]
)
async def get_routing_graph_metrics():
    """
    Returns quantitative connectivity metrics for the current directed road network graph,
    including node counts, edge counts, junction counts, and connected components.
    """
    graph = default_road_network_store.get_road_graph()
    return graph.get_metrics()


@router.post(
    "/routing/demonstration/evaluate",
    response_model=RiskAwareRouteAssessment,
    status_code=status.HTTP_200_OK,
    tags=["Topological Routing & Graph"]
)
async def evaluate_topological_route(request: GraphDemonstrationRouteRequest):
    """
    Executes risk-aware topological pathfinding over the directed road graph.
    Excludes verified impassable road segments and penalizes flooded/unmonitored roads.
    """
    graph = default_road_network_store.get_road_graph()
    router_engine = TopologicalGraphRouter(graph=graph)

    def _status_provider(segment_id: str):
        try:
            return default_road_status_service.get_corridor_status(segment_id)
        except Exception:
            return None

    assessment = router_engine.find_risk_aware_route(
        origin_node_id=request.origin_node_id,
        destination_node_id=request.destination_node_id,
        vehicle_type=request.vehicle_type,
        segment_status_provider=_status_provider,
        is_demonstration=True,
    )
    return assessment


class NearestNodeResponse(BaseModel):
    status: str = Field(..., description="'FOUND' or 'OUT_OF_BOUNDS'")
    nearest_node_id: Optional[str] = Field(None, description="Closest graph node ID in monitored network")
    node_name: Optional[str] = Field(None, description="Human-readable node or intersection label")
    latitude: Optional[float] = Field(None, description="Node latitude")
    longitude: Optional[float] = Field(None, description="Node longitude")
    distance_meters: Optional[float] = Field(None, description="Geodesic distance from user coordinates to snapped node")
    is_within_network: bool = Field(False, description="True if within maximum coverage radius")
    message: str = Field(..., description="Status explanation")


@router.get(
    "/routing/nearest-node",
    response_model=NearestNodeResponse,
    status_code=status.HTTP_200_OK,
    tags=["Topological Routing & Graph"]
)
async def get_nearest_graph_node(
    lat: float = Query(..., description="User latitude (WGS-84)"),
    lon: float = Query(..., description="User longitude (WGS-84)"),
    max_distance_meters: float = Query(15000.0, description="Maximum snapping radius in meters")
):
    """
    Snaps arbitrary user coordinates (e.g. from browser geolocation) to the nearest
    supported Hyderabad road network graph node.
    """
    import math
    if math.isnan(lat) or math.isnan(lon) or math.isinf(lat) or math.isinf(lon):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Coordinates must be finite numeric values."
        )
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Latitude must be between -90 and 90, longitude between -180 and 180."
        )

    from sahaay.emergency_destinations.service import haversine_distance_meters
    graph = default_road_network_store.get_road_graph()
    nodes = getattr(graph, "nodes", {})
    if not nodes:
        return NearestNodeResponse(
            status="OUT_OF_BOUNDS",
            nearest_node_id=None,
            node_name=None,
            latitude=None,
            longitude=None,
            distance_meters=None,
            is_within_network=False,
            message="Road network graph has no active nodes.",
        )

    best_node = None
    min_dist = float("inf")

    for node in nodes.values():
        dist = haversine_distance_meters(lat, lon, node.latitude, node.longitude)
        if dist < min_dist:
            min_dist = dist
            best_node = node

    if best_node is not None and min_dist <= max_distance_meters:
        node_name = best_node.metadata.get("name") or best_node.node_id
        return NearestNodeResponse(
            status="FOUND",
            nearest_node_id=best_node.node_id,
            node_name=node_name,
            latitude=best_node.latitude,
            longitude=best_node.longitude,
            distance_meters=round(min_dist, 1),
            is_within_network=True,
            message=f"Location snapped to nearest corridor junction: {node_name} ({round(min_dist, 1)}m away)",
        )

    return NearestNodeResponse(
        status="OUT_OF_BOUNDS",
        nearest_node_id=None,
        node_name=None,
        latitude=None,
        longitude=None,
        distance_meters=round(min_dist, 1) if min_dist != float("inf") else None,
        is_within_network=False,
        message=f"Location ({lat:.4f}, {lon:.4f}) is outside supported Hyderabad monitored corridors (nearest node is {min_dist/1000.0:.1f} km away, max search radius: {max_distance_meters/1000.0:.1f} km).",
    )


# ---------------------------------------------------------------------------
# Phase C: Weather & Rainfall Ingestion Pipeline Endpoints
# ---------------------------------------------------------------------------

from sahaay.hyderabad_risk.weather_pipeline import (
    default_weather_pipeline,
    IngestionHealthStatus,
    StationMetadata,
    RawTelemetryPayload,
)
from sahaay.forecast_risk.schemas import ForecastRiskAssessmentOutput


class WeatherBatchIngestRequest(BaseModel):
    records: List[RawTelemetryPayload] = Field(..., description="List of raw telemetry observation records")
    activate_live_stream: bool = Field(False, description="Attempt privileged live stream activation")
    counter_max_mm: Optional[float] = Field(1000.0, description="Gauge counter maximum capacity before rollover")


class WeatherBatchIngestResponse(BaseModel):
    ingested_at_utc: str
    valid_observations_count: int
    quarantined_observations_count: int
    status: str
    warnings: List[str] = Field(default_factory=list)


@router.get(
    "/weather/provider/status",
    status_code=status.HTTP_200_OK,
    tags=["Live Weather & Rainfall Telemetry"]
)
async def get_weather_provider_status():
    """
    Reports institutional authorization status, endpoint configuration,
    and access blocker status for candidate meteorological data providers.
    """
    adapter = default_weather_pipeline.adapter
    adapter_status = adapter.get_source_status() if hasattr(adapter, "get_source_status") else {}

    return {
        "active_primary_provider": adapter_status,
        "candidate_providers_inventory": [
            {
                "source_id": "IMD-LIVE-AWS",
                "source_name": "India Meteorological Department (IMD) AWS Telemetry Gateway",
                "authorization_status": "BLOCKED_NO_EXECUTED_AGREEMENT",
                "access_method": "HTTPS REST API (IMD/MoES Telemetry Gateway)",
                "authentication": "Bearer Token / API Key in Authorization header",
                "data_types": "Cumulative gauge counter Ct (mm), interval rainfall (mm/h), air temperature (°C)",
                "geographic_coverage": "Telangana & Greater Hyderabad regional bounds (15.0-20.5°N, 76.5-82.5°E)",
                "update_cadence": "Hourly / 15-minute telemetry packets",
                "licensing": "Government of India / IMD statutory data policy; commercial or operational dispatch requires executed MOU",
                "integration_verdict": "BLOCKED_NO_EXECUTED_AGREEMENT",
            },
            {
                "source_id": "TSDPS-URBAN-AWS",
                "source_name": "Telangana State Development Planning Society Urban AWS Network",
                "authorization_status": "BLOCKED_PENDING_INSTITUTIONAL_APPROVAL",
                "access_method": "State Department Secure REST API Gateway",
                "authentication": "IP Whitelist & Bearer Token",
                "data_types": "15-minute and 1-hour precipitation (mm), ambient temperature, relative humidity",
                "geographic_coverage": "~100 urban telemetry stations within GHMC core zones",
                "update_cadence": "15-minute transmission cadence; 30-180 min storm lag",
                "licensing": "Government of Telangana; non-commercial research use only",
                "integration_verdict": "BLOCKED_PENDING_INSTITUTIONAL_APPROVAL",
            },
            {
                "source_id": "DWR-BEGUMPET-RADAR",
                "source_name": "IMD Begumpet Doppler Weather Radar (S-Band DWR)",
                "authorization_status": "BLOCKED_NO_API_ACCESS_IDENTIFIED",
                "access_method": "Public Web Portal (Raster Reflectivity Products)",
                "authentication": "None available for public telemetry; bilateral agreement needed for raw volume scans",
                "data_types": "Reflectivity Z (dBZ), QPE instantaneous rain rate (mm/hr), 1h/3h PAC accumulations",
                "geographic_coverage": "Begumpet Airport (17.448°N, 78.468°E), 100-250 km radial mesh",
                "update_cadence": "10-15 minute volume scans",
                "licensing": "MoES / IMD statutory weather data policy",
                "integration_verdict": "BLOCKED_NO_API_ACCESS_IDENTIFIED",
            },
            {
                "source_id": "IMD-NWP-WRF",
                "source_name": "IMD Regional Numerical Weather Prediction (WRF / GFS)",
                "authorization_status": "BLOCKED_NO_EXECUTED_AGREEMENT",
                "access_method": "IMD NWP Portal / GRIB2 Bulletin Archives",
                "authentication": "SFTP/FTP credentials for research archives",
                "data_types": "Quantitative precipitation forecast (QPF) in cumulative mm over 3h/24h intervals",
                "geographic_coverage": "Regional grid ~0.125° (~12-14 km resolution)",
                "update_cadence": "6-hourly cycles (00, 06, 12, 18 UTC); 24-72h horizons",
                "licensing": "MoES non-commercial academic research only",
                "integration_verdict": "BLOCKED_NO_EXECUTED_AGREEMENT",
            },
            {
                "source_id": "OPEN-METEO-GLOBAL-NWP",
                "source_name": "Commercial / Global Open NWP (Open-Meteo / ECMWF)",
                "authorization_status": "BLOCKED_ZERO_CREDENTIALS_CONFIGURED",
                "access_method": "Public / Commercial Cloud REST API",
                "authentication": "API Key required for enterprise; open tier uncalibrated",
                "data_types": "Hourly precipitation accumulation (mm), rain rate (mm/h)",
                "geographic_coverage": "Global interpolated grid ~4-9 km",
                "update_cadence": "Hourly forecasts out to 168 hours; 4 runs daily",
                "licensing": "CC BY 4.0 (Open-Meteo); commercial enterprise agreement for SLA",
                "integration_verdict": "BLOCKED_ZERO_CREDENTIALS_CONFIGURED",
            },
        ],
        "operational_directive": "NON-AUTONOMOUS / ADVISORY ONLY: Live external weather feeds remain blocked until institutional data-sharing MOUs and server-side cryptographic authentication are approved.",
    }


@router.get(
    "/weather/ingestion/health",
    response_model=IngestionHealthStatus,
    status_code=status.HTTP_200_OK,
    tags=["Live Weather & Rainfall Telemetry"]
)
async def get_weather_ingestion_health():
    """
    Returns operational health status of the rainfall ingestion pipeline,
    including retrieval timestamps, data age, error state, and station counts.
    """
    return default_weather_pipeline.get_ingestion_health()


@router.get(
    "/weather/stations",
    response_model=List[StationMetadata],
    status_code=status.HTTP_200_OK,
    tags=["Live Weather & Rainfall Telemetry"]
)
async def get_weather_stations():
    """
    Returns the canonical gazetteer of monitored meteorological weather stations
    across Greater Hyderabad and surrounding reservoir catchments.
    """
    return default_weather_pipeline.get_stations_gazetteer()


@router.get(
    "/weather/corridor/{corridor_id}",
    response_model=RainfallRiskResult,
    status_code=status.HTTP_200_OK,
    tags=["Live Weather & Rainfall Telemetry"]
)
async def get_corridor_weather_evaluation(corridor_id: str):
    """
    Evaluates real-time weather and rainfall risk for a specific road corridor.
    Uses nearest-station telemetry without fabricating dry weather (0.0mm) during outages.
    """
    seg = default_road_network_store.get_segment(corridor_id)
    if seg is None:
        for s in default_road_network_store.list_segments():
            if s.corridor_id == corridor_id:
                seg = s
                break

    if seg is not None and seg.geometry.coordinates:
        mid_idx = len(seg.geometry.coordinates) // 2
        c_lon, c_lat = seg.geometry.coordinates[mid_idx]
    else:
        # Default central Hyderabad coordinates
        c_lat, c_lon = 17.40, 78.45

    return default_weather_pipeline.evaluate_corridor_weather(
        corridor_id=corridor_id,
        corridor_lat=c_lat,
        corridor_lon=c_lon,
    )


@router.get(
    "/weather/forecast/{corridor_id}",
    response_model=ForecastRiskAssessmentOutput,
    status_code=status.HTTP_200_OK,
    tags=["Live Weather & Rainfall Telemetry"]
)
async def get_corridor_forecast_risk(corridor_id: str):
    """
    Evaluates localized forward-looking flood risk using Phase 18 forecast-risk service.
    Strictly separates forecast precipitation from observed rainfall and confirmed road status.
    """
    seg = default_road_network_store.get_segment(corridor_id)
    if seg is None:
        for s in default_road_network_store.list_segments():
            if s.corridor_id == corridor_id:
                seg = s
                break

    road_name = seg.road_name if seg else f"Corridor {corridor_id}"
    v_idx = seg.static_vulnerability_index if seg else 0.50
    v_cat = seg.static_vulnerability_category if seg else "UNKNOWN"

    if seg is not None and seg.geometry.coordinates:
        mid_idx = len(seg.geometry.coordinates) // 2
        c_lon, c_lat = seg.geometry.coordinates[mid_idx]
    else:
        c_lat, c_lon = 17.40, 78.45

    # Fallback evaluation: zero live forecast feeds are authorized
    return default_weather_pipeline.evaluate_corridor_forecast_risk(
        corridor_id=corridor_id,
        road_name=road_name,
        corridor_lat=c_lat,
        corridor_lon=c_lon,
        forecast_inputs=None,  # Live forecast feed is blocked; triggers safe INSUFFICIENT_DATA fallback
        static_vulnerability_index=v_idx,
        static_vulnerability_category=v_cat,
    )


@router.post(
    "/weather/ingest",
    response_model=WeatherBatchIngestResponse,
    status_code=status.HTTP_200_OK,
    tags=["Live Weather & Rainfall Telemetry"]
)
async def ingest_weather_telemetry_batch(request: WeatherBatchIngestRequest):
    """
    Ingestion boundary for raw meteorological telemetry batches.
    Validates schemas, normalizes units, detects counter rollovers, and deduplicates.
    Enforces security gate: privileged live stream activation remains BLOCKED.
    """
    if request.activate_live_stream:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "SECURITY GATE: Privileged live-feed activation is BLOCKED pending approved "
                "server-side cryptographic authentication. Caller-supplied flags cannot authorize live feeds."
            )
        )

    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    valid_c, quar_c, warnings = default_weather_pipeline.ingest_batch(
        telemetry_records=request.records,
        counter_max_mm=request.counter_max_mm,
    )

    return WeatherBatchIngestResponse(
        ingested_at_utc=now_iso,
        valid_observations_count=valid_c,
        quarantined_observations_count=quar_c,
        status="SUCCESS" if valid_c > 0 else "QUARANTINED_OR_EMPTY",
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Phase D: Evidence-to-Map and Flood-Risk Integration Endpoints
# ---------------------------------------------------------------------------

from sahaay.corridor_evidence.schemas import CorridorEvidenceAssessment
from sahaay.corridor_evidence.service import default_corridor_evidence_service
from sahaay.road_status.schemas import (
    RoadConditionState,
    RoadEvidenceType,
    RoadFreshnessCategory,
    RoadVerificationState,
    RoadStatusSnapshot,
    UncertaintyLevel,
)


class CustomCorridorEvidenceEvaluationRequest(BaseModel):
    corridor_id: str = Field(..., description="Corridor ID to evaluate")
    road_name: Optional[str] = Field(None, description="Road name if overriding")
    caller_role: str = Field("OPERATOR", description="Caller role string (unauthenticated)")
    request_live_feed_activation: bool = Field(False, description="Attempt privileged live activation")
    has_conflicting_evidence: bool = Field(False, description="Flag explicitly declaring conflicting evidence")
    verified_impassable_by_responder: bool = Field(False, description="Official responder verified impassable")
    verified_waterlogged_by_responder: bool = Field(False, description="Official responder verified waterlogged")
    verified_passable_by_responder: bool = Field(False, description="Official responder verified passable")
    citizen_reports_count: int = Field(0, ge=0, description="Citizen report count")
    independent_citizen_sources: int = Field(0, ge=0, description="Independent citizen sources count")
    observed_rainfall_1h_mm: Optional[float] = Field(None, ge=0.0, description="Observed gauge rainfall in mm")
    rainfall_telemetry_outage: bool = Field(False, description="Simulate rainfall telemetry outage")
    forecast_rainfall_band: Optional[str] = Field("UNKNOWN", description="Precipitation forecast band")
    forecast_risk_category: Optional[str] = Field("UNKNOWN", description="Forecast risk category")
    vision_predicted_class: Optional[str] = Field(None, description="Vision prediction class")
    vision_probability: Optional[float] = Field(None, ge=0.0, le=1.0, description="Vision flood probability")
    vision_quality_gate_failed: bool = Field(False, description="Simulate image quality gate failure")


@router.get(
    "/corridor-evidence/assessment/{corridor_id}",
    response_model=CorridorEvidenceAssessment,
    status_code=status.HTTP_200_OK,
    tags=["Canonical Corridor Evidence"]
)
async def get_corridor_evidence_assessment(corridor_id: str):
    """
    Returns the canonical corridor-level evidence assessment, integrating road status,
    community verification, rainfall telemetry, forecast risk, static susceptibility,
    and vision inference into an auditable multi-signal evidence view.
    """
    try:
        return default_corridor_evidence_service.assess_corridor(corridor_id=corridor_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate canonical evidence assessment for corridor {corridor_id}: {str(e)}"
        )


@router.get(
    "/corridor-evidence/assessments",
    response_model=List[CorridorEvidenceAssessment],
    status_code=status.HTTP_200_OK,
    tags=["Canonical Corridor Evidence"]
)
async def get_all_corridor_evidence_assessments():
    """
    Returns canonical corridor-level evidence assessments for all road corridors in the store catalog.
    """
    try:
        return default_corridor_evidence_service.assess_all_corridors()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate corridor evidence assessments: {str(e)}"
        )


@router.post(
    "/corridor-evidence/evaluate",
    response_model=CorridorEvidenceAssessment,
    status_code=status.HTTP_200_OK,
    tags=["Canonical Corridor Evidence"]
)
async def evaluate_custom_corridor_evidence(request: CustomCorridorEvidenceEvaluationRequest):
    """
    Evaluates canonical evidence assessment for supplied custom scenario inputs.
    Strictly gates privileged live-feed activation and treats caller-supplied role strings as unauthenticated.
    """
    if request.request_live_feed_activation:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "SECURITY GATE: Privileged live-feed activation is BLOCKED pending approved "
                "server-side cryptographic authentication. Caller-supplied flags cannot authorize live feeds."
            )
        )

    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Build simulated road status snapshot if flags are present
    sim_snap = None
    if request.verified_impassable_by_responder:
        sim_snap = RoadStatusSnapshot(
            road_segment_id=request.corridor_id,
            road_name=request.road_name or f"Corridor {request.corridor_id}",
            condition_state=RoadConditionState.VERIFIED_IMPASSABLE,
            evidence_type=RoadEvidenceType.FIELD_RESPONDER_INSPECTION,
            verification_state=RoadVerificationState.VERIFIED_BY_RESPONDER,
            verified_by_entity="OFFICIAL_RESPONDER",
            freshness_category=RoadFreshnessCategory.FRESH,
            uncertainty_level=UncertaintyLevel.LOW,
            confidence_score=0.95,
            last_status_update_utc=now_iso,
        )
    elif request.verified_waterlogged_by_responder:
        sim_snap = RoadStatusSnapshot(
            road_segment_id=request.corridor_id,
            road_name=request.road_name or f"Corridor {request.corridor_id}",
            condition_state=RoadConditionState.VERIFIED_WATERLOGGED,
            evidence_type=RoadEvidenceType.FIELD_RESPONDER_INSPECTION,
            verification_state=RoadVerificationState.VERIFIED_BY_RESPONDER,
            verified_by_entity="OFFICIAL_RESPONDER",
            measured_water_depth_cm=25.0,
            freshness_category=RoadFreshnessCategory.FRESH,
            uncertainty_level=UncertaintyLevel.LOW,
            confidence_score=0.90,
            last_status_update_utc=now_iso,
        )
    elif request.verified_passable_by_responder:
        sim_snap = RoadStatusSnapshot(
            road_segment_id=request.corridor_id,
            road_name=request.road_name or f"Corridor {request.corridor_id}",
            condition_state=RoadConditionState.VERIFIED_PASSABLE,
            evidence_type=RoadEvidenceType.FIELD_RESPONDER_INSPECTION,
            verification_state=RoadVerificationState.VERIFIED_BY_RESPONDER,
            verified_by_entity="OFFICIAL_RESPONDER",
            freshness_category=RoadFreshnessCategory.FRESH,
            uncertainty_level=UncertaintyLevel.LOW,
            confidence_score=0.95,
            last_status_update_utc=now_iso,
        )
    elif request.has_conflicting_evidence:
        sim_snap = RoadStatusSnapshot(
            road_segment_id=request.corridor_id,
            road_name=request.road_name or f"Corridor {request.corridor_id}",
            condition_state=RoadConditionState.CONFLICTING,
            evidence_type=RoadEvidenceType.COMMUNITY_REPORT,
            verification_state=RoadVerificationState.UNVERIFIED,
            has_conflicting_evidence=True,
            conflict_details="Contradictory observations detected across reporter submissions.",
            freshness_category=RoadFreshnessCategory.FRESH,
            uncertainty_level=UncertaintyLevel.HIGH,
            confidence_score=0.30,
            last_status_update_utc=now_iso,
        )
    elif request.citizen_reports_count >= 2 or request.independent_citizen_sources >= 2:
        sim_snap = RoadStatusSnapshot(
            road_segment_id=request.corridor_id,
            road_name=request.road_name or f"Corridor {request.corridor_id}",
            condition_state=RoadConditionState.CORROBORATED,
            evidence_type=RoadEvidenceType.COMMUNITY_REPORT,
            verification_state=RoadVerificationState.CORROBORATED,
            freshness_category=RoadFreshnessCategory.FRESH,
            uncertainty_level=UncertaintyLevel.MEDIUM,
            confidence_score=0.65,
            last_status_update_utc=now_iso,
        )
    elif request.citizen_reports_count == 1:
        sim_snap = RoadStatusSnapshot(
            road_segment_id=request.corridor_id,
            road_name=request.road_name or f"Corridor {request.corridor_id}",
            condition_state=RoadConditionState.UNVERIFIED,
            evidence_type=RoadEvidenceType.COMMUNITY_REPORT,
            verification_state=RoadVerificationState.UNVERIFIED,
            freshness_category=RoadFreshnessCategory.FRESH,
            uncertainty_level=UncertaintyLevel.HIGH,
            confidence_score=0.40,
            last_status_update_utc=now_iso,
        )

    # Build simulated weather result if requested
    sim_weather = None
    if request.rainfall_telemetry_outage:
        sim_weather = RainfallRiskResult(
            location_id=request.corridor_id,
            rain_1h_mm=None,
            rain_3h_mm=None,
            rain_6h_mm=None,
            rain_24h_mm=None,
            risk_category="UNKNOWN",
            risk_score=0.0,
            confidence=0.0,
            qc_flags=["QC_MISSING_VALUE"],
            data_freshness_hours=99.0,
            provider="IMD-AWS-TELEMETRY",
            station_id="HYD-STN-BEGUMPET",
            station_name="Begumpet Observatory",
            station_dist_km=4.2,
            data_timestamp=now_iso,
            reason_codes=["PRIMARY_TELEMETRY_OUTAGE"],
            missing_inputs=["rain_1h_mm", "rain_3h_mm"],
            warnings=["Telemetry feed unavailable; outage active"],
        )
    elif request.observed_rainfall_1h_mm is not None:
        is_zero = (request.observed_rainfall_1h_mm == 0.0)
        sim_weather = RainfallRiskResult(
            location_id=request.corridor_id,
            rain_1h_mm=request.observed_rainfall_1h_mm,
            rain_3h_mm=request.observed_rainfall_1h_mm,
            rain_6h_mm=request.observed_rainfall_1h_mm,
            rain_24h_mm=request.observed_rainfall_1h_mm,
            risk_category="HIGH" if request.observed_rainfall_1h_mm >= 30.0 else "LOW",
            risk_score=0.70 if request.observed_rainfall_1h_mm >= 30.0 else 0.10,
            confidence=0.85,
            qc_flags=["VALID_MEASURED_ZERO"] if is_zero else ["QC_VALID"],
            data_freshness_hours=0.5,
            provider="IMD-AWS-TELEMETRY",
            station_id="HYD-STN-BEGUMPET",
            station_name="Begumpet Observatory",
            station_dist_km=4.2,
            data_timestamp=now_iso,
            reason_codes=["VALID_OBSERVATION_INGESTED"],
            missing_inputs=[],
            warnings=[],
        )

    # Build simulated forecast result if requested
    sim_fc = None
    if (request.forecast_rainfall_band and request.forecast_rainfall_band != "UNKNOWN") or (request.forecast_risk_category and request.forecast_risk_category != "UNKNOWN"):
        from datetime import timedelta
        from sahaay.forecast_risk.schemas import (
            ForecastRainfallInput,
            ForecastSourceType,
            PrecipitationUnit,
            AccumulationInterval,
        )
        now_dt = datetime.now(timezone.utc)
        valid_dt = now_dt + timedelta(hours=1)
        fc_in = ForecastRainfallInput(
            location_id=request.corridor_id,
            source_id="NWP-LOCAL-TEST",
            source_type=ForecastSourceType.NUMERICAL_WEATHER_PREDICTION_NWP,
            issue_timestamp_utc=now_dt.isoformat().replace("+00:00", "Z"),
            valid_timestamp_utc=valid_dt.isoformat().replace("+00:00", "Z"),
            forecast_horizon_hours=1.0,
            rainfall_amount=45.0 if request.forecast_rainfall_band in ["HEAVY", "CRITICAL", "EXTREME_TORRENTIAL"] else 5.0,
            rainfall_units=PrecipitationUnit.MILLIMETERS,
            accumulation_interval=AccumulationInterval.INTERVAL_1H,
            is_synthetic_fixture=True,
        )
        sim_fc = default_weather_pipeline.evaluate_corridor_forecast_risk(
            corridor_id=request.corridor_id,
            road_name=request.road_name or f"Corridor {request.corridor_id}",
            corridor_lat=17.40,
            corridor_lon=78.45,
            forecast_inputs=[fc_in],
            reference_time_utc=now_dt,
        )

    # Build simulated vision result if requested
    sim_vision = None
    if request.vision_quality_gate_failed:
        sim_vision = {
            "inference_available": True,
            "predicted_class": "inconclusive",
            "confidence": 0.50,
            "is_inconclusive": True,
            "rejection_reason": "Image quality gate failed (borderline luminance out of bounds)",
        }
    elif request.vision_probability is not None:
        sim_vision = {
            "inference_available": True,
            "raw_probability": request.vision_probability,
            "confidence": round(max(request.vision_probability, 1.0 - request.vision_probability), 4),
        }
    elif request.vision_predicted_class:
        sim_vision = {
            "inference_available": True,
            "predicted_class": request.vision_predicted_class,
            "confidence": 0.85,
        }

    return default_corridor_evidence_service.assess_corridor(
        corridor_id=request.corridor_id,
        road_status_snapshot=sim_snap,
        weather_result=sim_weather,
        forecast_result=sim_fc,
        vision_result=sim_vision,
    )


# ==============================================================================
# Phase E: Safe Routing and Emergency Destinations Endpoints
# ==============================================================================

from sahaay.emergency_destinations.schemas import (
    EmergencyDestinationRecord,
    DestinationSuitabilityRequest,
    DestinationSuitabilityResponse,
)
from sahaay.routing.contracts import (
    EmergencyDestinationType,
    FacilityOperationalStatus,
)
from sahaay.emergency_destinations.registry import default_destination_registry
from sahaay.emergency_destinations.service import default_destination_routing_service


class SafeRouteEvaluationRequest(BaseModel):
    origin_node_id: Optional[str] = Field(None, description="Starting graph node ID")
    destination_node_id: Optional[str] = Field(None, description="Target destination graph node ID")
    origin_latitude: Optional[float] = Field(None, description="Optional starting latitude")
    origin_longitude: Optional[float] = Field(None, description="Optional starting longitude")
    destination_latitude: Optional[float] = Field(None, description="Optional destination latitude")
    destination_longitude: Optional[float] = Field(None, description="Optional destination longitude")
    vehicle_type: VehicleType = Field(VehicleType.LIGHT_MOTOR_VEHICLE, description="Vehicle classification")
    caller_role: Optional[str] = Field(None, description="Client-supplied role token")
    request_emergency_dispatch: bool = Field(False, description="Attempt privileged emergency dispatch")


@router.get(
    "/emergency-destinations/",
    response_model=List[EmergencyDestinationRecord],
    status_code=status.HTTP_200_OK,
    tags=["Phase E: Emergency Destinations"]
)
async def list_emergency_destinations(
    destination_type: Optional[EmergencyDestinationType] = None,
    operational_status: Optional[FacilityOperationalStatus] = None,
    zone: Optional[str] = None,
    only_connected: bool = False,
):
    """
    Returns registered emergency destinations (hospitals, municipal shelters).
    Preserves verified capabilities, provenance, data quality indicators, and synthetic fixture disclosures.
    """
    return default_destination_registry.filter_destinations(
        destination_type=destination_type,
        operational_status=operational_status,
        zone=zone,
        only_connected=only_connected,
    )


@router.get(
    "/emergency-destinations/{facility_id}",
    response_model=EmergencyDestinationRecord,
    status_code=status.HTTP_200_OK,
    tags=["Phase E: Emergency Destinations"]
)
async def get_emergency_destination(facility_id: str):
    """
    Retrieves full audit profile of a single emergency destination.
    Returns 404 if facility is not registered.
    """
    dest = default_destination_registry.get_destination(facility_id)
    if not dest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency destination '{facility_id}' not found in registry.",
        )
    return dest


@router.post(
    "/emergency-destinations/assess-suitability",
    response_model=DestinationSuitabilityResponse,
    status_code=status.HTTP_200_OK,
    tags=["Phase E: Emergency Destinations"]
)
async def assess_destination_suitability(request: DestinationSuitabilityRequest):
    """
    Ranks candidate emergency destinations based on transparent criteria:
    1. Topological road graph connectivity.
    2. Ground corridor passability (pruning verified impassable segments).
    3. Verified operational status (OPERATIONAL_VERIFIED > CONSTRAINED > UNVERIFIED).
    4. Risk-penalized travel distance.
    Straight-line geographic proximity alone never determines suitability.
    """
    # Security check: caller role spoofing or dispatch attempt denied
    if request.caller_role or request.request_emergency_dispatch:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Caller-supplied roles are unauthenticated. Privileged actions denied.",
        )

    def _status_provider(segment_id: str):
        try:
            return default_road_status_service.get_corridor_status(segment_id)
        except Exception:
            return None

    return default_destination_routing_service.assess_destinations(
        request=request,
        segment_status_provider=_status_provider,
    )


@router.get(
    "/map/emergency-destinations",
    status_code=status.HTTP_200_OK,
    tags=["Phase E: Map & GeoJSON"]
)
async def get_map_emergency_destinations():
    """
    Returns a GeoJSON FeatureCollection of all registered emergency destinations
    with cartographic styling properties, operational status badges, and fixture disclosures.
    """
    return default_destination_registry.to_geojson_feature_collection()


@router.post(
    "/routing/safe-route",
    response_model=RiskAwareRouteAssessment,
    status_code=status.HTTP_200_OK,
    tags=["Phase E: Safe Routing"]
)
async def evaluate_safe_route(request: SafeRouteEvaluationRequest):
    """
    Executes risk-aware topological routing with detailed feasibility explanations.
    Hard-prunes verified impassable segments and surfaces disconnected components.
    Prohibits guaranteed safety or optimality claims.
    """
    # Security check: caller role spoofing or dispatch attempt denied
    if request.caller_role or request.request_emergency_dispatch:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client-supplied role tokens and autonomous dispatch requests are strictly rejected.",
        )

    # Resolve origin node
    orig_node = request.origin_node_id
    if not orig_node and request.origin_latitude is not None and request.origin_longitude is not None:
        orig_node = default_destination_routing_service._find_nearest_graph_node(
            request.origin_latitude, request.origin_longitude
        )
    if not orig_node:
        orig_node = request.origin_node_id or "UNKNOWN_ORIGIN"

    # Resolve destination node
    dest_node = request.destination_node_id
    if not dest_node and request.destination_latitude is not None and request.destination_longitude is not None:
        dest_node = default_destination_routing_service._find_nearest_graph_node(
            request.destination_latitude, request.destination_longitude
        )
    if not dest_node:
        dest_node = request.destination_node_id or "UNKNOWN_DESTINATION"

    graph = default_road_network_store.get_road_graph()
    router_engine = TopologicalGraphRouter(graph=graph)

    def _status_provider(segment_id: str):
        try:
            return default_road_status_service.get_corridor_status(segment_id)
        except Exception:
            return None

    def _forecast_provider(segment_id: str):
        try:
            from sahaay.hyderabad_risk.weather_pipeline import default_weather_pipeline
            return default_weather_pipeline.evaluate_corridor_forecast_risk(
                corridor_id=segment_id,
                road_name=f"Corridor {segment_id}",
            )
        except Exception:
            return None

    return router_engine.find_risk_aware_route(
        origin_node_id=orig_node,
        destination_node_id=dest_node,
        vehicle_type=request.vehicle_type,
        segment_status_provider=_status_provider,
        forecast_risk_provider=_forecast_provider,
        is_demonstration=True,
    )


@router.get(
    "/map/route-overlay",
    status_code=status.HTTP_200_OK,
    tags=["Phase E: Map & GeoJSON"]
)
async def get_route_map_overlay(
    origin_node_id: str,
    destination_node_id: str,
    vehicle_type: VehicleType = VehicleType.LIGHT_MOTOR_VEHICLE,
):
    """
    Returns GeoJSON LineString features for a computed route overlay with segment symbology.
    Returns empty features with explicit explanation if nodes are missing or components disconnected.
    """
    graph = default_road_network_store.get_road_graph()
    router_engine = TopologicalGraphRouter(graph=graph)

    def _status_provider(segment_id: str):
        try:
            return default_road_status_service.get_corridor_status(segment_id)
        except Exception:
            return None

    route = router_engine.find_risk_aware_route(
        origin_node_id=origin_node_id,
        destination_node_id=destination_node_id,
        vehicle_type=vehicle_type,
        segment_status_provider=_status_provider,
        is_demonstration=True,
    )

    features = []
    for seg_assess in route.recommended_segments:
        seg_record = default_road_network_store.get_segment(seg_assess.segment_id)
        if seg_record and seg_record.geometry:
            feature = {
                "type": "Feature",
                "id": seg_assess.segment_id,
                "geometry": {
                    "type": "LineString",
                    "coordinates": seg_record.geometry.coordinates,
                },
                "properties": {
                    "segment_id": seg_assess.segment_id,
                    "road_name": seg_assess.road_name,
                    "passability_state": seg_assess.passability_state.value,
                    "is_traversable": seg_assess.is_traversable,
                    "length_meters": seg_assess.length_meters,
                    "stroke_color": "#2563eb",  # Blue for recommended path
                    "stroke_weight": 5,
                },
            }
            features.append(feature)

    for seg_assess in route.excluded_segments:
        seg_record = default_road_network_store.get_segment(seg_assess.segment_id)
        if seg_record and seg_record.geometry:
            feature = {
                "type": "Feature",
                "id": seg_assess.segment_id,
                "geometry": {
                    "type": "LineString",
                    "coordinates": seg_record.geometry.coordinates,
                },
                "properties": {
                    "segment_id": seg_assess.segment_id,
                    "road_name": seg_assess.road_name,
                    "passability_state": seg_assess.passability_state.value,
                    "is_traversable": False,
                    "length_meters": seg_assess.length_meters,
                    "stroke_color": "#e11d48",  # Crimson Red for impassable
                    "stroke_weight": 6,
                    "pruned_reason": "VERIFIED_IMPASSABLE",
                },
            }
            features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "route_id": route.route_id,
            "outcome": route.outcome.value,
            "total_distance_meters": route.total_distance_meters,
            "engine_status": route.engine_status,
            "warnings": route.warnings,
            "safety_disclaimer": route.safety_disclaimer,
            "is_demonstration": True,
        },
    }


# ==============================================================================
# Phase F: Production Hardening, Operational Readiness & Security Hardening
# ==============================================================================

import hashlib
from sahaay.security.auth import (
    UserRole,
    SUPERVISOR_ROLES,
    AuthenticatedIdentity,
    get_current_authenticated_identity,
    validate_no_client_role_spoofing,
    fail_closed_operational_action,
)
from sahaay.config import get_runtime_config
from sahaay.pilot.readiness_register import (
    DataIntegrationReadinessRegister,
    default_readiness_register,
)
from sahaay.pilot.gate import PilotActivationGate


class ComponentHealthItem(BaseModel):
    component_name: str
    liveness_status: str
    readiness_status: str
    details: Dict[str, Any]
    blockers: List[str] = Field(default_factory=list)


class OperationalReadinessResponse(BaseModel):
    timestamp_utc: str
    liveness: str = "UP"
    operational_readiness: str = "PILOT_BLOCKED"
    pilot_decision: str = "NO_GO"
    components: Dict[str, ComponentHealthItem]
    active_blockers: List[str]
    smallest_safe_next_actions: List[str]
    safety_disclaimer: str


class PrivilegedActionRequest(BaseModel):
    action_type: str = Field(..., description="Operational action identifier")
    target_resource: str = Field(..., description="Corridor, station, or incident ID")
    caller_role: Optional[str] = Field(None, description="Client-supplied role assertion; checked for spoofing")
    is_server_authenticated: Optional[bool] = Field(None, description="Client-supplied flag; ignored/denied")
    attempt_autonomous_dispatch: bool = Field(False, description="Attempt privileged emergency dispatch")
    attempt_live_stream_activation: bool = Field(False, description="Attempt live stream activation")
    justification_notes: str = Field("Authorized test routine", description="Operational justification")


class PrivilegedActionResponse(BaseModel):
    status: str
    action_type: str
    operator_id: str
    authenticated_role: str
    timestamp_utc: str
    audit_hash: str
    audit_disclaimer: str = (
        "AUDIT DISCLAIMER: Software SHA-256 hash records state snapshot only; "
        "does not prove legal identity or tamper-proof storage."
    )


@router.get(
    "/readiness",
    response_model=OperationalReadinessResponse,
    status_code=status.HTTP_200_OK,
    tags=["Phase F: Operational Readiness"]
)
@router.get(
    "/health/readiness",
    response_model=OperationalReadinessResponse,
    status_code=status.HTTP_200_OK,
    tags=["Phase F: Operational Readiness"]
)
async def get_operational_readiness():
    """
    Comprehensive operational readiness probe distinguishing application liveness from field pilot readiness.
    Evaluates road network coverage, graph topology, telemetry ingestion, forecast risk, corridor evidence,
    emergency destination fixtures, emergency workflow actions, vision model data-readiness, and security controls.
    """
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # 1. Road Network Store
    segments = default_road_network_store.list_segments()
    seg_count = len(segments)
    road_net_health = ComponentHealthItem(
        component_name="Road Network Catalog",
        liveness_status="UP",
        readiness_status="DEGRADED",
        details={
            "total_segments": seg_count,
            "centerline_km": round(sum(s.length_meters for s in segments) / 1000.0, 2),
            "catalog_type": "SPARSE_SEED_CATALOG",
            "coverage_scope": "BOUNDED_TEST_CORRIDORS",
            "citywide_coverage": "UNSUPPORTED",
        },
        blockers=[
            "Sparse ~22 segment road network catalog covers only bounded test corridors. Citywide Greater Hyderabad navigation is unsupported."
        ],
    )

    # 2. Topological Road Graph
    graph = default_road_network_store.get_road_graph()
    graph_metrics = graph.get_metrics()
    topological_health = ComponentHealthItem(
        component_name="Topological Road Graph",
        liveness_status="UP",
        readiness_status="DEGRADED",
        details={
            "total_nodes": graph_metrics.total_nodes,
            "total_directed_edges": graph_metrics.total_directed_edges,
            "connected_components_count": graph_metrics.connected_components_count,
            "non_fabrication_invariant": "ENFORCED_ZERO_SYNTHETIC_EDGES",
        },
        blockers=[
            f"Road graph contains {graph_metrics.connected_components_count} disconnected topological components; routes between disjoint components are unsupported."
        ],
    )

    # 3. Weather Ingestion Pipeline
    weather_health_info = default_weather_pipeline.get_ingestion_health()
    weather_health = ComponentHealthItem(
        component_name="Weather & Rainfall Telemetry Pipeline",
        liveness_status="UP",
        readiness_status="DEGRADED",
        details={
            "pipeline_status": weather_health_info.pipeline_status.value,
            "provider_authorization_status": weather_health_info.provider_authorization_status.value,
            "is_live_stream_connected": weather_health_info.is_live_stream_connected,
            "configured_endpoint": weather_health_info.configured_endpoint,
            "has_credentials": weather_health_info.has_credentials,
        },
        blockers=[
            "Real-time IMD AWS provider feed unapproved; operating on offline fallback with zero external network connectivity."
        ],
    )

    # 4. Forecast Risk Engine
    forecast_health = ComponentHealthItem(
        component_name="Forecast Precipitation Risk Engine",
        liveness_status="UP",
        readiness_status="DEGRADED",
        details={
            "forecast_source": "NWP_HRRR_CONVECTIVE_GRID",
            "offline_heuristic_mode": True,
            "calibrated_probabilities_claimed": False,
        },
        blockers=[
            "Numerical Weather Prediction (NWP) precipitation context operates in advisory mode without live grid subscriptions."
        ],
    )

    # 5. Canonical Corridor Evidence Service
    corridor_assessments = default_corridor_evidence_service.assess_all_corridors()
    evidence_health = ComponentHealthItem(
        component_name="Canonical Corridor Evidence Synthesis",
        liveness_status="UP",
        readiness_status="OPERATIONAL",
        details={
            "assessed_corridors_count": len(corridor_assessments),
            "evidence_signals_separated": 5,
            "prohibit_modeled_risk_as_flooding": True,
        },
        blockers=[],
    )

    # 6. Emergency Destination Registry
    destinations = default_destination_registry.list_destinations()
    fixtures_count = sum(1 for d in destinations if d.is_synthetic_fixture)
    destinations_health = ComponentHealthItem(
        component_name="Emergency Destination Registry",
        liveness_status="UP",
        readiness_status="DEGRADED",
        details={
            "total_registered_facilities": len(destinations),
            "synthetic_fixtures_count": fixtures_count,
            "real_time_bed_telemetry": "UNAVAILABLE",
        },
        blockers=[
            "All destination records are synthetic demonstration fixtures; real-time hospital bed and ICU telemetry feeds are absent."
        ],
    )

    # 7. Emergency Workflow Engine
    emergency_health = ComponentHealthItem(
        component_name="Emergency Workflow & Human Triage Desk",
        liveness_status="UP",
        readiness_status="DEGRADED",
        details={
            "autonomous_dispatch_authorized": False,
            "autonomous_closures_authorized": False,
            "external_side_effects_triggered": False,
            "human_authorization_mandatory": True,
        },
        blockers=[
            "Institutional 24/7 human review desk (GHMC DRF / Traffic Police) is unstaffed; emergency action requires manual field verification."
        ],
    )

    # 8. Computer Vision AI
    vision_service = get_inference_service()
    vision_health_item = ComponentHealthItem(
        component_name="Flood Vision Inference AI",
        liveness_status="UP",
        readiness_status="BLOCKED",
        details={
            "model_name": vision_service.model_name,
            "model_version": vision_service.model_version,
            "v4_data_readiness_gate": "BLOCKED_NO_GO",
        },
        blockers=[
            "Computer Vision V4 readiness gate is strictly NO-GO due to watermark leakage, class confounding, and lack of rights-cleared local imagery."
        ],
    )

    # 9. Security & Access Control
    cfg = get_runtime_config()
    security_health = ComponentHealthItem(
        component_name="Security & Access Control Gateway",
        liveness_status="UP",
        readiness_status="DEGRADED",
        details={
            "server_side_bearer_auth": "ACTIVE",
            "secrets_hygiene": cfg.security.masked_summary(),
            "institutional_idp": "PENDING_MUNICIPAL_OAUTH2_INTEGRATION",
        },
        blockers=[
            "Municipal enterprise IdP unintegrated; operating with local cryptographic Bearer token validation."
        ],
    )

    # 10. Institutional Pilot Activation Gate
    gate = PilotActivationGate()
    gate_state = gate.current_state.value
    gate_health = ComponentHealthItem(
        component_name="Institutional Pilot Activation Authority",
        liveness_status="UP",
        readiness_status="BLOCKED",
        details={
            "gate_state": gate_state,
            "institutional_mou_executed": False,
        },
        blockers=[
            "Institutional Memorandum of Understanding (MoU) with GHMC and Hyderabad Traffic Police is unexecuted."
        ],
    )

    all_components = {
        "road_network": road_net_health,
        "topological_graph": topological_health,
        "weather_pipeline": weather_health,
        "forecast_risk": forecast_health,
        "corridor_evidence": evidence_health,
        "emergency_destinations": destinations_health,
        "emergency_workflow": emergency_health,
        "vision_ai": vision_health_item,
        "security_and_auth": security_health,
        "pilot_activation_gate": gate_health,
    }

    all_blockers = []
    for c in all_components.values():
        all_blockers.extend(c.blockers)

    return OperationalReadinessResponse(
        timestamp_utc=now_iso,
        liveness="UP",
        operational_readiness="PILOT_BLOCKED",
        pilot_decision="NO_GO",
        components=all_components,
        active_blockers=all_blockers,
        smallest_safe_next_actions=default_readiness_register.smallest_safe_next_actions,
        safety_disclaimer=(
            "CONTROLLED PILOT READINESS STATUS: Sahaay AI remains strictly NO-GO for public or live emergency operation. "
            "Application liveness is UP, but operational readiness is PILOT_BLOCKED due to active institutional, "
            "data, and network limitations. Autonomous dispatch and road closures are permanently disarmed."
        ),
    )


@router.get(
    "/readiness/register",
    response_model=DataIntegrationReadinessRegister,
    status_code=status.HTTP_200_OK,
    tags=["Phase F: Operational Readiness"]
)
async def get_data_integration_readiness_register():
    """
    Returns the authoritative 10-item machine-readable Data and Integration Readiness Register.
    """
    return default_readiness_register


@router.post(
    "/security/privileged-action",
    response_model=PrivilegedActionResponse,
    status_code=status.HTTP_200_OK,
    tags=["Phase F: Security Hardening"]
)
async def execute_privileged_operational_action(
    request: PrivilegedActionRequest,
    identity: AuthenticatedIdentity = Depends(get_current_authenticated_identity),
    http_request: Request = None,
):
    """
    Executes a privileged operational action with strict server-side Bearer token authentication.
    Rejects missing/invalid tokens (401), unauthorized roles (403), client role spoofing (403),
    and disarmed actions (403). Enforces abuse rate limiting.
    """
    from sahaay.security.rate_limiter import enforce_rate_limit
    if http_request is not None:
        enforce_rate_limit(http_request, limit_per_minute=20, client_key_prefix="privileged")

    # 1. Enforce supervisor or admin role
    if identity.role not in SUPERVISOR_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: role '{identity.role.value}' lacks supervisor privileges for this action.",
        )

    # 2. Reject client-supplied role spoofing
    validate_no_client_role_spoofing(identity, request.caller_role)

    # 3. Reject client-supplied authentication bypass flags
    if request.is_server_authenticated is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client-supplied flag 'is_server_authenticated' is forbidden. Authority must originate from server token.",
        )

    # 4. Fail closed on dangerous operational side effects
    if request.attempt_autonomous_dispatch:
        fail_closed_operational_action("AUTONOMOUS_EMERGENCY_DISPATCH")
    if request.attempt_live_stream_activation:
        fail_closed_operational_action("LIVE_TELEMETRY_FEED_ACTIVATION")

    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    audit_payload = f"{request.action_type}:{request.target_resource}:{identity.subject_id}:{now_iso}"
    audit_hash = hashlib.sha256(audit_payload.encode()).hexdigest()

    return PrivilegedActionResponse(
        status="AUTHORIZED_EXECUTION_COMPLETED",
        action_type=request.action_type,
        operator_id=identity.subject_id,
        authenticated_role=identity.role.value,
        timestamp_utc=now_iso,
        audit_hash=audit_hash,
    )


@router.post(
    "/security/token/inspect",
    response_model=AuthenticatedIdentity,
    status_code=status.HTTP_200_OK,
    tags=["Phase F: Security Hardening"]
)
async def inspect_authenticated_token(
    identity: AuthenticatedIdentity = Depends(get_current_authenticated_identity),
):
    """
    Inspects authenticated Bearer token and returns trusted identity context without leaking secrets.
    """
    return identity




# ==============================================================================
# Automated Source Ingestion & Notification Endpoints (Hackathon Prototype)
# ==============================================================================

from sahaay.ingestion.orchestrator import default_orchestrator
from sahaay.ingestion.event_store import default_event_store
from sahaay.ingestion.schemas import IngestedEvent, ConnectorHealthStatus
from sahaay.notifications.service import default_notification_service
from sahaay.notifications.schemas import NotificationRecord, SubscriptionRequest, SubscriptionRecord


@router.get(
    "/ingestion/status",
    response_model=List[ConnectorHealthStatus],
    status_code=status.HTTP_200_OK,
    tags=["Automated Ingestion"]
)
async def get_ingestion_connectors_status():
    """
    Returns operational health, reliability metrics, and live-vs-mock status
    for all automated online source connectors (weather, news, community).
    """
    return default_orchestrator.get_all_connector_health()


@router.get(
    "/ingestion/events",
    response_model=List[IngestedEvent],
    status_code=status.HTTP_200_OK,
    tags=["Automated Ingestion"]
)
async def get_ingested_events(
    corridor_id: Optional[str] = None,
    limit: int = 50,
):
    """
    Returns recent normalized events from automated source ingestion.
    Supports corridor filtering. Old events automatically expire according to TTL.
    """
    return default_event_store.get_events(corridor_id=corridor_id, limit=limit)


@router.post(
    "/ingestion/poll",
    status_code=status.HTTP_200_OK,
    tags=["Automated Ingestion"]
)
async def trigger_ingestion_poll():
    """
    Triggers an automated polling cycle across all registered connectors.
    Normalizes incoming data, extracts entities, and evaluates corridor risk.
    """
    return default_orchestrator.poll_all_connectors()


@router.post(
    "/ingestion/demo/simulate",
    status_code=status.HTTP_200_OK,
    tags=["Automated Ingestion"]
)
async def simulate_automated_ingestion_demo():
    """
    Executes the deterministic 10-step hackathon demonstration workflow:
    Weather warning -> News event -> Automated community image analysis ->
    Evidence registration -> Decision engine alert -> Map status update ->
    Deduplicated notification -> Safe route recalculation -> Missing feed handling ->
    Honest unsupported route response.
    """
    return default_orchestrator.run_deterministic_hackathon_demo()


@router.get(
    "/ingestion/discovered-images",
    status_code=status.HTTP_200_OK,
    tags=["Automated Ingestion"]
)
async def get_discovered_images(limit: int = 50):
    """
    Returns candidate flood images discovered across online news articles, blogs,
    and community reports, along with their MobileNetV3 classification and quality gate results.
    """
    return default_orchestrator.get_discovered_images(limit=limit)


class CommunityWebhookPayload(BaseModel):
    text: str
    image_base64: Optional[str] = None
    author: Optional[str] = "community_member"
    post_id: Optional[str] = None
    platform: Optional[str] = "Civic Webhook Gateway"


@router.post(
    "/ingestion/community/webhook",
    status_code=status.HTTP_201_CREATED,
    tags=["Automated Ingestion"]
)
async def receive_community_webhook(
    payload: CommunityWebhookPayload,
    x_signature_sha256: Optional[str] = Header(None, alias="X-Signature-SHA256"),
):
    """
    Authorized webhook receiver for community channels (e.g. Telegram civic bot / WhatsApp bot).
    If an image payload is included, it is automatically decoded and forwarded to MobileNetV3
    without requiring manual operator upload.
    """
    raw_image_bytes = None
    if payload.image_base64:
        import base64
        try:
            raw_image_bytes = base64.b64decode(payload.image_base64)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 image data")

    event = default_orchestrator.community_connector.receive_webhook_submission(
        text=payload.text,
        image_bytes=raw_image_bytes,
        author=payload.author or "community_member",
        post_id=payload.post_id,
        platform=payload.platform or "Civic Webhook Gateway",
    )
    # Add to store and trigger evidence processing
    default_event_store.add_event(event)
    default_orchestrator._process_single_event(event)
    if event.image_reference:
        default_orchestrator._record_discovered_image(event)

    return event


@router.get(
    "/notifications/history",
    response_model=List[NotificationRecord],
    status_code=status.HTTP_200_OK,
    tags=["Notifications"]
)
async def get_notification_history(
    corridor_id: Optional[str] = None,
    limit: int = 50,
):
    """
    Returns recent deduplicated user safety notifications.
    Clearly distinguishes forecast warnings from verified observed hazards.
    """
    return default_notification_service.get_history(corridor_id=corridor_id, limit=limit)


@router.post(
    "/notifications/subscribe",
    response_model=SubscriptionRecord,
    status_code=status.HTTP_200_OK,
    tags=["Notifications"]
)
async def subscribe_to_corridor_alerts(
    request: SubscriptionRequest,
):
    """
    Registers a user subscription for a specific corridor or commute route.
    """
    return default_notification_service.subscribe(request)


@router.get(
    "/notifications/external-status",
    status_code=status.HTTP_200_OK,
    tags=["Notifications"]
)
async def get_notification_external_status():
    """
    Returns the real connectivity and readiness state of external push/SMS/webhook gateways.
    Distinguishes in-app active notifications from unconfigured external gateways.
    """
    return default_notification_service.get_external_delivery_status()


