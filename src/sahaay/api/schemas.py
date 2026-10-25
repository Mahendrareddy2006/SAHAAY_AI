"""
Sahaay AI - API Schemas (Pydantic V2)
Strict data contracts for HTTP request/response payloads.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class LocationCoords(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)

class ClassScores(BaseModel):
    not_flooded: float = Field(..., ge=0.0, le=1.0)
    flooded: float = Field(..., ge=0.0, le=1.0)

class VisionPredictionResponse(BaseModel):
    prediction_id: str
    predicted_class: str
    confidence: float
    class_scores: ClassScores
    is_ambiguous: bool
    model_name: str
    model_version: str
    device: str
    inference_latency_ms: float
    created_at: str
    report_id: Optional[str] = None
    location: Optional[LocationCoords] = None
    warnings: List[str] = Field(default_factory=list)

class VisionHealthResponse(BaseModel):
    status: str
    model_name: str
    model_version: str
    checkpoint_loaded: bool
    device: str

class ErrorResponse(BaseModel):
    error: str
    detail: str
    code: str
