# Sahaay AI — Phase 6 Data Access & Institutional Permission Tracker

**Document Version:** 1.0.0  
**Phase:** 6 (Field-Pilot Readiness & Ground-Truth Protocol)  
**Date:** 2026-10-25  
**Compliance Standard:** Digital Personal Data Protection (DPDP) Act 2023 / Open Government Data (OGD) Framework  

---

## 1. Overview and Operational Integrity Policy

Sahaay AI requires multi-modal data streams to evaluate flood risk, road vulnerability, and real-time inundation. However, operational readiness demands complete transparency regarding what data feeds are genuinely authorized, what feeds are pending approval, and what feeds remain unavailable.

### Strict Governance Principles:
1. **Zero Fabricated Authorizations:** No agreement is recorded as approved or active without an official executed MoU, Government Order (G.O.), or countersigned data-sharing contract.
2. **Zero Credentials in Code:** API keys, access tokens, SFTP credentials, and internal passwords must never be committed to Git.
3. **Quarantine Before Authorization:** Unapproved or unverified feeds are programmatically quarantined and disabled in adapter registries.
4. **No Autonomous External Commitments:** Engineering agents and researchers may not contact agencies or submit binding applications without formal authorization from the Project Principal Investigator.

---

## 2. Institutional Feeds Audit & Permission Matrix

The master tracking register is maintained at [`data/phase6/permission_register.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/phase6/permission_register.csv). Below is the comprehensive status of all seven candidate sources.

```
+---------------------------------------------------------------------------------------------------------+
|                                    DATA ACCESS PERMISSION STATUS                                        |
+---------------------------------------------------------------------------------------------------------+
| Source ID | Source Name               | Agency            | Status                                      |
+-----------+---------------------------+-------------------+---------------------------------------------+
| SRC-01    | TSDPS AWS Telemetry       | TSDPS             | PENDING_INSTITUTIONAL_APPROVAL             |
| SRC-02    | GHMC DRF Incident Logs    | GHMC DM Wing      | REQUEST_NOT_SUBMITTED                       |
| SRC-03    | Municipal & Traffic CCTV  | HTP / GHMC CCC    | PENDING_INSTITUTIONAL_APPROVAL (QUARANTINED)|
| SRC-04    | Citizen-Submitted Reports | Registered Users  | INTERNAL_PROTOCOL_PENDING_SAFETY_CLEARANCE  |
| SRC-05    | Supervised Field Obs.     | Sahaay Field Team | INTERNAL_PROTOCOL_PENDING_SAFETY_CLEARANCE  |
| SRC-06    | Water-Depth Sensors       | Irrigation / GHMC | REQUEST_NOT_SUBMITTED                       |
| SRC-07    | DEM & Drainage GIS Layers | TRAC / GHMC       | NO_COMMERCIAL_LICENSE_IDENTIFIED            |
+---------------------------------------------------------------------------------------------------------+
```

---

## 3. Detailed Data Source Dossiers

### 3.1 SRC-01: TSDPS Automatic Weather Stations (AWS)
- **Responsible Organization:** Telangana State Development Planning Society (TSDPS), Planning Department, Government of Telangana.
- **Data Required:** 15-minute and 1-hour cumulative precipitation (mm), ambient temperature, relative humidity across ~100 urban telemetry stations within GHMC.
- **Intended Purpose:** Near-real-time environmental runoff modeling and rainfall rate-of-rise threshold calibration.
- **Request Status:** `PENDING_INSTITUTIONAL_APPROVAL`
- **Authorization Evidence:** None granted (`NONE_GRANTED`).
- **Access Method & Auth:** Secure HTTPS REST endpoint requiring an API Bearer token issued by TSDPS data administrators.
- **Permitted Use & Retention:** Non-commercial public safety research; maximum 36-month local cache; redistribution of raw station streams prohibited.
- **Known Limitations:**
  - High reporting latency during heavy convective storms (30 to 180-minute delay).
  - Tipping-bucket rain gauges are prone to under-measurement during intense downpours ($> 50\text{ mm/hr}$).
  - Station density (~2–4 km spacing) does not capture localized cloudbursts occurring between stations.
- **Next Action & Owner:** Submit formal research requisition packet to TSDPS Member Secretary. Accountable Owner: **Project Principal Investigator**.

### 3.2 SRC-02: GHMC Disaster Response Force (DRF) Incident Logs
- **Responsible Organization:** Greater Hyderabad Municipal Corporation (GHMC), Disaster Management Wing & Emergency Operations Centre.
- **Data Required:** Timestamped waterlogging dispatch tickets, static pump operations logs, water clearance completion records, road closure logs.
- **Intended Purpose:** Historical validation of waterlogging recurrence and ground-truth corroboration of citizen distress calls.
- **Request Status:** `REQUEST_NOT_SUBMITTED`
- **Authorization Evidence:** None granted (`NONE_GRANTED`).
- **Access Method & Auth:** Daily CSV export or secure SFTP drop from internal GHMC Disaster Management portal.
- **Permitted Use & Retention:** Strictly internal research; mandatory scrubbing of caller phone numbers and personal names; 24-month retention.
- **Known Limitations:**
  - Call logs are heavily biased toward high-traffic arterial routes and VIP VIP zones.
  - Substantial time lag (30–90 min) between initial citizen call and official DRF dispatch logging.
- **Next Action & Owner:** Draft formal data-sharing request for the GHMC Commissioner and Director, Disaster Management. Accountable Owner: **Legal & Compliance Lead**.

### 3.3 SRC-03: Hyderabad Traffic Police & GHMC CCTV Network
- **Responsible Organization:** Hyderabad Traffic Police (HTP) / GHMC Command & Control Centre (CCC).
- **Data Required:** Live video stream access at key flood-prone junctions across 4 candidate pilot corridors.
- **Intended Purpose:** Optical confirmation of standing water and validation of vehicle impassability.
- **Request Status:** `PENDING_INSTITUTIONAL_APPROVAL`
- **Authorization Evidence:** None granted (`NONE_GRANTED`).
- **Access Method & Auth:** RTSP/HLS streams via IP-whitelisted VPN tunnel with TLS mutual certificate authentication.
- **Permitted Use & Retention:** Restricted to real-time optical analysis; on-edge blurring of faces and vehicle registration plates; zero public distribution of raw video; 30-day rolling buffer.
- **Known Limitations:**
  - Optical degradation during monsoon rains (lens water droplets, fogging, headlight flare).
  - Camera Pan-Tilt-Zoom shifts alter focal geometry.
  - **CRITICAL GATE:** Scientifically blocked from the live operational path under the **Vision V4 NO-GO readiness gate**.
- **Next Action & Owner:** Complete Data Protection Impact Assessment (DPIA) under the DPDP Act 2023 for pilot junction cameras. Accountable Owner: **Vision Safety Lead & Legal Counsel**.

### 3.4 SRC-04: Citizen-Submitted Reports & Geotagged Imagery
- **Responsible Organization:** Registered Hyderabad Residents / Public Community Contributors.
- **Data Required:** Geocoordinates, submission timestamp, observed water depth category, passability rubric, optional contextual photo.
- **Intended Purpose:** Real-time crowdsourced flood corroboration and community alert verification.
- **Request Status:** `INTERNAL_PROTOCOL_PENDING_SAFETY_CLEARANCE`
- **Authorization Evidence:** Internal drafting complete; awaiting public staging deployment.
- **Access Method & Auth:** HTTPS POST via Sahaay Mobile/Web App with reCAPTCHA v3 and device integrity validation.
- **Permitted Use & Retention:** DPDP Act compliant; 3-decimal coordinate coarsening ($\sim 110\text{ m}$ precision); SHA-256 identity masking; right-to-erasure support within 14 days; 12-month retention.
- **Known Limitations:**
  - High false-positive rate from unverified users; spatial clustering around tech corridors; daylight bias.
- **Next Action & Owner:** Deploy public Terms of Service and Privacy Notice on staging portal for legal review. Accountable Owner: **Legal & Compliance Lead**.

### 3.5 SRC-05: Supervised Field-Team Observations
- **Responsible Organization:** Sahaay AI Field Engineering & Research Team.
- **Data Required:** Systematic ground-truth observations from designated safe pedestrian vantage points; water depth measurements with calibrated staff gauges; traffic passability classification.
- **Intended Purpose:** Primary empirical ground-truth baseline for model and decision engine validation.
- **Request Status:** `INTERNAL_PROTOCOL_PENDING_SAFETY_CLEARANCE`
- **Authorization Evidence:** Protocol authored in Phase 6; pending site safety check and PPE procurement.
- **Access Method & Auth:** Dedicated field tablet tool with cryptographically signed local records (Ed25519) and offline-first SQLite sync.
- **Permitted Use & Retention:** Open-science anonymized benchmark dataset; strict prohibition against capturing identifiable private properties.
- **Known Limitations:**
  - Restricted strictly to daytime hours and safe pedestrian vantage points.
  - Zero entry into floodwater or active vehicular lanes allowed.
- **Next Action & Owner:** Perform daytime physical site hazard checks across candidate corridors; procure calibrated fiberglass staff gauges and PPE gear. Accountable Owner: **Field Operations Lead**.

### 3.6 SRC-06: Municipal & Irrigation Water-Depth Telemetry
- **Responsible Organization:** Telangana Irrigation & CAD Department / GHMC Stormwater Drainage Wing.
- **Data Required:** Ultrasonic/radar water-level sensor telemetry at major stormwater nala outfalls (e.g. Balkapur, Picket, Shahhatem nalas).
- **Intended Purpose:** Automated, hazard-free ground-truth water depth measurements.
- **Request Status:** `REQUEST_NOT_SUBMITTED`
- **Authorization Evidence:** None granted (`NONE_GRANTED`).
- **Access Method & Auth:** MQTT telemetry topic or REST API.
- **Known Limitations:**
  - Extremely sparse deployment (under 15 active urban nala gauges across the entire metropolitan area).
  - Debris and solid waste build-up on sensors causes false high-level spikes.
- **Next Action & Owner:** Conduct census of physical sensor locations across GHMC to determine if any gauges coincide with pilot corridors. Accountable Owner: **Hydrology Data Lead**.

### 3.7 SRC-07: Hyderabad DEM & Stormwater Drainage GIS Layers
- **Responsible Organization:** Telangana State Remote Sensing Applications Centre (TRAC) / GHMC Town Planning.
- **Data Required:** High-resolution Digital Elevation Model ($\le 5\text{ m}$ spatial resolution) and comprehensive vector stormwater conduit shapefiles.
- **Intended Purpose:** Micro-topographic depression modeling and physical road susceptibility scoring.
- **Request Status:** `NO_COMMERCIAL_LICENSE_IDENTIFIED`
- **Authorization Evidence:** None granted (`NONE_GRANTED`).
- **Access Method & Auth:** Institutional offline GeoPackage / GeoTIFF delivery.
- **Known Limitations:**
  - Public open DEMs (SRTM 30m, AW3D30) have $\pm 5\text{ m}$ to $\pm 10\text{ m}$ vertical error, insufficient for urban curb-level waterlogging analysis.
  - Existing municipal GIS shapefiles frequently omit informal underground culverts.
- **Next Action & Owner:** Submit formal academic research request to TRAC Director for CartoDEM/LIDAR derivatives. Accountable Owner: **Geospatial Data Lead**.

---

## 4. Overall Data Access Gate Status

**Current Status: `NOT_READY_BLOCKED`**

No live operational pilot may be initiated until at least **SRC-01 (TSDPS)** or **SRC-05 (Field Observations)** achieves formal approval and safety clearance. Until then, all system operations run strictly under synthetic demonstration mode, historical replay, or sandbox operator review.
