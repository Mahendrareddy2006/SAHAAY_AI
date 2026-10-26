"""
Sahaay AI - Hardened Decision Engine Contracts & Synthesis Rules (v2.0)
Synthesizes visual evidence, rainfall telemetry, road vulnerability, and citizen reports
into an explainable, multi-factor alert level.
"""

import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


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


class DecisionStatus(str, Enum):
    EVALUATED = "EVALUATED"                                   # Valid, high-integrity decision reached
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"                   # Primary data feeds missing
    STALE_DATA = "STALE_DATA"                                 # Primary observations expired
    INCONCLUSIVE_CONTRADICTORY = "INCONCLUSIVE_CONTRADICTORY" # Contradictory evidence detected


class CurrentFloodEvidenceStatus(str, Enum):
    OBSERVED_FLOOD_EVIDENCE = "OBSERVED_FLOOD_EVIDENCE"             # Confirmed by verified ground observation
    ELEVATED_ENVIRONMENTAL_RISK = "ELEVATED_ENVIRONMENTAL_RISK"     # Modeled risk active; inundation unproven
    NO_CURRENT_EVIDENCE_AVAILABLE = "NO_CURRENT_EVIDENCE_AVAILABLE" # No current reports; not a declaration of safety
    INCONCLUSIVE = "INCONCLUSIVE"                                   # Ambiguous or contradictory observations
    INSUFFICIENT_OR_STALE_DATA = "INSUFFICIENT_OR_STALE_DATA"       # Feeds missing or too old


class DecisionInput(BaseModel):
    location_id: str
    road_name: str
    
    # Component 1: Vision Evidence (Advisory)
    vision_predicted_class: Optional[str] = Field(None, description="'flooded', 'not_flooded', or 'inconclusive'")
    vision_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    vision_is_ambiguous: bool = False
    
    # Component 2: Rainfall Evidence
    rainfall_risk_category: str = Field("UNKNOWN", description="LOW, MEDIUM, HIGH, CRITICAL, or UNKNOWN")
    rainfall_risk_score: float = Field(0.0, ge=0.0, le=1.0)
    rainfall_proximity_tier: str = Field("UNKNOWN", description="LOCAL_URBAN, PERI_URBAN, REGIONAL_CATCHMENT, or UNKNOWN")
    rainfall_station_id: Optional[str] = None
    
    @field_validator("rainfall_risk_category")
    @classmethod
    def validate_rainfall_category(cls, v: str) -> str:
        valid_cats = {"LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"}
        if v not in valid_cats:
            raise ValueError(f"rainfall_risk_category must be one of {valid_cats}, got {v}")
        return v

    @classmethod
    def from_rainfall_result(
        cls,
        location_id: str,
        road_name: str,
        rainfall_result: Any,
        **kwargs: Any
    ) -> "DecisionInput":
        """
        Constructs DecisionInput from a RainfallRiskResult, preserving explicit UNKNOWN semantics
        and propagating station proximity tier and provenance metadata.
        Ensures missing telemetry is never silently imputed as safe zero rainfall.
        """
        cat = getattr(rainfall_result, "risk_category", "UNKNOWN")
        score = getattr(rainfall_result, "risk_score", 0.0)
        proximity_tier = getattr(rainfall_result, "station_proximity_tier", None) or kwargs.pop("rainfall_proximity_tier", "UNKNOWN")
        st_id = getattr(rainfall_result, "station_id", None) or kwargs.pop("rainfall_station_id", None)
        engine_missing = list(getattr(rainfall_result, "missing_inputs", []))
        user_missing = list(kwargs.pop("missing_inputs", []))
        combined_missing = sorted(list(set(engine_missing + user_missing)))
        return cls(
            location_id=location_id,
            road_name=road_name,
            rainfall_risk_category=cat,
            rainfall_risk_score=score,
            rainfall_proximity_tier=proximity_tier,
            rainfall_station_id=st_id,
            missing_inputs=combined_missing,
            **kwargs
        )
    
    # Component 3: Road Vulnerability Evidence
    vulnerability_category: str = Field("LOW", description="LOW, MODERATE, HIGH, SEVERE")
    vulnerability_index: float = Field(0.1, ge=0.0, le=1.0)
    
    # Component 4: Citizen / Field Reports & Provenance
    report_age_minutes: float = Field(0.0, ge=0.0, description="Minutes elapsed since report capture")
    is_field_verified: bool = False
    citizen_report_count_in_zone: int = Field(0, ge=0)
    water_depth_estimate: Optional[str] = Field(None, description="e.g. 'KNEE_DEEP', 'WAIST_DEEP_OR_MORE'")
    
    # Conflict & Data Quality Indicators
    has_contradictory_evidence: bool = False
    missing_inputs: List[str] = Field(default_factory=list)
    stale_inputs: List[str] = Field(default_factory=list)
    source_timestamps: Dict[str, Optional[str]] = Field(default_factory=dict)


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
    ruleset_version: str = "decision_engine_rules_v2.0"
    created_at: str
    warnings: List[str]
    
    # Phase 5 Unified Response Contract Fields
    decision_status: DecisionStatus = DecisionStatus.EVALUATED
    environmental_risk_category: str = "LOW"
    rainfall_proximity_tier: str = "UNKNOWN"
    road_vulnerability_category: str = "LOW"
    current_flood_evidence_status: CurrentFloodEvidenceStatus = CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE
    requires_human_verification: bool = False
    reason_codes: List[str] = Field(default_factory=list)
    supporting_evidence: List[str] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)
    stale_inputs: List[str] = Field(default_factory=list)
    source_timestamps: Dict[str, Optional[str]] = Field(default_factory=dict)
    model_or_rule_versions: Dict[str, str] = Field(default_factory=dict)


def evaluate_decision(input_data: DecisionInput) -> DecisionOutput:
    """
    Evaluates multi-source evidence using explicit, auditable rules.
    Strictly separates static vulnerability, modeled environmental risk, and observed flooding.
    Never allows missing rainfall to be interpreted as safe zero rainfall.
    Surfaces contradictory evidence rather than blind majority voting.
    """
    evidence: List[str] = []
    reason_codes: List[str] = []
    supporting_evidence: List[str] = []
    warnings: List[str] = [
        "Decision Engine advisory: Preserves uncertainty and separates observed from predicted risk.",
        "Not an official municipal NDRF/GHMC evacuation directive. Autonomous road closures prohibited."
    ]
    
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    # Default outputs
    level = AlertLevel.CLEAR
    hazard = HazardNature.PREDICTED_RISK
    dec_status = DecisionStatus.EVALUATED
    evidence_status = CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE
    score = 0.10
    confidence = 0.70
    actionable = False
    requires_human_verification = False
    
    # 1. Freshness Audit
    is_fresh = input_data.report_age_minutes <= 180.0
    if not is_fresh and input_data.report_age_minutes > 0.0:
        evidence.append(f"Data freshness decay: Report is {input_data.report_age_minutes:.0f} minutes old")
        reason_codes.append("OBSERVATION_FRESHNESS_DECAYED")

    # 2. Contradictory Evidence Audit
    # Conflict: Fresh vision claims not_flooded with high confidence, but citizen report asserts deep water
    visual_asserts_dry = (
        input_data.vision_predicted_class == "not_flooded"
        and (input_data.vision_confidence or 0.0) >= 0.75
        and not input_data.vision_is_ambiguous
    )
    report_asserts_flood = (
        input_data.water_depth_estimate in ["KNEE_DEEP", "WAIST_DEEP_OR_MORE"]
        or input_data.citizen_report_count_in_zone >= 1
    )
    
    has_conflict = input_data.has_contradictory_evidence or (visual_asserts_dry and report_asserts_flood and is_fresh)
    
    if has_conflict:
        dec_status = DecisionStatus.INCONCLUSIVE_CONTRADICTORY
        evidence_status = CurrentFloodEvidenceStatus.INCONCLUSIVE
        level = AlertLevel.ADVISORY
        hazard = HazardNature.COMMUNITY_REPORT
        score = 0.40
        confidence = 0.35
        requires_human_verification = True
        reason_codes.append("CONTRADICTORY_OBSERVATIONS_DETECTED")
        explanation = (
            "Contradictory observations detected between ground community reports and optical surveillance. "
            "Evidence is inconclusive; field verification required."
        )
        evidence.append("Contradictory evidence: Citizen submission indicates waterlogging but camera confirms dry pavement.")
        supporting_evidence.extend(evidence)
        
        return DecisionOutput(
            location_id=input_data.location_id,
            road_name=input_data.road_name,
            alert_level=level,
            hazard_nature=hazard,
            decision_score=score,
            confidence=confidence,
            explanation=explanation,
            evidence_chain=evidence,
            is_actionable_for_crews=actionable,
            ruleset_version="decision_engine_rules_v2.0",
            created_at=now_iso,
            warnings=warnings,
            decision_status=dec_status,
            environmental_risk_category=input_data.rainfall_risk_category,
            rainfall_proximity_tier=input_data.rainfall_proximity_tier,
            road_vulnerability_category=input_data.vulnerability_category,
            current_flood_evidence_status=evidence_status,
            requires_human_verification=requires_human_verification,
            reason_codes=reason_codes,
            supporting_evidence=supporting_evidence,
            missing_inputs=input_data.missing_inputs,
            stale_inputs=input_data.stale_inputs,
            source_timestamps=input_data.source_timestamps,
            model_or_rule_versions={
                "decision_rules": "decision_engine_rules_v2.0",
                "rainfall_engine": "hyderabad_rainfall_risk_v1.0",
                "vulnerability_engine": "hyderabad_road_vulnerability_v1.0",
            }
        )

    # 3. Missing Primary Rainfall Data Audit (Non-Silent Missingness)
    if input_data.rainfall_risk_category == "UNKNOWN" or "rain_1h_mm" in input_data.missing_inputs:
        dec_status = DecisionStatus.INSUFFICIENT_DATA
        evidence_status = CurrentFloodEvidenceStatus.INSUFFICIENT_OR_STALE_DATA
        level = AlertLevel.ADVISORY
        score = 0.20
        confidence = 0.15
        requires_human_verification = True
        reason_codes.append("TELEMETRY_DATA_MISSING_OR_STALE")
        reason_codes.append("MISSING_PRIMARY_RAINFALL_TELEMETRY")
        explanation = "Primary rainfall observation unavailable. Operational decision cannot be certified; normal traffic caution advised."
        evidence.append("Missing rainfall observation: Non-silent missingness rule triggered.")
        warnings.append("Absence of telemetry data must NOT be interpreted as zero rainfall.")

    # 4. Vision Evidence Processing
    has_vision = input_data.vision_predicted_class is not None
    visual_flood_confirmed = (
        has_vision
        and input_data.vision_predicted_class == "flooded"
        and not input_data.vision_is_ambiguous
        and (input_data.vision_confidence or 0.0) >= 0.70
    )
    
    if visual_flood_confirmed:
        evidence.append(f"Visual flood evidence: Inundation detected with {(input_data.vision_confidence or 0.0)*100:.1f}% confidence")
        reason_codes.append("VISUAL_INUNDATION_DETECTED")
    elif has_vision and input_data.vision_predicted_class == "not_flooded":
        evidence.append(f"Visual check: No surface inundation observed (confidence {(input_data.vision_confidence or 0.0)*100:.1f}%)")
        reason_codes.append("VISUAL_DRY_SURFACE_CHECKED")
    elif has_vision and input_data.vision_predicted_class == "inconclusive":
        evidence.append("Visual evidence inconclusive: Image failed quality gate or exhibits severe specular reflection.")
        reason_codes.append("OPTICAL_QUALITY_GATE_AMBIGUOUS")
        warnings.append("Inconclusive vision evidence cannot trigger flood claims. Field verification required.")

    # 5. Environmental & Vulnerability Factors
    if input_data.rainfall_risk_category in ["HIGH", "CRITICAL"]:
        evidence.append(f"Severe rainfall trigger: Category {input_data.rainfall_risk_category} (score {input_data.rainfall_risk_score:.2f})")
        reason_codes.append(f"RAINFALL_TRIGGER_{input_data.rainfall_risk_category}")
        
    if input_data.vulnerability_category in ["HIGH", "SEVERE"]:
        evidence.append(f"High baseline susceptibility: Road segment has {input_data.vulnerability_category} vulnerability index ({input_data.vulnerability_index:.2f})")
        reason_codes.append(f"VULNERABILITY_INDEX_{input_data.vulnerability_category}")

    # 6. Core Decision Hierarchy & Synthesis
    if visual_flood_confirmed and is_fresh:
        hazard = HazardNature.OBSERVED_HAZARD
        evidence_status = CurrentFloodEvidenceStatus.OBSERVED_FLOOD_EVIDENCE
        actionable = True
        
        # Emergency Policy: Only verified deep flood + critical local rain or on-site responder confirmation
        is_deep = input_data.water_depth_estimate in ["KNEE_DEEP", "WAIST_DEEP_OR_MORE"]
        is_local_rain = input_data.rainfall_proximity_tier in ["LOCAL_URBAN", "PERI_URBAN"]
        if (input_data.rainfall_risk_category in ["HIGH", "CRITICAL"] and is_local_rain and is_deep) or input_data.is_field_verified:
            level = AlertLevel.EMERGENCY
            score = 0.95
            confidence = 0.95
            explanation = "Confirmed deep street waterlogging verified by visual observation and corroborated by critical rainfall or field responder inspection."
            reason_codes.append("EMERGENCY_DEEP_INUNDATION_CONFIRMED")
        else:
            level = AlertLevel.WARNING
            score = 0.85
            confidence = 0.88
            explanation = "Visible street flooding identified from fresh community photo upload. Response crews notified."
            reason_codes.append("WARNING_FRESH_SURFACE_INUNDATION")
            
    elif input_data.is_field_verified and is_fresh:
        level = AlertLevel.WARNING
        hazard = HazardNature.OBSERVED_HAZARD
        evidence_status = CurrentFloodEvidenceStatus.OBSERVED_FLOOD_EVIDENCE
        score = 0.88
        confidence = 0.92
        actionable = True
        explanation = "Ground flood condition verified by municipal DRF or traffic police field inspection."
        reason_codes.append("FIELD_RESPONDER_INSPECTION_CONFIRMED")
        
    elif input_data.citizen_report_count_in_zone >= 3 and is_fresh and not input_data.has_contradictory_evidence:
        # Corroborated community reports elevate to WATCH / WARNING
        level = AlertLevel.WATCH
        hazard = HazardNature.COMMUNITY_REPORT
        evidence_status = CurrentFloodEvidenceStatus.OBSERVED_FLOOD_EVIDENCE
        score = 0.70
        confidence = 0.75
        actionable = True
        explanation = f"Multiple independent community reports ({input_data.citizen_report_count_in_zone}) corroborate active waterlogging on corridor."
        reason_codes.append("COMMUNITY_CORROBORATION_THRESHOLD_MET")

    elif input_data.rainfall_risk_category in ["HIGH", "CRITICAL"] and input_data.vulnerability_category in ["HIGH", "SEVERE"]:
        if input_data.rainfall_proximity_tier == "REGIONAL_CATCHMENT":
            # Regional catchment heavy rainfall (>35km away) does NOT establish hyper-local urban corridor inundation.
            # Actionable crew dispatch and WATCH alert are withheld in favor of qualified, non-actionable ADVISORY.
            level = AlertLevel.ADVISORY
            hazard = HazardNature.PREDICTED_RISK
            evidence_status = CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE
            score = min(0.40, input_data.rainfall_risk_score)
            confidence = 0.35
            actionable = False
            explanation = (
                f"Elevated rainfall detected at distant regional catchment station ({input_data.rainfall_station_id or 'regional watershed'}, >35km). "
                "Represents dam/reservoir catchment conditions, NOT verified hyper-local road corridor precipitation. "
                "Actionable WATCH alert withheld; normal traffic caution advised."
            )
            reason_codes.append("REGIONAL_CATCHMENT_TELEMETRY_DISCOUNTED")
            warnings.append(
                "Rainfall telemetry originates from distant regional catchment (>35km); represents watershed conditions, "
                "NOT hyper-local road corridor precipitation. Corroborated local evidence required for actionable alerts."
            )
        elif input_data.rainfall_proximity_tier == "UNKNOWN":
            # Missing or unverified station proximity cannot produce actionable local alerts based on rainfall alone.
            # Actionable crew dispatch and WATCH alert are withheld in favor of qualified, non-actionable ADVISORY.
            level = AlertLevel.ADVISORY
            hazard = HazardNature.PREDICTED_RISK
            evidence_status = CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE
            score = min(0.40, input_data.rainfall_risk_score)
            confidence = 0.35
            actionable = False
            explanation = (
                "Elevated rainfall detected, but telemetry station proximity is UNKNOWN (distance not established). "
                "Telemetry cannot be verified as hyper-local road corridor precipitation. "
                "Actionable WATCH alert withheld; normal traffic caution advised."
            )
            reason_codes.append("UNKNOWN_PROXIMITY_TELEMETRY_DISCOUNTED")
            warnings.append(
                "Rainfall telemetry has UNKNOWN proximity tier; station distance cannot be established. "
                "Cannot be treated as hyper-local road corridor precipitation. Corroborated local evidence required for actionable alerts."
            )
        else:
            # Modeled environmental risk: WATCH (Not observed flooding!)
            level = AlertLevel.WATCH
            hazard = HazardNature.PREDICTED_RISK
            evidence_status = CurrentFloodEvidenceStatus.ELEVATED_ENVIRONMENTAL_RISK
            score = 0.75
            confidence = 0.65
            actionable = True
            explanation = "High waterlogging risk anticipated over the next 1-3 hours due to heavy rainfall on a chronically vulnerable road segment."
            reason_codes.append("PREDICTED_WATERLOGGING_SURGE_ANTICIPATED")
            warnings.append("Elevated environmental risk active. Road is NOT confirmed flooded now.")

    elif input_data.citizen_report_count_in_zone >= 1 and is_fresh:
        # Single unverified report -> ADVISORY
        level = AlertLevel.ADVISORY
        hazard = HazardNature.COMMUNITY_REPORT
        evidence_status = CurrentFloodEvidenceStatus.INCONCLUSIVE
        score = 0.45
        confidence = 0.50
        actionable = False
        requires_human_verification = True
        explanation = "Unverified citizen report received. Requires field dispatch or independent corroboration."
        reason_codes.append("UNVERIFIED_COMMUNITY_SUBMISSION")

    elif dec_status == DecisionStatus.INSUFFICIENT_DATA:
        # Preserve INSUFFICIENT_OR_STALE_DATA status from step 3
        level = AlertLevel.ADVISORY
        hazard = HazardNature.PREDICTED_RISK
        evidence_status = CurrentFloodEvidenceStatus.INSUFFICIENT_OR_STALE_DATA
        score = 0.20
        confidence = 0.15
        actionable = False
        requires_human_verification = True

    elif input_data.rainfall_risk_category == "MEDIUM":
        level = AlertLevel.ADVISORY
        hazard = HazardNature.PREDICTED_RISK
        evidence_status = CurrentFloodEvidenceStatus.ELEVATED_ENVIRONMENTAL_RISK
        score = 0.30
        confidence = 0.60
        actionable = False
        explanation = "Moderate rainfall detected. Normal traffic caution advised."
        reason_codes.append("MODERATE_ENVIRONMENTAL_VIGILANCE")

    elif input_data.vulnerability_category in ["HIGH", "SEVERE"] and input_data.rainfall_risk_category != "LOW":
        level = AlertLevel.ADVISORY
        hazard = HazardNature.PREDICTED_RISK
        evidence_status = CurrentFloodEvidenceStatus.ELEVATED_ENVIRONMENTAL_RISK
        score = 0.30
        confidence = 0.60
        actionable = False
        explanation = "High baseline susceptibility under active weather conditions. Normal traffic caution advised."
        reason_codes.append("MODERATE_ENVIRONMENTAL_VIGILANCE")

    elif dec_status != DecisionStatus.INSUFFICIENT_DATA:
        level = AlertLevel.CLEAR
        hazard = HazardNature.PREDICTED_RISK
        evidence_status = CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE
        score = 0.10
        confidence = 0.70
        actionable = False
        explanation = "Normal conditions. No active flood evidence or elevated rainfall risk."
        reason_codes.append("NORMAL_DRY_BASELINE")

    supporting_evidence = list(evidence)

    return DecisionOutput(
        location_id=input_data.location_id,
        road_name=input_data.road_name,
        alert_level=level,
        hazard_nature=hazard,
        decision_score=score,
        confidence=confidence,
        explanation=explanation,
        evidence_chain=evidence,
        is_actionable_for_crews=actionable,
        ruleset_version="decision_engine_rules_v2.0",
        created_at=now_iso,
        warnings=warnings,
        decision_status=dec_status,
        environmental_risk_category=input_data.rainfall_risk_category,
        rainfall_proximity_tier=input_data.rainfall_proximity_tier,
        road_vulnerability_category=input_data.vulnerability_category,
        current_flood_evidence_status=evidence_status,
        requires_human_verification=requires_human_verification,
        reason_codes=reason_codes,
        supporting_evidence=supporting_evidence,
        missing_inputs=input_data.missing_inputs,
        stale_inputs=input_data.stale_inputs,
        source_timestamps=input_data.source_timestamps,
        model_or_rule_versions={
            "decision_rules": "decision_engine_rules_v2.0",
            "rainfall_engine": "hyderabad_rainfall_risk_v1.0",
            "vulnerability_engine": "hyderabad_road_vulnerability_v1.0",
            "vision_inference": "advisory_quality_gate_v4.0"
        }
    )
