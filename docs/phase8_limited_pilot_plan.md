# Sahaay AI — Phase 8 Smallest Feasible Safe Pilot Plan: Rasoolpura Corridor

**Document Version:** 1.0.0  
**Phase:** 8 (Limited Pilot Scope Definition)  
**Date:** 2026-10-25  
**Candidate Pilot Site:** CORR-HYD-01 (Begumpet — Rasoolpura Metro Walkway)  
**Status:** Pre-Approved Protocol Template (Blocked until prerequisites verified)  

---

## 1. Minimal Pilot Scope Definition

To minimize operational risk while establishing empirical validation feasibility, Sahaay AI defines the **Smallest Feasible Safe Pilot Scope**:

```
+--------------------------------------------------------------------------------------------------+
|                                    MINIMAL SAFE PILOT SPECIFICATION                              |
+--------------------------------------------------------------------------------------------------+
| Attribute               | Minimal Safe Scope Specification                                       |
+-------------------------+------------------------------------------------------------------------+
| Target Corridor         | CORR-HYD-01 (Rasoolpura Junction, Begumpet)                            |
| Specific Vantage Point  | Rasoolpura Metro Station Concourse Elevated Walkway                    |
| Grade Separation        | 4.8 meters vertical clearance above roadway; permanent 1.2m barrier    |
| Traffic Exposure        | ZERO. 100% grade-separated from vehicular carriageway                 |
| Operating Window        | 08:00 IST to 12:00 IST (Morning Daylight Hours Only)                   |
| Shift Duration          | Maximum 2 hours continuous monitoring                                  |
| Field Team Roster       | 1 Field Lead, 1 Safety Officer, 1 Data Recorder                        |
| Measurement Method      | Non-contact: Visual curb calibration & vertical fiberglass depth staff |
| Optical Camera Policy   | Telephoto pavement only; automatic Gaussian blurring of faces/plates   |
+--------------------------------------------------------------------------------------------------+
```

---

## 2. Scope-Specific Pre-Collection Readiness Checklist

Before the designated Field Lead may activate a session at Rasoolpura Metro Walkway, the following 10 checklist items must evaluate to **TRUE**:

```
===================================================================================
             SAHAAY AI — RASOOLPURA METRO LIMITED PILOT CHECKLIST
===================================================================================
[ ] CHECK-01: Pilot Activation Gate state evaluates to PILOT_AUTHORIZED.
[ ] CHECK-02: Physical survey of Rasoolpura concourse confirmed structural railing >= 1.1m.
[ ] CHECK-03: Metro station security informed of passive non-interfering research vantage.
[ ] CHECK-04: Team members wearing EN ISO 20471 Class 2 safety vests and non-slip boots.
[ ] CHECK-05: 3m calibrated fiberglass staff gauge and laser rangefinder verified.
[ ] CHECK-06: Fully charged satellite/cellular phones with 100/108/GHMC Control numbers saved.
[ ] CHECK-07: Weather check: IMD Damini radar confirms zero lightning strikes within 10 km.
[ ] CHECK-08: Wind check: Local anemometer confirms wind gusts < 35 km/h.
[ ] CHECK-09: Ambient lighting: Daylight lux confirmed >= 500 lux (daylight operations).
[ ] CHECK-10: Cardinal Rule 1 acknowledged: ZERO entry into floodwater by any team member.
===================================================================================
DECISION: [ ] PROCEED (All 10 True)    [X] BLOCKED (One or more False)
===================================================================================
```

---

## 3. Human Approval Record Template

When all 10 items above evaluate to TRUE, the Principal Investigator or Project Director must execute this formal authorization record:

```json
{
  "approval_record_id": "AUTH-PILOT-RASOOLPURA-01",
  "approved_corridor_id": "CORR-HYD-01",
  "vantage_point": "Rasoolpura Metro Concourse Walkway",
  "authorized_operating_window": {
    "valid_from_utc": "2026-10-26T02:30:00Z",
    "valid_until_utc": "2026-10-26T06:30:00Z"
  },
  "roster": {
    "field_lead_name_and_id": "HUMAN_TEAM_TO_SUPPLY",
    "safety_officer_name_and_id": "HUMAN_TEAM_TO_SUPPLY",
    "data_recorder_name_and_id": "HUMAN_TEAM_TO_SUPPLY"
  },
  "safety_veto_acknowledgement": true,
  "cardinal_rules_acknowledged": true,
  "authorizing_official_role": "PROJECT_DIRECTOR",
  "authorizing_official_id": "DIR-HYD-01",
  "authorization_timestamp_utc": "2026-10-26T02:00:00Z",
  "digital_signature_hash": "SHA256_HEX_PLACEHOLDER"
}
```
