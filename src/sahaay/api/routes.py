"""
Sahaay AI - FastAPI Route Handlers
Implements versioned /api/v1 endpoints for Flood Vision inference and system health.
"""

from typing import Optional
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, status
from fastapi.responses import JSONResponse

from sahaay.api.schemas import (
    VisionPredictionResponse,
    VisionHealthResponse,
    ErrorResponse
)
from sahaay.decision.contracts import DecisionInput, DecisionOutput, evaluate_decision
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
