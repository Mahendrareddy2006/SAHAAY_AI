"""
Sahaay AI - FastAPI Route Handlers
Implements versioned /api/v1 endpoints for Flood Vision inference and system health.
"""

from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, status
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
        "service": "Sahaay AI Platform API",
        "version": "1.0.0"
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
    file: UploadFile = File(..., description="JPEG, PNG, or WEBP image (max 15MB)"),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    report_id: Optional[str] = Form(None)
):
    """
    Flood Vision AI Inference Endpoint.
    Analyzes submitted image for visual evidence of standing flood water / road waterlogging.
    """
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
        return result
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
async def verify_citizen_report(report_id: str, request: ReportVerificationRequest):
    """
    Updates the verification status of a ground report by an authorized responder.
    """
    record = report_service.verify_report(report_id, request)
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
async def submit_review_action(submission: ReviewActionSubmission):
    """Submits an attributable, cryptographically hashed human review decision."""
    try:
        return review_queue_service.record_review_action(
            item_id=submission.item_id,
            reviewer_role=submission.reviewer_role,
            reviewer_id=submission.reviewer_id,
            action_type=submission.action_type,
            justification_notes=submission.justification_notes,
            new_status=submission.new_status,
        )
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


