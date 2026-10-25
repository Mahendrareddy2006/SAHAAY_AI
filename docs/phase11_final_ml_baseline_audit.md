# Sahaay AI — Phase 11: Final AI/ML Baseline Audit

## 1. Executive Summary

This document establishes the official AI/ML engineering baseline audit for **Sahaay AI Phase 11: Final AI/ML Evaluation, Model Benchmarking & Research Handover**, continuing directly from Phase 10 commit [`e1ada07`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai).

As the final planned phase of AI/ML engineering, the objective of Phase 11 is to deliver an evidence-based, scientifically uncompromised synthesis of all machine learning models, heuristic scoring systems, diagnostic baselines, and data readiness audits across Phases 1 through 10.

### Core Strategic Commitments:
1. **Exclusively AI/ML Responsibility:** The scope is strictly confined to dataset auditing, model benchmarking, robustness evaluation, error analysis, and research handover. API endpoints, backend databases, frontend dashboards, live telemetry ingestion, deployment scripts, and pilot authorization workflows remain owned by other teammates and are untouched.
2. **No Manufactured Success:** In adherence to the non-negotiable directive that **a rigorous `NOT_RUN` result is preferable to an unsupported model claim**, this phase will not manufacture artificial model training results.
3. **Preservation of Safety Semantics:** All non-autonomous decision semantics (`NO_CURRENT_FLOOD_EVIDENCE` $\neq$ road safe; environmental susceptibility $\neq$ current inundation; missing telemetry $\neq$ zero rain) remain strictly invariant.
4. **Historical Artifact Integrity:** All historical model checkpoints, manifests, and audit reports are preserved on disk without modification or overwriting.

---

## 2. Working Tree & Commit Verification

Prior to performing any evaluation or generating deliverables, the Git repository state and working tree were forensically verified:

- **Baseline Commit:** `e1ada07` (`feat(phase10): rainfall and road-risk model experiments, baselines & evaluation`)
- **Active Branch:** `master`
- **Working Tree Status:** Clean (zero uncommitted changes, zero untracked files).
- **Pre-Change Test Regression Baseline:**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest -q
  ```
  - **Total Tests:** 159
  - **Passed Tests:** **159** (100% pass rate in 8.15s)
  - **Failed Tests:** 0
  - **Subsystem Breakdown:**
    - Pilot activation, session management & blocker closure: 36 passed
    - Hyderabad geospatial & rainfall risk pipeline: 12 passed
    - Decision engine contracts & end-to-end integration: 21 passed
    - Vision model validation, quality gate & split integrity: 64 passed
    - Phase 9 adversarial split-integrity & audit tests: 8 passed
    - Phase 10 risk-baseline edge-case tests: 18 passed

---

## 3. Physical Artifact Verification on Disk

Every checkpoint, manifest, dataset, and script referenced in Phase 11 was independently checked for physical existence, file size, and MD5 checksum:

### 3.1 Vision Model Checkpoints ([`models/vision/`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision))
| Checkpoint Identifier | File Path | File Size (Bytes) | MD5 Checksum | Architecture / Parameters | Training Dataset |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **V1 Baseline** | [`models/vision/best_model.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/best_model.pt) | 18,493,276 | `82b57acf92942266b4a6a26713515ee4` | MobileNetV3-Small (1.52M params) | Manifest V1 (roham1 scraped imagery) |
| **V2 Clean Split** | [`models/vision/v2/model_v2.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v2/model_v2.pt) | 18,493,276 | `88e117abbc123bd6299e22c6374bd8c7` | MobileNetV3-Small (1.52M params) | Manifest V2 (clean split roham1) |
| **V3 Clean** | [`models/vision/v3/model_v3_clean.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v3/model_v3_clean.pt) | 18,493,276 | `b553eee151c66f96b809204a638fd30e` | MobileNetV3-Small (1.52M params) | Manifest V3 (Clemson flood + Virenbr11) |
| **V3 Monsoon** | [`models/vision/v3/model_v3_monsoon.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v3/model_v3_monsoon.pt) | 18,493,276 | `818ae953fc264badf86e14e08bf9f26b` | MobileNetV3-Small (1.52M params) | Manifest V3 with monsoon augmentations |

### 3.2 Dataset Manifests ([`data/processed/`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/processed))
| Manifest Name | File Path | File Size (Bytes) | MD5 Checksum | Partition Details |
| :--- | :--- | :---: | :---: | :--- |
| **Manifest V2 Test** | [`data/processed/manifest_v2/test_v2.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/processed/manifest_v2/test_v2.csv) | 122,297 | `0207c1501e8c7e1878f5c2d5acbb8144` | $N=450$ (225 flood, 225 non-flood) |
| **Manifest V3 Test** | [`data/processed/manifest_v3/test_v3.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/processed/manifest_v3/test_v3.csv) | 70,572 | `551d91c9254a29dde46b0b3e3e05f09f` | $N=222$ (111 Clemson, 50 dry, 61 potholes) |
| **Manifest V4 Full** | [`data/processed/manifest_v4/full_manifest_v4.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/processed/manifest_v4/full_manifest_v4.csv) | 477,289 | `c7d9665e51d64c3b826840a8f76b4fdd` | $N=1,478$ (739 flood, 739 non-flood) |
| **Manifest V4 Train** | [`data/processed/manifest_v4/train_v4.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/processed/manifest_v4/train_v4.csv) | 334,064 | `c3a08bfcc8a71a619eb7ebc197cfcfd7` | $N=1,034$ (Train partition, zero leakage) |
| **Manifest V4 Val** | [`data/processed/manifest_v4/val_v4.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/processed/manifest_v4/val_v4.csv) | 71,943 | `ed700563a837af34cd5c69548c706373` | $N=223$ (Validation partition) |
| **Manifest V4 Test** | [`data/processed/manifest_v4/test_v4.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/processed/manifest_v4/test_v4.csv) | 71,602 | `35e3e52c52c831657fff60e0d67ca398` | $N=221$ (Strictly locked evaluation test set) |

### 3.3 Hydrological & Geospatial Datasets ([`data/hyderabad_risk/`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/hyderabad_risk))
| Dataset Name | File Path | File Size (Bytes) | MD5 Checksum | Records / Features |
| :--- | :--- | :---: | :---: | :--- |
| **Flooding Locations** | [`data/hyderabad_risk/raw/flooding_locations.kml`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/hyderabad_risk/raw/flooding_locations.kml) | 16,367 | `52180f3e0ac2a0fcaa0b3407041e4576` | 23 static placemarks (0 timestamps, 0 depths) |
| **Hyderabad Drains** | [`data/hyderabad_risk/raw/hyderabad_drains.kml`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/hyderabad_risk/raw/hyderabad_drains.kml) | 584,087 | `9de0987beed49f1ced89982dad2c82a6` | 96 multi-segment nala LineStrings |
| **Waterbodies** | [`data/hyderabad_risk/raw/greater_hyderabad_waterbodies.geojson`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/hyderabad_risk/raw/greater_hyderabad_waterbodies.geojson) | 5,039,685 | `2d33ee59f119e40722e7e2dea6734ff7` | 2,324 lake and tank Polygons |
| **Monthly Rainfall** | [`data/hyderabad_risk/raw/hyderabad_monthly_rainfall_1901_2021.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/hyderabad_risk/raw/hyderabad_monthly_rainfall_1901_2021.csv) | 16,778 | `023abc5d7a1635bc593e132f354e8dc4` | 121 years of gridded monthly rainfall |
| **Hourly Telemetry** | [`data/hyderabad_risk/raw/telangana_hourly_telemetry_rainfall_2021_2025.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/hyderabad_risk/raw/telangana_hourly_telemetry_rainfall_2021_2025.csv) | 9,131,690 | `caf7704ffe26ca9ec18d207b9d2d1924` | 72,223 raw records across 38 stations |
| **Derived Features** | [`data/hyderabad_risk/derived/hyderabad_risk_features.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/hyderabad_risk/derived/hyderabad_risk_features.csv) | 5,232 | `000d66e7a851be396f171aadd636114c` | 20 candidate Hyderabad road corridors |

---

## 4. Synthesis of Historical Findings

### 4.1 Phase 9: Vision Model Benchmarking & Confounding Audit
- **Cramér's $V = 1.0000$ and Mutual Information $= 1.0000\text{ bits}$:** Across all available road imagery, source identity perfectly predicts class ($100\%$ of flood images originate from Clemson; $100\%$ of road negatives originate from Virenbr11).
- **Non-Semantic Metadata Shortcut:** A Random Forest classifier trained strictly on file metadata (`width`, `height`, `file_size_kb`, `aspect_ratio`, `megapixels`, `bytes_per_pixel`) achieves **85.97% test accuracy** on Manifest V4 without observing image pixels.
- **Vision V4 Gate Status:** Formally locked in **`NO-GO`** status. Production training was recorded as **`NOT_RUN`**.

### 4.2 Phase 10: Rainfall and Road-Risk Baseline Evaluation
- **Rules-Based Reference Validation:** 21 / 21 boundary, monotonicity, and edge-case checks passing across IMD intensity thresholds ($7.5, 15.0, 35.0, 100.0\text{ mm/hr}$), multi-window surge/saturation, and confidence discounting.
- **Zero Ground-Truth Flood Outcome Labels:** `flooding_locations.kml` contains static chronic points with no timestamps or depths. Real-world observation database contains exactly 0 observations. Supervised flood prediction was recorded as **`NOT_RUN`**.
- **Telemetry Inadequacy for Forecasting:** Rain gauge telemetry exhibits $>90\%$ missingness, up to 141.6-day transmission gaps, and $50.82\%$ cumulative bucket accumulator counters ($>250\text{ mm}$). Short-term rainfall forecasting was recorded as **`NOT_RUN`**.

---

## 5. Scope Boundaries & Objectives for Phase 11

In Phase 11, the AI/ML engineering responsibility executes:
1. Production of the definitive 7-category component inventory ([`docs/phase11_model_inventory.md`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/docs/phase11_model_inventory.md)).
2. Comprehensive vision evaluation distinguishing historical claims from reproduced metrics ([`docs/phase11_vision_evaluation.md`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/docs/phase11_vision_evaluation.md)).
3. Rainfall and vulnerability baseline evaluation against the validated Phase 10 standard ([`docs/phase11_rainfall_road_risk_evaluation.md`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/docs/phase11_rainfall_road_risk_evaluation.md)).
4. Evidence-based model selection and operational dispositions ([`docs/phase11_model_selection_decisions.md`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/docs/phase11_model_selection_decisions.md)).
5. Teammate integration handover document preserving safety invariants ([`docs/phase11_ml_handover_for_team.md`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/docs/phase11_ml_handover_for_team.md)).
6. Final technical completion report ([`docs/phase11_completion_report.md`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/docs/phase11_completion_report.md)).
