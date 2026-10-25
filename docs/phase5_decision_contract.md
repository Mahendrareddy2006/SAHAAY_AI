# Sahaay AI — Phase 5 Unified Flood Intelligence Response Contract

## 1. Specification Overview

The Unified Flood Intelligence Contract defines the canonical data schema returned by the Sahaay AI Decision Engine for corridor evaluations, live map feeds, and emergency response dashboards.

### 1.1 Core Enumerations

#### `AlertLevel`
- `CLEAR`: Normal conditions. No current flood observations and dry to light baseline rainfall.
- `ADVISORY`: Heightened vigilance advised due to moderate environmental risk, unverified citizen submissions, or aging observations.
- `WATCH`: Severe waterlogging anticipated within 1–3 hours due to heavy rainfall on a chronically vulnerable corridor (predictive environmental risk).
- `WARNING`: High waterlogging confirmed by verified visual evidence or corroborated real-time reports. Actionable for municipal response crews.
- `EMERGENCY`: Severe inundation confirmed by verified observation and corroborated by critical rainfall or on-site field responders. Immediate life/asset safety hazard.

#### `DecisionStatus`
- `EVALUATED`: High-integrity decision reached using valid, fresh multi-source inputs.
- `INSUFFICIENT_DATA`: Primary required data (e.g., rainfall observation or corridor GIS profile) is completely missing; decision cannot be authoritatively established.
- `STALE_DATA`: Telemetry or report observations have exceeded maximum freshness thresholds ($> 3\text{--}6\text{ hours}$); confidence is severely decayed.
- `INCONCLUSIVE_CONTRADICTORY`: Conflicting multi-source observations exist (e.g., citizen report asserts flooding while contemporaneous verified optical vantage shows dry pavement).

#### `CurrentFloodEvidenceStatus`
1. **`OBSERVED_FLOOD_EVIDENCE`**: Supported by an authentic, verified, timestamped citizen report, CCTV feed, or field responder observation.
2. **`ELEVATED_ENVIRONMENTAL_RISK`**: Regional rainfall accumulation and static catchment vulnerability justify high caution, but **current road inundation has not been confirmed**.
3. **`NO_CURRENT_EVIDENCE_AVAILABLE`**: No qualifying recent optical or ground report is available. **Crucially: this is NOT a declaration that the road is safe or passable.**
4. **`INCONCLUSIVE`**: Available evidence is contradictory, degraded by optical glare/neon reflections, or fails the automated image quality gate.
5. **`INSUFFICIENT_OR_STALE_DATA`**: Data feeds are offline or too stale to support an evaluation.

---

## 2. Canonical JSON Schema (`UnifiedCorridorEvaluationResponse`)

```json
{
  "corridor_id": "HYD-LOC-001",
  "corridor_name": "Tolichowki Flyover Underpass",
  "evaluated_at": "2026-10-25T11:30:00Z",
  "alert_level": "WATCH",
  "decision_status": "EVALUATED",
  "environmental_risk_category": "HIGH",
  "road_vulnerability_category": "HIGH",
  "current_flood_evidence_status": "ELEVATED_ENVIRONMENTAL_RISK",
  "decision_score": 0.75,
  "confidence": 0.65,
  "requires_human_verification": true,
  "reason_codes": [
    "IMD_HEAVY_INTENSITY_EXCEEDED",
    "CHRONIC_WATERLOGGING_HOTSPOT_PROXIMITY",
    "STATION_DISTANCE_DISCOUNTED_51KM"
  ],
  "supporting_evidence": [
    "Heavy rainfall intensity: 25.0 mm/hr detected at Kondapochamma AWS",
    "Baseline susceptibility: High vulnerability index (0.53) due to 120m proximity to Galaxy Tolichowki hotspot",
    "No verified ground optical report received in the last 60 minutes"
  ],
  "missing_inputs": [],
  "stale_inputs": [],
  "source_timestamps": {
    "telemetry_rainfall": "2026-10-25T11:00:00Z",
    "gis_vulnerability": "2026-10-25T10:30:00Z",
    "citizen_reports": null,
    "vision_cctv": null
  },
  "model_or_rule_versions": {
    "decision_rules": "decision_engine_rules_v2.0",
    "rainfall_engine": "hyderabad_rainfall_risk_v1.0",
    "vulnerability_engine": "hyderabad_road_vulnerability_v1.0",
    "vision_inference": "advisory_quality_gate_v4.0"
  },
  "warnings": [
    "Decision Engine advisory: Preserves uncertainty and separates observed from predicted risk.",
    "Not an official municipal evacuation directive. Autonomous road closures prohibited."
  ]
}
```

---

## 3. Concrete JSON Examples for the Five Evidence Statuses

### Example 1: `OBSERVED_FLOOD_EVIDENCE`
```json
{
  "corridor_id": "HYD-LOC-005",
  "corridor_name": "Malakpet Railway Underbridge",
  "evaluated_at": "2026-10-25T11:30:00Z",
  "alert_level": "WARNING",
  "decision_status": "EVALUATED",
  "environmental_risk_category": "MEDIUM",
  "road_vulnerability_category": "HIGH",
  "current_flood_evidence_status": "OBSERVED_FLOOD_EVIDENCE",
  "decision_score": 0.88,
  "confidence": 0.92,
  "requires_human_verification": false,
  "reason_codes": [
    "VERIFIED_FIELD_RESPONDER_INUNDATION",
    "MODERATE_RAINFALL_CORROBORATION"
  ],
  "supporting_evidence": [
    "Verified field responder report confirmed 45 cm standing water at Malakpet RUB subway approach",
    "Observation timestamp: 2026-10-25T11:20:00Z (freshness: 10 minutes)"
  ],
  "missing_inputs": [],
  "stale_inputs": []
}
```

### Example 2: `ELEVATED_ENVIRONMENTAL_RISK`
```json
{
  "corridor_id": "HYD-LOC-002",
  "corridor_name": "Shaikpet Nala Road",
  "evaluated_at": "2026-10-25T11:30:00Z",
  "alert_level": "WATCH",
  "decision_status": "EVALUATED",
  "environmental_risk_category": "CRITICAL",
  "road_vulnerability_category": "MODERATE",
  "current_flood_evidence_status": "ELEVATED_ENVIRONMENTAL_RISK",
  "decision_score": 0.78,
  "confidence": 0.62,
  "requires_human_verification": true,
  "reason_codes": [
    "IMD_VERY_HEAVY_INTENSITY_EXCEEDED",
    "ROLLING_3H_FLASH_SURGE",
    "OPEN_NALA_BUFFER_PROXIMITY"
  ],
  "supporting_evidence": [
    "Extreme rainfall detected: 42.0 mm/hr and 68.0 mm over 3 hours",
    "Road segment located 65m from Shaikpet open nala drainage link",
    "Notice: Road is not confirmed flooded now; elevated environmental flash risk active"
  ],
  "missing_inputs": [],
  "stale_inputs": []
}
```

### Example 3: `NO_CURRENT_EVIDENCE_AVAILABLE`
```json
{
  "corridor_id": "HYD-LOC-011",
  "corridor_name": "Madhapur Cyber Towers Corridor",
  "evaluated_at": "2026-10-25T11:30:00Z",
  "alert_level": "CLEAR",
  "decision_status": "EVALUATED",
  "environmental_risk_category": "LOW",
  "road_vulnerability_category": "LOW",
  "current_flood_evidence_status": "NO_CURRENT_EVIDENCE_AVAILABLE",
  "decision_score": 0.08,
  "confidence": 0.70,
  "requires_human_verification": false,
  "reason_codes": [
    "DRY_WEATHER_OBSERVED",
    "NO_COMMUNITY_REPORTS_RECEIVED"
  ],
  "supporting_evidence": [
    "Rainfall telemetry reports dry conditions (0.0 mm/hr)",
    "No citizen or camera reports filed in the past 24 hours"
  ],
  "missing_inputs": [],
  "stale_inputs": []
}
```

### Example 4: `INCONCLUSIVE` (Contradictory or Degraded Evidence)
```json
{
  "corridor_id": "HYD-LOC-008",
  "corridor_name": "Lakdikapul Junction & Railway Bridge",
  "evaluated_at": "2026-10-25T11:30:00Z",
  "alert_level": "ADVISORY",
  "decision_status": "INCONCLUSIVE_CONTRADICTORY",
  "environmental_risk_category": "LOW",
  "road_vulnerability_category": "MODERATE",
  "current_flood_evidence_status": "INCONCLUSIVE",
  "decision_score": 0.40,
  "confidence": 0.35,
  "requires_human_verification": true,
  "reason_codes": [
    "CONTRADICTORY_MULTI_SOURCE_EVIDENCE",
    "OPTICAL_QUALITY_GATE_AMBIGUITY"
  ],
  "supporting_evidence": [
    "Citizen report filed claiming deep road water (freshness: 12 min)",
    "Contemporaneous optical CCTV image demonstrates specular reflection from wet asphalt without water depth",
    "Automated image quality gate flagged specular wet asphalt ambiguity (confidence 0.52)"
  ],
  "missing_inputs": [],
  "stale_inputs": []
}
```

### Example 5: `INSUFFICIENT_OR_STALE_DATA`
```json
{
  "corridor_id": "HYD-LOC-016",
  "corridor_name": "Uppal Ring Road Junction",
  "evaluated_at": "2026-10-25T11:30:00Z",
  "alert_level": "ADVISORY",
  "decision_status": "STALE_DATA",
  "environmental_risk_category": "UNKNOWN",
  "road_vulnerability_category": "MODERATE",
  "current_flood_evidence_status": "INSUFFICIENT_OR_STALE_DATA",
  "decision_score": 0.20,
  "confidence": 0.12,
  "requires_human_verification": true,
  "reason_codes": [
    "TELEMETRY_FEED_STALE_EXCEEDED_6H",
    "HOURLY_RAINFALL_OBSERVATION_MISSING"
  ],
  "supporting_evidence": [
    "Nearest telemetry station observation is 7.2 hours stale",
    "Hourly rainfall measurement unavailable; non-silent missingness rule triggered"
  ],
  "missing_inputs": ["rain_1h_mm", "rain_3h_mm"],
  "stale_inputs": ["telemetry_rainfall"]
}
```
