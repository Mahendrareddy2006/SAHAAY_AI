# Sahaay AI — Phase 7 Pilot Feasibility Protocol & Phased Implementation

**Document Version:** 1.0.0  
**Phase:** 7 (Pilot Activation Gate & Operational Validation)  
**Date:** 2026-10-25  
**Study Type:** Human-Supervised Operational Feasibility Pilot  

---

## 1. Study Objective & Scientific Boundary

The primary objective of the first Hyderabad field pilot is **feasibility assessment**, not model accuracy benchmarking. Specifically, the pilot must establish:
1. Can ground-truth water depth and road passability observations be collected safely without endangering field personnel?
2. Does the data-ingestion pipeline reliably preserve spatio-temporal provenance and filter duplicates under real monsoon conditions?
3. Can field observers achieve high inter-observer agreement ($\ge 90\%$) using the standardized measurement rubrics?

### Critical Scientific Guardrails:
- **Zero Premature Claims:** An absence of observed flooding during dry weather or light rainfall cannot be interpreted as proof that Sahaay AI predicts or detects floods accurately.
- **Pre-Registration Lock:** The sample size requirements ($50$ flood episodes, $100$ non-flood episodes across $\ge 4$ storm dates) pre-registered in Phase 6 remain locked and cannot be retroactively adjusted based on pilot outcomes.

---

## 2. Four-Stage Feasibility Progression

```
+--------------------------------------------------------------------------------------------------+
|                                  PILOT FEASIBILITY STAGES                                        |
+--------------------------------------------------------------------------------------------------+
|                                                                                                  |
|   STAGE A: SYNTHETIC DRY RUN (Current Repository State)                                          |
|   - Goal: Validate software schemas, CLI tools, review queues, and failure modes.               |
|   - Data: Strictly simulated fixtures labeled `is_synthetic_or_simulated: true`.                 |
|   - Safety Risk: ZERO. No physical field deployment.                                             |
|                                                                                                  |
|   STAGE B: AUTHORIZED NON-HAZARDOUS BASELINE OBSERVATION (Clear Weather)                         |
|   - Prerequisite: PilotActivationGate == PILOT_AUTHORIZED.                                       |
|   - Goal: Validate physical access to elevated footbridges; test optical rangefinder & staffs.   |
|   - Conditions: Dry daylight conditions (08:00 - 17:30 IST); zero rainfall.                     |
|   - Verification: Zero vehicular interaction; 100% bystander privacy redaction.                  |
|                                                                                                  |
|   STAGE C: CONTROLLED MONSOON WEATHER-EVENT OBSERVATION                                          |
|   - Prerequisite: Successful completion of Stage B and active precipitation forecast.            |
|   - Goal: Collect physical observations during naturally occurring rain storms.                  |
|   - Safety Directives: Cardinal safety rules enforced; 10km lightning / 35km/h wind abort limits.|
|                                                                                                  |
|   STAGE D: DATA QUALITY & DISAGREEMENT AUDIT                                                     |
|   - Goal: Comprehensive post-pilot audit of measurement completeness, error bounds,             |
|     observer disagreement clusters, and spatial disaggregation.                                  |
|                                                                                                  |
+--------------------------------------------------------------------------------------------------+
```

---

## 3. Data Integrity & Observer Agreement Rules

1. **Dual Observer Protocol:** During Stage C, two observers will record independent, uncoordinated observations at the same vantage point every 15 minutes.
2. **Disagreement Flagging:** If Observer A and Observer B disagree on water presence category or report depths differing by $> 5.0\text{ cm}$, the ingestion pipeline automatically tags both records with `quality_flags: OBSERVER_DISAGREEMENT`.
3. **Supervisor Attribution:** Disagreements are routed to `GET /api/v1/review/pending` where a supervisor reviews telephoto imagery and issues an attributable reconciliation verdict.
