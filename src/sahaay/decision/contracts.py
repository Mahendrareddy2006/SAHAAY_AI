"""
Sahaay AI - Decision Engine Component Contracts
Synthesizes visual evidence, rainfall risk, road vulnerability, and verification metadata
into an explainable, multi-factor alert level.
"""

from enum import Enum
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

class AlertLevel(str, Enum):
    CLEAR = "CLEAR"              # Normal baseline, no hazard
    ADVISORY = "ADVISORY"        # Stale/unverified report or elevated rainfall on safe road
    WATCH = "WATCH"              # Heavy forecast rain on vulnerable road (predicted risk)
    WARNING = "WARNING"          # Verified visual waterlogging or critical rainfall on vulnerable road
    EMERGENCY = "EMERGENCY"      # Confirmed deep flood, impassable road, immediate hazard

class HazardNature(str, Enum):
    OBSERVED_HAZARD = "OBSERVED_HAZARD"       # Ground truth verified via image or inspection
    PREDICTED_RISK = "PREDICTED_RISK"         # Anticipated from rainfall & vulnerability
    COMMUNITY_REPORT = "COMMUNITY_REPORT"     # Citizen submission awaiting field verification
    MAINTENANCE_NOTICE = "MAINTENANCE_NOTICE" # Desilting / drain clearance log

class DecisionInput(BaseModel):
    location_id: str
    road_name: str
    # Component 1: Vision Evidence
    vision_predicted_class: Optional[str] = Field(None, description="'flooded' or 'not_flooded'")
    vision_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    vision_is_ambiguous: bool = False
    
    # Component 2: Rainfall Evidence
    rainfall_risk_category: str = Field("LOW", description="LOW, MEDIUM, HIGH, CRITICAL")
    rainfall_risk_score: float = Field(0.0, ge=0.0, le=1.0)
    
    # Component 3: Road Vulnerability Evidence
    vulnerability_category: str = Field("LOW", description="LOW, MODERATE, HIGH, SEVERE")
    vulnerability_index: float = Field(0.1, ge=0.0, le=1.0)
    
    # Provenance & Freshness
    report_age_minutes: float = Field(0.0, ge=0.0, description="Minutes elapsed since report/photo capture")
    is_field_verified: bool = False
    citizen_report_count_in_zone: int = Field(1, ge=1)

class DecisionOutput(BaseModel):
    location_id: str
    road_name: str
    alert_level: AlertLevel
    hazard_nature: HazardNature
    decision_score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    explanation: str
    evidence_chain: List[str]
    is_actionable_for_crews: bool
    ruleset_version: str = "decision_engine_rules_v1.0"
    created_at: str
    warnings: List[str]

def evaluate_decision(input_data: DecisionInput) -> DecisionOutput:
    """
    Evaluates evidence using explicit, auditable rules rather than opaque score multiplication.
    
    Rule Hierarchy:
    1. Fresh, high-confidence vision 'flooded' -> WARNING or EMERGENCY.
    2. Fresh vision 'not_flooded' does NOT override high rainfall risk on severe vulnerability road.
    3. Stale reports (>180 min) decay to ADVISORY unless corroborated by active rainfall.
    4. Heavy rainfall on high-vulnerability road triggers WATCH (predictive warning).
    """
    import time
    
    evidence = []
    warnings = [
        "Decision Engine advisory: Preserves uncertainty and separates observed from predicted risk.",
        "Not an official municipal NDRF/GHMC evacuation directive."
    ]
    
    # Freshness factor: decays over 3 hours
    is_fresh = input_data.report_age_minutes <= 180.0
    if not is_fresh:
        evidence.append(f"Data freshness decay: Report is {input_data.report_age_minutes:.0f} minutes old")
        
    # Check vision evidence
    has_vision = input_data.vision_predicted_class is not None
    visual_flood_confirmed = (
        has_vision
        and input_data.vision_predicted_class == "flooded"
        and not input_data.vision_is_ambiguous
        and (input_data.vision_confidence or 0.0) >= 0.70
    )
    
    if visual_flood_confirmed:
        evidence.append(f"Visual flood evidence: Inundation detected with {input_data.vision_confidence*100:.1f}% confidence")
    elif has_vision and input_data.vision_predicted_class == "not_flooded":
        evidence.append(f"Visual check: No surface inundation observed (confidence {input_data.vision_confidence*100:.1f}%)")
        warnings.append("Absence of visual flooding in uploaded photo does NOT confirm passability.")
        
    # Check rainfall
    if input_data.rainfall_risk_category in ["HIGH", "CRITICAL"]:
        evidence.append(f"Severe rainfall trigger: Category {input_data.rainfall_risk_category} (score {input_data.rainfall_risk_score:.2f})")
        
    # Check vulnerability
    if input_data.vulnerability_category in ["HIGH", "SEVERE"]:
        evidence.append(f"High baseline susceptibility: Road segment has {input_data.vulnerability_category} vulnerability index ({input_data.vulnerability_index:.2f})")

    # Decision Logic
    if visual_flood_confirmed and is_fresh:
        if input_data.rainfall_risk_category in ["HIGH", "CRITICAL"] or input_data.is_field_verified:
            level = AlertLevel.EMERGENCY
            hazard = HazardNature.OBSERVED_HAZARD
            score = 0.95
            explanation = "Confirmed deep street waterlogging verified by visual evidence and corroborated by severe rainfall/field verification."
            actionable = True
        else:
            level = AlertLevel.WARNING
            hazard = HazardNature.OBSERVED_HAZARD
            score = 0.85
            explanation = "Visible street flooding identified from fresh community photo upload."
            actionable = True
            
    elif input_data.rainfall_risk_category in ["HIGH", "CRITICAL"] and input_data.vulnerability_category in ["HIGH", "SEVERE"]:
        level = AlertLevel.WATCH
        hazard = HazardNature.PREDICTED_RISK
        score = 0.75
        explanation = "High waterlogging risk anticipated over the next 1-3 hours due to heavy rainfall on a chronically vulnerable road segment."
        actionable = True
        
    elif has_vision and input_data.vision_predicted_class == "flooded" and (not is_fresh or input_data.vision_is_ambiguous):
        level = AlertLevel.ADVISORY
        hazard = HazardNature.COMMUNITY_REPORT
        score = 0.45
        explanation = "Unverified or aging citizen report showing possible waterlogging. Requires field dispatch or corroboration."
        actionable = False
        
    elif input_data.rainfall_risk_category == "MEDIUM" or input_data.vulnerability_category == "MODERATE":
        level = AlertLevel.ADVISORY
        hazard = HazardNature.PREDICTED_RISK
        score = 0.30
        explanation = "Moderate rainfall or baseline vulnerability detected. Normal traffic caution advised."
        actionable = False
        
    else:
        level = AlertLevel.CLEAR
        hazard = HazardNature.OBSERVED_HAZARD if has_vision else HazardNature.PREDICTED_RISK
        score = 0.10
        explanation = "Normal conditions. No active flood evidence or elevated rainfall risk."
        actionable = False
        
    confidence_val = 0.90 if (visual_flood_confirmed or input_data.is_field_verified) else 0.70
    
    return DecisionOutput(
        location_id=input_data.location_id,
        road_name=input_data.road_name,
        alert_level=level,
        hazard_nature=hazard,
        decision_score=score,
        confidence=confidence_val,
        explanation=explanation,
        evidence_chain=evidence,
        is_actionable_for_crews=actionable,
        ruleset_version="decision_engine_rules_v1.0",
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        warnings=warnings
    )
