# Sahaay AI — Phase 6 Ground-Truth Observation Protocol

**Document Version:** 1.0.0  
**Status:** Approved Technical Specification  
**Date:** 2026-10-25  

---

## 1. Purpose and Scientific Scope

This protocol establishes the standardized, audit-proof data collection architecture required to establish legitimate ground-truth flood observations for the Hyderabad metropolitan region.

Historically, flood models have suffered from severe label noise, circular training leaks, and synthetic overconfidence. To serve as valid validation evidence, observations must be collected under strict spatio-temporal boundaries with recorded measurement uncertainties.

---

## 2. Core Observation Schema Definition

The ground-truth schema is formalized in Python under [`src/sahaay/observations/schemas.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/observations/schemas.py) and is exported in tabular format at [`data/phase6/observation_template.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/phase6/observation_template.csv).

### 2.1 Essential Schema Fields

```
+---------------------------------------------------------------------------------------------------------+
|                                    GROUND-TRUTH FIELD SPECIFICATION                                     |
+---------------------------------------------------------------------------------------------------------+
| Field Name               | Type      | Required? | Constraints & Valid Values                           |
+--------------------------+-----------+-----------+------------------------------------------------------+
| observation_id           | String    | Yes       | Regex: ^OBS-[0-9]{8}-[0-9]{4}$                       |
| start_time_utc           | DateTime  | Yes       | ISO-8601 UTC string; must not be future              |
| end_time_utc             | DateTime  | Yes       | ISO-8601 UTC string; must satisfy end >= start       |
| timezone                 | String    | Yes       | Constant "Asia/Kolkata" or "+05:30"                  |
| corridor_id              | String    | Yes       | e.g. CORR-HYD-01 to CORR-HYD-04                      |
| latitude                 | Float     | Yes       | 17.20 <= lat <= 17.60 (Hyderabad Municipal Extent)  |
| longitude                | Float     | Yes       | 78.20 <= lon <= 78.65 (Hyderabad Municipal Extent)  |
| coordinate_precision_m   | Float     | Yes       | Float in meters (e.g. 5.0, 10.0)                     |
| observer_pseudonym       | String    | Yes       | Format: OBSERVER-XXXX (PII stripped)                 |
| observation_method       | Enum      | Yes       | PHYSICAL_VANTAGE_INSPECTION, CALIBRATED_STAFF_GAUGE, |
|                          |           |           | OFFICIAL_DISPATCH_RECORD, TELEMETRY_SENSOR           |
| water_presence_extent    | Enum      | Yes       | NO_WATER, SURFACE_WETNESS_OR_PUDDLE,                 |
|                          |           |           | PARTIAL_LANE_WATERLOGGING, FULL_ROADWAY_INUNDATION,  |
|                          |           |           | UNABLE_TO_OBSERVE, INSUFFICIENT_QUALITY              |
| measured_water_depth_cm  | Float/Null| Optional  | Numeric >= 0.0 cm; required if depth measured        |
| depth_measurement_method | Enum      | Yes       | PHYSICAL_GAUGE_STAFF, CURB_REFERENCE_CALIBRATION,    |
|                          |           |           | ESTIMATED_WHEEL_SUBMERSION, NOT_MEASURED             |
| road_passability         | Enum      | Yes       | PASSABLE_ALL_VEHICLES, IMPASSABLE_TWO_WHEELERS,      |
|                          |           |           | IMPASSABLE_LOW_SEDANS, IMPASSABLE_ALL_LIGHT_VEHICLES, |
|                          |           |           | TOTALLY_IMPASSABLE, UNKNOWN                          |
| rainfall_source          | String    | Yes       | e.g. TSDPS_AWS_BEGUMPET, MANUAL_GAUGE                |
| rainfall_source_timestamp| DateTime  | Yes       | ISO-8601 UTC observation timestamp of rain gauge     |
| image_reference          | String    | Optional  | Path to privacy-redacted image file                  |
| quality_flags            | String    | Yes       | Comma-separated: NONE, VIEW_OBSTRUCTED, etc.         |
| verification_status      | Enum      | Yes       | DRAFT, SUPERVISOR_VERIFIED, REJECTED, EXPIRED        |
| verifier_timestamp_utc   | DateTime  | Optional  | Required if verification_status == VERIFIED          |
| related_incident_id      | String    | Optional  | Link to GHMC dispatch ticket or citizen report       |
| consent_and_privacy_stat | Enum      | Yes       | DPDP_CONSENT_GRANTED_REDACTED, EXEMPT_RESEARCH_PUBLIC |
| retention_policy_months  | Integer   | Yes       | Retention duration (e.g. 36)                          |
+---------------------------------------------------------------------------------------------------------+
```

---

## 3. Verification & Quality Assurance Lifecycle

```
+--------------------------------------------------------------------------------------------------+
|                                    VERIFICATION LIFECYCLE                                        |
+--------------------------------------------------------------------------------------------------+
|                                                                                                  |
|   [OBSERVER ENTRY]                                                                               |
|          |                                                                                       |
|          v                                                                                       |
|   STATUS: DRAFT                                                                                  |
|          |                                                                                       |
|          +--> Automated Ingestion Validation (Schema, CRS, Future-date, Depth bounds)            |
|          |          |                                                                            |
|          |          +--> [FAILS VALIDATION] ----> STATUS: REJECTED (Reason logged)               |
|          |                                                                                       |
|          +--> [PASSES VALIDATION]                                                                |
|                     |                                                                            |
|                     v                                                                            |
|   STATUS: PENDING_SUPERVISOR_REVIEW                                                              |
|                     |                                                                            |
|                     +--> Supervisor verifies:                                                    |
|                     |    - Telephoto image confirms curb/depth reading                           |
|                     |    - Contemporaneous radar/AWS confirms active storm                       |
|                     |    - Cross-check against peer observer logs (Zero conflict)                |
|                     |                                                                            |
|                     v                                                                            |
|   STATUS: SUPERVISOR_VERIFIED (Stamped with Verifier Role & Timestamp)                          |
|                     |                                                                            |
|                     v                                                                            |
|   [ANALYSIS-READY GROUND-TRUTH VAULT]                                                            |
|                                                                                                  |
+--------------------------------------------------------------------------------------------------+
```

---

## 4. Distinguishing Real Field Data from Synthetic Fixtures

To ensure synthetic or simulated data never contaminates scientific ground truth:
1. **Filename & Header Marking:** All synthetic fixtures must reside in `data/phase6/review_fixtures/` or `data/phase5_demo/` and contain the key `"is_synthetic_or_simulated": true`.
2. **Observation ID Prefix:** Field observations must use the prefix `OBS-`. Synthetic fixtures must use `SIM-` or `FIXTURE-`.
3. **Ingestion Gate Rejection:** The production ingestion pipeline will reject any file marked `is_synthetic_or_simulated: true` from entering the verified ground-truth repository.
