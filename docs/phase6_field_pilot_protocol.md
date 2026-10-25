# Sahaay AI — Phase 6 Hyderabad Field Pilot Protocol & Pre-Collection Checklist

**Document Version:** 1.0.0  
**Status:** Pilot Operational Protocol (Candidate State — Pending Authorization)  
**Date:** 2026-10-25  

---

## 1. Candidate Corridor Selection & Rationale

Four candidate corridors in Hyderabad were identified in Phase 3 and Phase 4. These sites remain **candidate corridors only**; no field collection may begin until site inspections and municipal clearances are documented.

```
+---------------------------------------------------------------------------------------------------------+
|                                    CANDIDATE CORRIDOR MATRIX                                            |
+---------------------------------------------------------------------------------------------------------+
| Corridor ID      | Name / Segment             | Historical Vulnerability | Safe Vantage Location        |
+------------------+----------------------------+--------------------------+------------------------------+
| CORR-HYD-01      | Begumpet (Rasoolpura -     | CRITICAL (Low elevation, | Rasoolpura Metro Station     |
|                  | Prakash Nagar Junction)    | nala bottle-neck)        | Elevated Pedestrian Walkway  |
+------------------+----------------------------+--------------------------+------------------------------+
| CORR-HYD-02      | Tolichowki - Shaikpet      | HIGH (Drainage runoff    | Tolichowki Flyover           |
|                  | Main Road                  | from Jubilee Hills)      | Pedestrian Walkway           |
+------------------+----------------------------+--------------------------+------------------------------+
| CORR-HYD-03      | Madhapur - Hitec City      | MODERATE (High traffic   | Cyber Towers Junction        |
|                  | (Cyber Towers Junction)    | arterial route)          | Skywalk Pedestrian Deck      |
+------------------+----------------------------+--------------------------+------------------------------+
| CORR-HYD-04      | Musheerabad - RTC X Roads  | HIGH (Old drainage       | RTC X Roads Foot             |
|                  |                            | network, Musi basin)     | Over-Bridge (FOB)            |
+------------------+----------------------------+--------------------------+------------------------------+
```

### Selection Rationale:
1. **Severe Historical Inundation:** Documented in municipal disaster records and open-source data during monsoon seasons (2016, 2020, 2021).
2. **Elevated Physical Vantage Availability:** Every selected candidate site has an existing, grade-separated pedestrian footbridge, metro station concourse walkway, or flyover sidewalk that allows observation from $\ge 4\text{ meters}$ above road grade without entering traffic.
3. **AWS Proximity:** Each candidate site is located within $3.5\text{ km}$ of a TSDPS automatic weather station.

---

## 2. Mandatory Pre-Collection Checklist (Operational Safety Gate)

Before any field observation session may be scheduled or dispatched, the following checklist must be completed. **If any single item evaluates to FALSE, the deployment is programmatically and operationally BLOCKED.**

```
===================================================================================
                   SAHAAY AI — PRE-COLLECTION AUTHORIZATION GATE
===================================================================================
[ ] GATE-01: Institutional Data Access Agreement / MoU signed with GHMC or HTP.
[ ] GATE-02: Physical site hazard inspection completed by Field Operations Lead within last 14 days.
[ ] GATE-03: Written confirmation that vantage point is completely clear of vehicular traffic.
[ ] GATE-04: Team staffing confirmed: Field Lead, Safety Officer, and Data Recorder all present.
[ ] GATE-05: Certified Class 2 high-visibility safety vests and non-slip boots verified for all team members.
[ ] GATE-06: Telescopic fiberglass depth gauge and optical rangefinder calibrated.
[ ] GATE-07: First-aid trauma kit and emergency whistle present in vehicle.
[ ] GATE-08: Local emergency contacts (GHMC Control, Traffic Police, 108) verified and saved on all phones.
[ ] GATE-09: Weather check completed: Zero lightning warnings (< 10 km) and wind gusts < 35 km/h.
[ ] GATE-10: Daylight confirmation: Planned observation window falls strictly between 08:00 and 17:30 IST.
[ ] GATE-11: Data-logging tablet initialized with cryptographically signed offline-first schema (v2.0).
[ ] GATE-12: Zero private residential balconies or unpermitted commercial structures used as vantage points.
===================================================================================
DECISION: [ ] PROCEED (All 12 True)    [X] BLOCKED (One or more False)
===================================================================================
Current Repository State: GATE EVALUATION = BLOCKED (Item 01 and 02 are currently FALSE).
```

---

## 3. Observation Schedule & Reporting Workflow

Field deployments are organized into structured, time-bounded shifts during naturally occurring rainfall events:

```
+--------------------------------------------------------------------------------------------------+
|                                    OBSERVATION SHIFT WORKFLOW                                    |
+--------------------------------------------------------------------------------------------------+
|                                                                                                  |
|   PHASE 1: TRIGGER & DISPATCH (T - 60 min)                                                       |
|   - Radar or AWS indicates incoming precipitation event over candidate corridor.                 |
|   - Field Lead verifies weather forecast and completes Pre-Collection Checklist.                 |
|   - Team departs base camp in field vehicle; parks in safe, designated off-street parking.       |
|                                                                                                  |
|   PHASE 2: SITE OCCUPATION (T = 0)                                                               |
|   - Team ascends to designated pedestrian walkway / footbridge via secure public stairs.        |
|   - Safety Officer establishes observation zone; confirms 360-degree clear pedestrian flow.     |
|   - Data Recorder logs arrival timestamp, GPS fix ($\pm \text{meters}$), and weather condition.  |
|                                                                                                  |
|   PHASE 3: CYCLIC MONITORING (Every 15 minutes for max 2 hours)                                  |
|   - Step A: Water presence check (categorical rubric).                                           |
|   - Step B: Water depth measurement (via visual curb index or calibrated staff from bridge).     |
|   - Step C: Roadway passability assessment (observing real vehicle behavior through junction).   |
|   - Step D: Contextual vantage image capture (strictly telephoto roadway, faces/plates blurred). |
|   - Step E: Immediate local sync to encrypted tablet storage.                                    |
|                                                                                                  |
|   PHASE 4: DEMOBILIZATION & DATA AUDIT                                                           |
|   - Team returns to base camp before 17:30 IST or upon weather abort trigger.                    |
|   - Data Recorder runs automated schema validation (`audit_phase6_observations.py`).             |
|   - Field Lead cryptographically signs and locks the observation batch.                          |
|                                                                                                  |
+--------------------------------------------------------------------------------------------------+
```

---

## 4. Privacy, Consent, and Data-Retention Procedures

All data collected in the field must comply with the **Digital Personal Data Protection (DPDP) Act 2023**:

1. **No Identifiable Bystander Imagery:**
   - Field photography must be framed to focus on road pavement, curbs, and water reflections.
   - Any accidental capture of pedestrians or vehicle license plates must be processed through an automated redaction filter (Gaussian blur $\ge 15\text{ px}$) prior to entering the analysis pipeline.
2. **No Private Residential Intrusion:**
   - Field teams may never photograph private courtyards, residential windows, or private commercial interiors.
3. **Encrypted Storage:**
   - Raw logs and imagery must be stored on AES-256 encrypted drives.
4. **Data Retention Limits:**
   - De-identified research observations will be preserved for up to 36 months for scientific benchmarking.
   - Raw unredacted buffer records (if captured) must be purged within 14 days following verification.
