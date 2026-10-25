# Sahaay AI — Phase 7 Evaluation Readiness & Model Safety Gate

**Document Version:** 1.0.0  
**Phase:** 7 (Pilot Activation Gate & Operational Validation)  
**Date:** 2026-10-25  

---

## 1. Principles of Independent Evaluation

Supervised machine learning evaluation in flood resilience is prone to systemic shortcuts:
1. **Conflating Rule Conformance with Prediction Accuracy:** Passing 111 unit tests demonstrates that the software executes its coded rules properly. It does **not** prove that Sahaay AI accurately predicts real floods in Hyderabad.
2. **Circular Validation Prohibition:** Static vulnerability was calibrated against historical municipal waterlogging spots (115 points). Those points cannot be used as ground-truth test labels.
3. **Imbalanced Evaluation Fallacy:** In Hyderabad, dry or passable roads account for $> 95\%$ of observation shifts. Reporting raw overall accuracy creates an illusion of high performance by predicting "no flood" constantly.

---

## 2. Pre-Registered Episode Definitions & Sample Size Thresholds

To eliminate ambiguity prior to conducting evaluations, episode units are formalized as follows:

```
+--------------------------------------------------------------------------------------------------+
|                                    EPISODE BOUNDARY CRITERIA                                     |
+--------------------------------------------------------------------------------------------------+
|                                                                                                  |
|   1. VERIFIED FLOOD EPISODE (Class 1)                                                            |
|      - Physical water depth verified at $d \ge 5.0\text{ cm}$ over at least 1 traffic lane.       |
|      - Temporal Boundary: Measurements taken within 60 minutes at the same junction belong to     |
|        the SAME episode (to prevent repeated counting of a single puddle).                       |
|      - Spatial Boundary: Must be separated by $> 500\text{ meters}$ to count as an independent   |
|        inundation site.                                                                          |
|                                                                                                  |
|   2. VERIFIED NON-FLOOD EPISODE (Class 0)                                                        |
|      - Road asphalt verified as dry, damp, or localized puddle ($d < 5.0\text{ cm}$).            |
|      - Meteorological Requirement: Must be recorded while local AWS records active rain           |
|        ($> 0.0\text{ mm}$ within past 3 hours) to verify non-inundation under rainfall stress.   |
|                                                                                                  |
+--------------------------------------------------------------------------------------------------+
```

### Eligibility Prerequisites for Supervised Model Evaluation:
- **Minimum 50 independent flood episodes** (Class 1).
- **Minimum 100 independent non-flood episodes** (Class 0).
- Collected across at least **4 distinct storm dates** and **3 independent candidate corridors**.
- **Zero cross-split cluster leakage:** All observations from an event date and corridor must reside in the same split.

---

## 3. Subsystem Evaluation Status

| Subsystem | Readiness Gate Status | Permitted Operational Evaluation |
| :--- | :---: | :--- |
| **Vision V4** | **NO-GO** | Blocked. Optical models may not assert flood labels or trigger alarms. |
| **Rainfall Baseline** | `BLOCKED_PENDING_GROUND_TRUTH` | Rule conformance & missingness tests only. No supervised re-weighting. |
| **Road Vulnerability** | `BLOCKED_PENDING_GROUND_TRUTH` | Spatial stability tests only. Hotspot validation prohibited. |
| **Decision Engine** | `CONFORMANCE_VERIFIED` | Response contract, reason code completeness, and safe abstention verified. |
