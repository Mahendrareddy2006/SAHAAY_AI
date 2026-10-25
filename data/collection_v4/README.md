# Sahaay AI — Vision V4 Field Collection Repository (`data/collection_v4/`)

## 1. Directory Purpose & Scope
This directory houses the data acquisition registries, annotation manifests, and provenance tracking records for **Phase 2: Hyderabad Field Data Acquisition, Consent, and Annotation Pipeline**.

> [!IMPORTANT]
> **Operational Data Status**:
> As of Phase 2 initialization, **no real-world municipal or citizen imagery has been captured or committed to this repository**.
> All location entries in documentation are candidate corridors pending formal approval.
> Any records in `acquisition_register.csv` prefixed with `SYNTHETIC-EX-` are purely synthetic demonstration fixtures designed for software schema validation and automated test execution. They must NEVER be passed as training or evaluation evidence.

---

## 2. Directory Structure

```
data/collection_v4/
├── acquisition_register.csv       # Master acquisition register tracking legal provenance & capture metadata
├── annotation_template.csv        # Blank standardized annotation template for dual-annotator workflows
├── README.md                      # Operational guidelines and schema documentation (this file)
├── raw/                           # [Restricted/Vaulted] Raw ingested assets (git-ignored, access-controlled)
└── processed_privacy/             # Anonymized derivatives (faces and license plates blurred)
```

---

## 3. Register Schema Specification (`acquisition_register.csv`)

Every prospective or ingested image record must track the following 21 fields:

| Field Name | Type / Enum | Description | Validation Rule |
| :--- | :--- | :--- | :--- |
| `acquisition_id` | String | Unique acquisition ID (`ACQ-HYD-YYYY-XXXXX` or `SYNTHETIC-EX-XXX`) | Required, Primary Key |
| `location_id` | String | Candidate corridor foreign key (`HYD-LOC-001` to `HYD-LOC-020`) | Must match verified candidate ID |
| `capture_timestamp` | ISO 8601 UTC | Exact capture time (`YYYY-MM-DDTHH:MM:SSZ`) | Valid UTC timestamp |
| `source_type` | Enum | `municipal_cctv`, `citizen_upload`, `field_team_vantage`, `commercial_dashcam` | Required enum |
| `source_owner` | String | Pseudonymous or institutional contributor ID | Required |
| `permission_status` | Enum | `pending`, `approved`, `rejected`, `unknown` | Strict enum |
| `consent_or_authorization_reference` | String | MOU reference number, IRB protocol ID, or Terms agreement hash | Mandatory if `approved` |
| `capture_method` | Enum | `fixed_cctv`, `smartphone_rear`, `dslr_tripod`, `dashcam_forward` | Required enum |
| `camera_or_device_id_pseudonymous` | String | Pseudonymous hardware token to monitor camera-specific shortcut bias | Required |
| `latitude` | Float (WGS84) | Decimal latitude (17.20 to 17.60 for Hyderabad urban area) | Bounded |
| `longitude` | Float (WGS84) | Decimal longitude (78.20 to 78.70 for Hyderabad urban area) | Bounded |
| `location_precision_m` | Float | Geocoding or GPS uncertainty radius in meters | Positive float |
| `weather_condition` | Enum | `clear`, `overcast`, `light_rain`, `heavy_rain`, `torrential_downpour` | Required enum |
| `lighting_condition` | Enum | `daylight`, `twilight_dusk`, `twilight_dawn`, `night_streetlights`, `night_unlit` | Required enum |
| `road_surface_condition` | Enum | `dry`, `wet_sheen`, `wet_puddles_potholes`, `inundated_shallow`, `inundated_deep` | Matched condition target |
| `image_or_clip_reference` | Path / URI | Relative path to preserved image asset | Must exist on disk if processed |
| `annotation_status` | Enum | `unassigned`, `in_progress`, `dual_annotated`, `adjudicated` | Tracking status |
| `review_status` | Enum | `pending`, `approved`, `rejected_quality`, `rejected_safety` | Quality gate status |
| `privacy_processing_status` | Enum | `unprocessed`, `blurred_verified`, `quarantined_pii` | Mandatory for model eligibility |
| `retention_expiry` | ISO 8601 Date | Scheduled purge / review date (maximum 36 months from capture) | Required |
| `exclusion_reason` | String | Reason code if excluded from training eligibility | `none` or explicit reason |

---

## 4. Privacy Vaulting & Security Procedures

1. **Isolation of Raw Assets**:
   Raw imagery may contain unblurred faces or license plates. Raw assets stored in `data/collection_v4/raw/` are excluded from version control (`.gitignore`) and encrypted at rest.
2. **Eligibility Precondition**:
   An image can ONLY be added to an eligible training or evaluation manifest if:
   - `permission_status == "approved"`
   - `privacy_processing_status == "blurred_verified"`
   - `review_status == "approved"`
   - `exclusion_reason == "none"`
3. **Audit Trail**:
   Any excluded record is assigned an auditable exclusion code (e.g., `unauthorized_source`, `privacy_noncompliant`, `quality_blur_failure`) and recorded in machine-readable exclusion reports.
