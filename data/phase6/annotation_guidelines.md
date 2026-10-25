# Sahaay AI — Phase 6 Ground-Truth Annotation & Rubric Guidelines

**Document Version:** 1.0.0  
**Status:** Official Annotation Standard  
**Date:** 2026-10-25  

---

## 1. Principles of Ground-Truth Integrity

The integrity of any machine learning model or rule-based decision engine is bounded by the precision and honesty of its ground-truth labels. In flood intelligence, ambiguous annotations and sloppy classifications directly lead to false alarms or catastrophic omissions.

### Core Tenets:
1. **Never Impute Absence of Observation as Absence of Flood:** If an observation is missing or obstructed, it must be recorded as `UNABLE_TO_OBSERVE`. It must **never** be labeled as `NO_WATER`.
2. **Never Generalize Point Observations Across Space or Time:** An observation of "No water" at 10:00 IST at Rasoolpura Junction applies *only* to that specific junction at that specific timestamp. It cannot be extrapolated to adjacent roads or subsequent hours.
3. **Explicit Measurement Provenance:** Measured water depth must document whether it was directly gauged against a physical calibrated staff, read from a surveyed municipal curb, or estimated from vehicle tire submersion.
4. **Resolution of Observer Disagreements:** When two observers record differing observations at the same location within the same 15-minute window, the record is flagged as `OBSERVER_DISAGREEMENT` and referred to the Supervisor. Conflicting observations are preserved side-by-side in raw storage and never blindly averaged.

---

## 2. Water Presence and Extent Rubric

Every observation must assign one of the following mutually exclusive categories:

| Category Code | Label | Definition | Boundary Edge Cases |
| :---: | :--- | :--- | :--- |
| `NO_WATER` | Dry or Surface Film | Asphalt is dry or damp from light rain without standing water or surface pooling. | Thin sheen reflecting light with depth $< 0.5\text{ cm}$ is `NO_WATER`. |
| `SURFACE_WETNESS_OR_PUDDLE` | Localized Puddles | Isolated depressions with water depth $0.5\text{ cm} \le d < 5.0\text{ cm}$; water covers $< 10\%$ of road lane area. | Vehicle tires splash but wheel rims are completely above water. |
| `PARTIAL_LANE_WATERLOGGING` | Partial Lane Inundation | Water depth $5.0\text{ cm} \le d < 20.0\text{ cm}$; standing water submerges at least 1 lane but leaves at least 1 lane passable. | Two-wheelers forced to slow down or navigate around the pooled water. |
| `FULL_ROADWAY_INUNDATION` | Full Carriageway Inundation | Water depth $\ge 20.0\text{ cm}$; water spans the entire width of the carriageway from curb to curb / median. | Traffic completely halted or large commercial vehicles only. |
| `UNABLE_TO_OBSERVE` | View Obstructed | Torrential rain, heavy fog, darkness, physical visual obstacle, or tear gas prevents clear view of asphalt. | Must be accompanied by `quality_flags` describing obstruction. |
| `INSUFFICIENT_QUALITY` | Low-Quality Observation | Observer reports high uncertainty, optical blur, or missing required metadata. | Excluded from analysis-ready evaluation datasets. |

---

## 3. Water Depth Measurement Rubric

Depth must be measured in centimeters ($\text{cm}$) using one of the four methods:

```
+--------------------------------------------------------------------------------------------------+
|                                    DEPTH MEASUREMENT METHODS                                     |
+--------------------------------------------------------------------------------------------------+
|                                                                                                  |
|   1. PHYSICAL_GAUGE_STAFF (Gold Standard - $\pm 1.0\text{ cm}$ error)                             |
|      - Calibrated fiberglass measurement rod lowered vertically from pedestrian railing.         |
|      - Observer must ensure base contacts road asphalt, not silt sediment.                       |
|                                                                                                  |
|   2. CURB_REFERENCE_CALIBRATION (Silver Standard - $\pm 2.5\text{ cm}$ error)                    |
|      - Visual index relative to surveyed municipal curb stone (standard Hyderabad curb = 15 cm).|
|      - 1/3 curb submerged = ~5 cm; half curb = ~7.5 cm; full curb submerged = 15 cm.            |
|                                                                                                  |
|   3. ESTIMATED_WHEEL_SUBMERSION (Bronze Standard - $\pm 5.0\text{ cm}$ error)                   |
|      - Visual index based on passenger car tire diameter (standard tire = ~60 cm diameter):     |
|        * Submerged to tire contact patch = ~5 cm.                                                |
|        * Submerged to lower rim lip = ~15 cm.                                                    |
|        * Submerged to center wheel hub = ~30 cm.                                                 |
|        * Submerged to hood line = > 60 cm.                                                       |
|                                                                                                  |
|   4. NOT_MEASURED                                                                                |
|      - When conditions do not allow safe depth estimation. Measured depth field must be null.   |
|                                                                                                  |
+--------------------------------------------------------------------------------------------------+
```

---

## 4. Road Passability Rubric

Traffic passability must be evaluated based on the behavior of actual vehicles traversing the segment:

| Passability Category | Criteria | Typical Depth Range |
| :--- | :--- | :---: |
| `PASSABLE_ALL_VEHICLES` | Normal traffic flow; all vehicle classes (two-wheelers, auto-rickshaws, sedans, buses) navigate without deviation. | $0 - 5\text{ cm}$ |
| `IMPASSABLE_TWO_WHEELERS` | Two-wheelers and auto-rickshaws stall, turn around, or mount pedestrian sidewalks; four-wheelers continue. | $5 - 15\text{ cm}$ |
| `IMPASSABLE_LOW_SEDANS` | Low-clearance hatchbacks and sedans stall or turn around; SUVs and heavy commercial vehicles continue. | $15 - 30\text{ cm}$ |
| `IMPASSABLE_ALL_LIGHT_VEHICLES`| All private passenger cars and light commercial vehicles turn back; only high-clearance buses/trucks pass. | $30 - 50\text{ cm}$ |
| `TOTALLY_IMPASSABLE` | All vehicular traffic is completely blocked; road is impassable to all standard motor vehicles. | $> 50\text{ cm}$ |
| `UNKNOWN` | No traffic present or view obstructed; passability cannot be determined. | N/A |

---

## 5. Ambiguous Cases & Disagreement Resolution Protocol

1. **Splashing vs Standing Water:** Moving water splashes created by vehicle speed must not be counted as flood depth. Look for undisturbed water lines against stationary objects (poles, curbs, barriers).
2. **Debris Accumulation vs Water Depth:** Piles of garbage, plastic bags, or fallen tree branches in water can mislead visual depth. Observers must measure depth where the water surface meets clean curb or pole lines.
3. **Observer Disagreements:**
   - If Observer A records $12\text{ cm}$ (`PARTIAL_LANE_WATERLOGGING`) and Observer B records $22\text{ cm}$ (`FULL_ROADWAY_INUNDATION`), the records are linked via `disagreement_cluster_id`.
   - The supervisor reviews timestamped telephoto imagery and issues an attributable reconciliation verdict:
     * `CONFIRMED_OBSERVER_A` (with justification)
     * `CONFIRMED_OBSERVER_B` (with justification)
     * `SPLIT_UNCERTAIN_REJECT` (relegated to inconclusive research log).
