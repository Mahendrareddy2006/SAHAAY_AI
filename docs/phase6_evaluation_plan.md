# Sahaay AI — Phase 6 Pre-Registered Evaluation Plan

**Document Version:** 1.0.0  
**Registration Date:** 2026-10-25  
**Evaluation Target:** Sahaay AI Multi-Modal Flood Intelligence Platform  
**Governance:** Open Science Pre-Registration Standard  

---

## 1. Executive Summary & Non-Negotiable Safeguards

To prevent p-hacking, retrospective threshold tuning, and false claims of machine learning predictive accuracy, this document pre-registers the evaluation design, statistical hypotheses, inclusion/exclusion rules, metrics, and acceptance criteria *prior* to conducting field observations or processing empirical data.

### Pre-Registration Invariant Safeguards:
1. **Zero Circular Validation:** The historical flood hotspot dataset (115 points) used to compute the static road vulnerability score in Phase 4 cannot serve as ground-truth test labels for evaluating vulnerability or the Decision Engine.
2. **Missing Telemetry Rule:** A missing rainfall observation must never be evaluated as $0.0\text{ mm}$.
3. **Absence of Proof is Not Proof of Absence:** A missing field observation must never be labeled as a negative ("no flood") example.
4. **Vision V4 Isolation:** Vision V4 is strictly excluded from the operational evaluation path under its established **NO-GO** gate.

---

## 2. Evaluation Questions by Subsystem

### A. Subsystem 1: Rainfall Baseline Engine
- **Primary Question Q1.1:** Does the rainfall engine maintain monotonic risk scoring as 1-hour rainfall increases from $0\text{ mm}$ to $100\text{ mm/hr}$?
- **Secondary Question Q1.2:** Does the engine transition to `INSUFFICIENT_DATA` or flag telemetry as stale when station observation age exceeds $120\text{ minutes}$?
- **Secondary Question Q1.3:** Does the engine reject or quarantine unphysical sensor anomalies (e.g. negative precipitation or spikes $> 200\text{ mm/hr}$)?

### B. Subsystem 2: Road Vulnerability Baseline Engine
- **Primary Question Q2.1:** Are the generated road vulnerability categories (`LOW`, `MODERATE`, `HIGH`, `CRITICAL`) spatially stable under small GPS coordinate perturbations ($\le 25\text{ meters}$)?
- **Secondary Question Q2.2:** Does every elevated vulnerability score include at least one attributable reason code (`PROXIMITY_HISTORICAL_HOTSPOT`, `LOW_ELEVATION_DEPRESSION`, `HIGH_DRAINAGE_DENSITY`)?
- **Independence Requirement:** Field validation must assess vulnerability against independently recorded street water accumulation, not against the training hotspot catalog.

### C. Subsystem 3: Multi-Modal Decision Engine
- **Primary Question Q3.1:** Does the Decision Engine achieve $100\%$ safe abstention (zero autonomous road closures and zero emergency dispatches) when flood evidence is unverified?
- **Primary Question Q3.2:** When CCTV indicates dry asphalt but a citizen report asserts deep flooding, does the engine output `decision_status: INCONCLUSIVE` with reason code `CONTRADICTORY_OBSERVATIONS_DETECTED` in $100\%$ of cases?
- **Primary Question Q3.3:** When heavy rainfall occurs on a vulnerable road but zero field observations exist, does the engine output `current_flood_evidence_status: ELEVATED_ENVIRONMENTAL_RISK` rather than asserting confirmed flooding?

### D. Subsystem 4: Vision Model (Research Sandbox Only)
- Vision models remain excluded from the live evaluation path until a balanced, source-independent dataset is acquired.

---

## 3. Label Definitions & Inclusion/Exclusion Rules

### Ground-Truth Label Definitions:
- **Class 0 (Non-Flooded Road):** Ground-truth observation records `NO_WATER` or `SURFACE_WETNESS_OR_PUDDLE` ($d < 5.0\text{ cm}$) confirmed by supervisor review.
- **Class 1 (Waterlogged Road):** Ground-truth observation records `PARTIAL_LANE_WATERLOGGING` or `FULL_ROADWAY_INUNDATION` ($d \ge 5.0\text{ cm}$) confirmed by supervisor review or official DRF pump dispatch.

### Inclusion Rules:
- Record must have `verification_status: SUPERVISOR_VERIFIED`.
- Observation must have valid GPS coordinates within Hyderabad municipal boundary with precision $\le 15\text{ m}$.
- Timestamp must have contemporaneous ($\le 60\text{ min}$) rainfall telemetry or confirmed rain-gauge reading.

### Exclusion Rules:
- Observations flagged with `quality_flags: VIEW_OBSTRUCTED` or `UNRELIABLE_LIGHTING`.
- Records where observer disagreement was unresolved (`disagreement_status: UNRESOLVED`).
- Records marked `is_synthetic_or_simulated: true`.
- Observations submitted without explicit DPDP privacy consent.

---

## 4. Split Strategy: Group-Aware Spatial and Temporal Isolation

To prevent optimistic bias from spatial autocorrelation and temporal bursting:
1. **Corridor-Level Spatial Separation:** Observations from Candidate Corridor 1 (Begumpet) and Corridor 2 (Tolichowki) cannot be used to tune and evaluate on Corridor 3 (Madhapur).
2. **Event-Level Temporal Clustered Split:** All observations collected during a specific storm event (defined as rainfall occurring within a 24-hour meteorological window) must reside entirely within either the validation or test partition.
3. **Zero Burst Leakage:** Observations taken at 15-minute intervals from the same footbridge vantage point belong to the same episode cluster and must never cross splits.

---

## 5. Statistical Metrics & Uncertainty Reporting

Because real-world urban flood events are naturally class-imbalanced ($< 5\%$ of observation hours involve deep flooding), reporting raw "accuracy" is statistically invalid.

### Pre-Registered Primary Metrics:
1. **Balanced Accuracy:** Macro-average of recall across Class 0 (Dry/Puddle) and Class 1 (Flooded).
2. **Brier Score & Calibration Error:** Mean squared difference between predicted risk probabilities and binary outcomes.
3. **Contradiction Detection Recall:** Percentage of contradictory observation pairs correctly assigned `INCONCLUSIVE`.
4. **Safe Abstention Rate:** Proportion of missing/stale telemetry cases safely flagged without raising unverified alarms.
5. **Confidence Intervals:** All metrics must be reported with $95\%$ bootstrap confidence intervals ($B = 1,000$ iterations).

---

## 6. Sample Size Power Rationale & Acceptance Criteria

### Sample Size Calculation:
To detect a minimum balanced accuracy difference of $15\%$ against a baseline with $\alpha = 0.05$ and power $1 - \beta = 0.80$, the evaluation requires:
- Minimum **50 verified flood event episodes** (Class 1).
- Minimum **100 verified wet-road non-flooded episodes** (Class 0).
- Collected across at least **4 distinct storm dates** and **3 independent corridors**.

### Acceptance Thresholds for Pilot Validation:
- Decision Engine Contract Validity: $100.0\%$ (Zero schema failures).
- Contradiction Detection Recall: $\ge 95.0\%$.
- Safe Abstention under Missing Telemetry: $100.0\%$.
- Zero circular validation infractions: $100.0\%$.

---

## 7. Invalidation Conditions

The evaluation is automatically rendered **INVALID** if:
1. Any record from `data/phase5_demo/` or `data/phase6/review_fixtures/` is discovered in the evaluation set.
2. The Vision V4 gate is bypassed without independent external validation.
3. Historical hotspot points are used as test labels.
4. Evaluation thresholds are modified retrospectively after examining test outcomes.
