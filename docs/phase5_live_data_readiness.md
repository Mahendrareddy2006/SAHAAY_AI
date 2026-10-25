# Sahaay AI — Phase 5 Live Data Readiness & Adapter Boundary Architecture

## 1. Objective & Operational Safeguards

To prevent brittle external dependencies, intellectual property violations, or misleading claims of "live" intelligence, Sahaay AI enforces strict adapter boundaries for all external hydrological, meteorological, municipal, and optical feeds.

### 1.1 Core Principles
1. **Zero Secret Leakage**: No private API keys, bearer tokens, or institutional passwords are embedded in source code or committed to git.
2. **Zero Unauthenticated Scraping**: The platform does **not** scrape restricted government portals or unauthorized web endpoints.
3. **Truthful Stream Representation**: Historical datasets and scenario fixtures are **never** presented as real-time observations.
4. **Resilient Fallback Mandate**: If an external stream experiences an outage, exceeds freshness limits, or returns malformed records, the adapter must transition to safe offline fallback or return an explicit `UNKNOWN` state—**never** silently assuming zero rainfall or declaring safety.

---

## 2. External Feed Inventory & Authorization Status

| Stream Identifier | Organization / Agency | Modality | Authorization Status | Live Connected? | Operational Mode |
| :--- | :--- | :--- | :---: | :---: | :--- |
| **`TSDPS-URBAN-AWS`** | Telangana State Development Planning Society | Urban Weather Stations | `PENDING_APPROVAL` | No | Standby benchmark fixture fallback |
| **`NWIC-TELEMETRY-GAUGE`** | National Water Informatics Centre / NWDP | Reservoir & River Gauges | `HISTORICAL_PLAYBACK_ONLY` | No | QC-filtered historical telemetry playback |
| **`GHMC-DRF-DISPATCH`** | GHMC Disaster Response Force | Incident Dispatch Logs | `PENDING_APPROVAL` | No | Authorized drill scenario buffer |
| **`MUNICIPAL-CCTV-STREAM`** | GHMC ICCC / Hyderabad Traffic Police | Video Feeds | `QUARANTINED_DISABLED` | No | **Quarantined** under Vision V4 readiness gate |

---

## 3. Adapter Implementation Details

### 3.1 TSDPS Urban Automatic Weather Stations (`TSDPSWeatherAdapter`)
- **Coverage**: Urban AWS network across Hyderabad core zones (e.g., Khairatabad, Shaikpet, Charminar, Jubilee Hills).
- **Access Status**: `PENDING_APPROVAL`. State department secure REST API gateway requires formal institutional data access credentials.
- **Data Quality Safeguards**:
  - Automatically checks for cumulative bucket gauge accumulators ($> 250\text{ mm/hr}$).
  - Automatically filters negative electrical disconnect readings ($< 0.0\text{ mm}$).
- **Fallback Behavior**:
  - In production without credentials: returns `data_available: false` with reason `CREDENTIALS_PENDING_APPROVAL`.
  - In evaluation mode: provides safe offline dry-weather benchmark.

### 3.2 NWIC Telemetry Gauge (`NWICRainfallAdapter`)
- **Coverage**: 38 stations across Telangana catchment basins ($2021\text{--}2025$).
- **Access Status**: `HISTORICAL_PLAYBACK_ONLY`. Ingests verified open telemetry dataset with QC flags.
- **Handling of Outages & Gaps**:
  - Enforces non-silent missingness rule: missing hours are **never** treated as zero rainfall.
  - Telemetry freshness is explicitly computed; observations $> 3.0\text{ hours}$ old are marked `is_stale: true`.
  - Regional distance penalty is applied for stations $> 15\text{ km}$ away.

### 3.3 GHMC DRF Incident Dispatch (`GHMCDRFIncidentAdapter`)
- **Coverage**: Municipal flood control room incident logs and suction pump deployment dispatches.
- **Access Status**: `PENDING_APPROVAL`. Direct electronic access to municipal dispatch systems is restricted.
- **Operational Policy**:
  - System operates in safe offline standby mode until municipal data-sharing MOU is executed.
  - Supports controlled injection of authorized municipal drill fixtures for training and scenario evaluation.

### 3.4 Municipal CCTV Surveillance (`MunicipalCCTVAdapter`)
- **Coverage**: Arterial intersection cameras under GHMC ICCC and Hyderabad Traffic Police.
- **Access Status**: **`QUARANTINED_DISABLED`**.
- **Non-Negotiable Vision V4 Gate**:
  - In accordance with Phase 3 & Phase 4 Vision integrity policies, this adapter is quarantined.
  - Zero live CCTV video streams are ingested into production until formal written MOU execution and automated privacy redaction (face and license plate blurring) are legally verified.

---

## 4. Machine-Readable Audit

The live source status is continuously auditable via:
- Report: [`reports/phase5/live_data_source_status.json`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/phase5/live_data_source_status.json)
- Programmatic API: `LiveDataAdapterRegistry.generate_source_status_report()`
