# Sahaay AI — Phase 7 Field Observation Session Runbook

**Document Version:** 1.0.0  
**Phase:** 7 (Pilot Activation Gate & Operational Validation)  
**Date:** 2026-10-25  
**Audience:** Field Operations Lead, Safety Officer, Data Recorder  

---

## 1. Operational Mandates for Field Sessions

Every ground-truth observation deployment is managed as an auditable **Field Session** with a unique identifier (`SES-YYYYMMDD-XXXX`).

### Rules of Engagement:
1. **Activation Gate Precondition:** A real field session can **only** be activated if the system is in state `PILOT_AUTHORIZED`. Attempting to start a session while the gate is `BLOCKED` will fail.
2. **On-Site Safety Check:** Prior to starting observations, the Field Lead and Safety Officer must conduct a physical hazard check at the vantage point.
3. **Cardinal Life-Safety Boundary:**
   - **ZERO entry into floodwater or active carriageways.**
   - All observations are conducted from elevated, permanent pedestrian walkways.
4. **Immediate Abort Conditions:**
   - Lightning strikes within $10\text{ km}$
   - Wind gusts $> 35\text{ km/h}$
   - Water rising toward pedestrian walkway ($< 30\text{ cm}$ freeboard)
   - Railing instability, crowd hostility, or traffic diversion onto sidewalks

---

## 2. Session Lifecycle & State Machine

```
+--------------------------------------------------------------------------------------------------+
|                                    FIELD SESSION LIFECYCLE                                       |
+--------------------------------------------------------------------------------------------------+
|                                                                                                  |
|   1. INITIALIZATION (`INITIALIZED`)                                                              |
|      - Base camp schedules session: Corridor, Vantage Point, Shift Duration (Max 2h).          |
|      - CLI: `python scripts/manage_field_session.py create --session-id SES-20261025-0001 ...`   |
|                                                                                                  |
|   2. ON-SITE ACTIVATION (`ACTIVE_COLLECTING`)                                                    |
|      - Team arrives at elevated vantage point.                                                   |
|      - Field Lead executes `PreCollectionSafetyCheck`.                                           |
|      - CLI: `python scripts/manage_field_session.py start --session-id ... --lead-id ...`         |
|                                                                                                  |
|   3. CYCLIC OBSERVATION LOGGING                                                                  |
|      - Every 15 minutes, Data Recorder enters observation into schema v2.0.                     |
|      - Ingestion pipeline validates GPS bounding box, timestamp, depth consistency.             |
|                                                                                                  |
|   4. TERMINATION PATHS:                                                                          |
|      - Path A: NORMAL CLOSURE (`CLOSED_COMPLETE`)                                                |
|        Shift ends; team returns to base camp; Field Lead signs `PostCollectionSafetyReview`.     |
|        CLI: `python scripts/manage_field_session.py close --session-id ... --lead-id ...`        |
|                                                                                                  |
|      - Path B: SAFETY ABORT (`SAFETY_ABORTED`)                                                   |
|        Weather threshold breached; Safety Officer calls "STOP WORK"; team evacuates.             |
|        CLI: `python scripts/manage_field_session.py abort --session-id ... --reason ...`         |
|                                                                                                  |
+--------------------------------------------------------------------------------------------------+
```

---

## 3. Step-by-Step Field Lead Checklist

### Step 1: Pre-Departure Check (Base Camp)
- [ ] Confirm Pilot Activation Gate is `PILOT_AUTHORIZED`.
- [ ] Verify daylight window: Current time is between 08:00 and 17:30 IST.
- [ ] Inspect Class 2 high-visibility safety vests, steel-shank boots, and hard hats.
- [ ] Verify trauma first-aid kit, whistles, and fully charged satellite/cellular phones.
- [ ] Calibrate 3m fiberglass depth staff and laser rangefinder.

### Step 2: Vantage Arrival & On-Site Inspection
- [ ] Park vehicle in secure off-street commercial parking.
- [ ] Ascend to elevated footbridge via public stairs.
- [ ] Safety Officer confirms physical vantage point is entirely grade-separated from vehicular lanes.
- [ ] Verify weather: Damini lightning check confirms zero strikes within 10 km.
- [ ] Submit `PreCollectionSafetyCheck` via CLI or tablet.

### Step 3: Observation Logging (Every 15 min)
- [ ] Categorize water presence (`NO_WATER`, `PARTIAL_LANE_WATERLOGGING`, etc.).
- [ ] Measure or index water depth from bridge without leaning over railing.
- [ ] Observe real vehicle behavior for passability classification.
- [ ] Ensure any telephoto imagery contains zero identifiable faces or private property.
- [ ] Ingest record via `ObservationIngestionPipeline`.

### Step 4: Demobilization & Post-Review
- [ ] Pack gear and return to vehicle before daylight drops below safe levels.
- [ ] Execute `audit_phase6_observations.py` to verify record schema validity.
- [ ] Submit `PostCollectionSafetyReview` and close the session.
