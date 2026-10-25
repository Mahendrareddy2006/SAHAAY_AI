# Sahaay AI — Phase 7 Data Quality & Coverage Reporting Specification

**Document Version:** 1.0.0  
**Phase:** 7 (Pilot Activation Gate & Operational Validation)  
**Date:** 2026-10-25  

---

## 1. Principles of Truthful Data Quality Reporting

Data quality reporting in Sahaay AI adheres to strict empirical truthfulness:
1. **Separation of Real, Replay, and Synthetic Data:** Real field observations, historical telemetry replays, and synthetic test fixtures are partitioned into distinct accounting categories and never merged.
2. **Zero Inferred Flood Labels:** A flood episode cannot be inferred from a rainfall spike, an unverified citizen complaint, or static vulnerability scores. Only physical staff gauge or surveyed curb measurements qualify.
3. **Transparent Non-Zero Reporting:** When zero eligible ground-truth observations exist in the repository, the report must state `0` directly.
4. **PII Redaction in Public Audits:** Aggregated coverage summaries must omit exact residential coordinates, observer names, or phone numbers.

---

## 2. Core Coverage & Quality Metrics

The automated reporting script is maintained at [`scripts/report_phase7_data_quality.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/scripts/report_phase7_data_quality.py), producing [`reports/phase7/observation_data_quality.json`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/phase7/observation_data_quality.json).

```
+--------------------------------------------------------------------------------------------------+
|                                    DATA QUALITY METRICS MATRIX                                   |
+--------------------------------------------------------------------------------------------------+
| Dimension                | Measured Attribute              | Validation Standard                 |
+--------------------------+---------------------------------+-------------------------------------+
| Provenance Segregation   | Real vs Replayed vs Synthetic   | Tagged with `is_synthetic` flag     |
| Spatial Disaggregation   | Unique Corridors Represented    | Verified against candidate list     |
| Temporal Spread          | Unique Storm Dates Sampled      | Minimum 4 independent rain events   |
| Metric Completeness      | Depth & Passability Present     | Target >= 95.0% completeness        |
| Measurement Units        | Centimeters (cm)                | 0.0 cm <= depth <= 300.0 cm         |
| Privacy Integrity        | DPDP Consent Status             | Target 100.0% consent compliant     |
| Ground-Truth Eligibility | Verified Flood ($d \ge 5\text{ cm}$) | Target >= 50 episodes               |
| Ground-Truth Eligibility | Verified Dry ($d < 5\text{ cm}$)     | Target >= 100 episodes              |
+--------------------------------------------------------------------------------------------------+
```

---

## 3. Current Repository Audit Status

At commit `0393286`:
- Real field observations: `0`
- Verified flood inundation episodes: `0`
- Evaluation eligibility status: `INSUFFICIENT_GROUND_TRUTH_BLOCKED`
- Model evaluation: **Strictly Prohibited** until the pre-registered sample size is achieved.
