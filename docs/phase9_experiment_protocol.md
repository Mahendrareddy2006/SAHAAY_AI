# Sahaay AI — Phase 9: Experiment Protocol & Benchmarking Architecture

## 1. Executive Summary

This document defines the formal experimental protocol for **Sahaay AI Phase 9**.

In alignment with the mandate to prioritize scientific validity over producing unvalidated checkpoints, Phase 9 partitions experimental work into three distinct tracks:
- **Track A:** Existing-data diagnostic experiments (evaluating non-semantic metadata ceilings and image-quality filters).
- **Track B:** Cross-source transfer and stress testing of historical checkpoints (`model_v1`, `model_v2`, `model_v3_clean`, `model_v3_monsoon`).
- **Track C:** Data-readiness quantification and annotation tooling, formally documenting why production Vision V4 model training is **`NOT_RUN`**.

---

## 2. Track A — Existing-Data Diagnostic Experiments

### 2.1 Protocol & Dataset Scope
Track A uses the leak-free, globally clustered [`manifest_v4`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/processed/manifest_v4) (1,034 train, 223 val, 221 test) exclusively for controlled diagnostic experiments:
- **Positive Class:** 739 street inundation images from `clemson_floodimg`.
- **Negative Class:** 374 clean dry road images + 365 wet pavement / pothole hard negatives from `virenbr11`.
- **Split Deduplication:** Verified zero cross-split duplicate leakage at perceptual hash distance $h \le 2$ (minimum cross-split distance $\ge 3$ bits).

### 2.2 Mandatory Scientific Disclosure
> [!IMPORTANT]
> **Source Confounding Disclosure:**
> Because source identity is 100% collinear with the class label in `manifest_v4` ($V = 1.0000, I = 1.0000\text{ bits}$), test accuracy metrics on this split **DO NOT** establish general real-world flood detection capability. High accuracy demonstrates that a model has learned to distinguish Clemson camera optics and compression profiles from Virenbr11 road surface photography.

### 2.3 Diagnostic Baselines Evaluated
1. **File-Size Decision Stump:** Evaluates whether file size alone separates classes. Achieves **80.09% test accuracy** and **0.8534 ROC-AUC**.
2. **Dimension Decision Stump:** Evaluates whether width and height alone separate classes. Achieves **67.42% test accuracy**.
3. **Multi-Feature Metadata Random Forest:** Evaluates all 6 non-semantic features (`width`, `height`, `aspect_ratio`, `file_size_kb`, `megapixels`, `bytes_per_pixel`). Achieves **85.97% test accuracy** and **0.9145 ROC-AUC**.
4. **Image Quality Gate Baseline:** Deterministic pre-inference filter evaluating native luminance, Laplacian variance blur, and native resolution. Rejects 100% of degraded inputs without making forced binary guesses.

---

## 3. Track B — Cross-Source Transfer & Stress Testing

Track B benchmarks previously trained model checkpoints across independent out-of-distribution sources and synthetic environmental stress cohorts:

### 3.1 Historical Model Checkpoints Evaluated
- `model_v1_baseline` ([`models/vision/best_model.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/best_model.pt))
- `model_v2_historical` ([`models/vision/v2/model_v2.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v2/model_v2.pt))
- `model_v3_clean` ([`models/vision/v3/model_v3_clean.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v3/model_v3_clean.pt))
- `model_v3_monsoon` ([`models/vision/v3/model_v3_monsoon.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v3/model_v3_monsoon.pt))

### 3.2 Key Empirical Transfer Findings
1. **V2 Collapse on Unseen Clean Pavement:**
   When evaluated on 50 clean, dry asphalt road images from `virenbr11_plain`, `model_v2_historical` yielded a **94.0% false positive rate** (accuracy = 6.0%, mean flood probability = 0.9173). Having trained on a biased dataset where road pavement was underrepresented, V2 misclassified standard asphalt texture as floodwater.
2. **V3 Monsoon Hard-Negative Rejection:**
   `model_v3_monsoon` achieved **100% specificity (0% FPR)** on `virenbr11_pothole` (61 waterlogged potholes and rain puddles), demonstrating that monsoon augmentation (contrast jitter, blur, flips) successfully penalized puddle false alarms.
3. **Optical Degradation Stress Testing:**
   Under simulated windshield wiper blur and heavy spray, `model_v3_monsoon` maintained 96.4% recall compared to 98.2% on clear images, whereas `model_v3_clean` experienced false negative drops under heavy contrast reduction.
4. **Disqualification of Roham1 Dataset:**
   The Kaggle Roham1 dataset was evaluated for transfer benchmarking and disqualified. Inspection revealed that 100% of its non-flood images are fixed $224 \times 224$ thumbnails of arbitrary non-road objects (indoor furniture, animals, portraits). Testing models on Roham1 benchmarks thumbnail-detection shortcuts rather than flood generalization.

---

## 4. Track C — Production Training Readiness & Gating

### 4.1 Formal Decision: **EXPERIMENT STATUS = `NOT_RUN`**
Production Vision V4 model training is formally recorded as **`NOT_RUN`**. The existing readiness gate remains locked in **`NO-GO`** status:

| Readiness Gate Check | Required Threshold | Current Verified Value | Gate Status |
| :--- | :---: | :---: | :---: |
| **Gate 1: Multi-Source Class Cross-Representation** | $\ge 2$ independent sources with $\ge 200$ positive & $\ge 200$ negative | **0 sources** | **FAILED** |
| **Gate 2: Source-Label Contingency** | Cramér's $V \le 0.30$, Mutual Info $\le 0.20\text{ bits}$ | $V = 1.0000, I = 1.0000\text{ bits}$ | **FAILED** |
| **Gate 3: Non-Semantic Metadata Ceiling** | Metadata diagnostic accuracy $\le 65.0\%$ | **85.97% test accuracy** | **FAILED** |
| **Gate 4: Real-World Ground Truth** | Approved field observations acquired | **0 real observations** | **FAILED** |

### 4.2 Required Data Target to Unlock Production Training
To unlock valid, unconfounded Vision V4 training, the following empirical target must be satisfied through the approved Phase 7/8 collection protocol:

1. **Physical Vantage Corridors:** Minimum 4 candidate Hyderabad elevated corridors (e.g., Rasoolpura Metro Walkway, Lakdikapul Junction, Tolichowki Flyover, Malakpet Railway Underbridge).
2. **Multi-Condition Pairing per Viewport:**
   - **Condition A (Dry Baseline):** Clean asphalt, daytime traffic ($\ge 200$ images) and nighttime traffic with streetlights ($\ge 100$ images).
   - **Condition B (Hard Negative / Rain-Wet):** Wet asphalt, reflections, puddles, potholes with water depth $< 5\text{ cm}$ ($\ge 200$ images).
   - **Condition C (True Inundation):** Standing floodwater with measured depth $\ge 5\text{ cm}$, submerged lane markings ($\ge 200$ images).
3. **Temporal Diversity:** Imagery captured across at least 4 independent monsoon storm dates.
4. **Annotation Quality:** Dual blind annotation with Cohen's Kappa $\kappa \ge 0.85$.
5. **No Synthetic Misattribution:** Sandbox dry-run records must never be converted into training labels.

---

## 5. Model Safety Semantics & Advisory Contracts

In accordance with Sahaay AI core governance rules:
- **Advisory-Only Mandate:** Photo classification alone CANNOT trigger autonomous municipal road closures, emergency service dispatch (108/112), or evacuation orders.
- **Corroboration Required:** An `EMERGENCY` alert requires joint corroboration from rainfall telemetry ($> 70\text{ mm/hr}$ on vulnerable roads) or physical ground-crew confirmation.
- **Five Standard Inference States:**
  1. `FLOOD_EVIDENCE_DETECTED`: Standing water inundation identified with high confidence on clear imagery.
  2. `NO_CURRENT_FLOOD_EVIDENCE`: Clean dry or wet asphalt without standing inundation.
  3. `INCONCLUSIVE`: Optical quality degraded (blur, darkness, whiteout) or probability within uncertainty band $[0.40, 0.60]$.
  4. `INSUFFICIENT_OR_STALE_DATA`: Camera offline, missing feed, or stale observation.
  5. `HUMAN_VERIFICATION_REQUIRED`: Anomaly detected; manual review requested.

> [!WARNING]
> A negative image classification (`NO_CURRENT_FLOOD_EVIDENCE`) **MUST NEVER** be interpreted as proof that a road is safe for vehicular passage. Rapid flash flooding, upstream drain blockages, and nighttime hazards require physical verification.
