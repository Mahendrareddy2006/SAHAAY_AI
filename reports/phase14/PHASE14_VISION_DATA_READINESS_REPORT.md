# Sahaay AI — Phase 14: Vision Data Readiness and Evaluation Audit Report

**Audit Date:** 2026-10-27  
**Branch:** `feat/phase12-architecture-audit-and-data-contracts`  
**HEAD Commit:** `dbb5793` (*merge: incorporate Phase 12 contracts and Phase 13 rainfall ingestion pipeline*)  
**Working Tree Status:** Clean (preserved all Phase 12 contracts and Phase 13 rainfall ingestion work; no code modified; no model checkpoints altered; no dependencies installed)  
**Operational Safety Directive:** **STRICTLY NON-AUTONOMOUS / ADVISORY ONLY**. Zero claim of validated Hyderabad flood prediction or live-pilot readiness.

---

## Executive Summary & Formal Gate Decisions

This audit establishes whether the existing flood-vision datasets, manifests, and evaluation cohorts are suitable for defensible Vision V4 deep learning training and independent operational evaluation.

```
========================================================================================
PHASE 14 AUDIT DECISION MATRIX
========================================================================================
1. Vision V4 Model Training Decision    : NO-GO (Training Blocked)
2. Independent Evaluation Defensibility : DEFENSIBLE INDEPENDENT EVALUATION SET ABSENT
3. Operational Safety Status            : LAB / RESEARCH ONLY (No Live Deployment)
========================================================================================
```

### Core Audit Findings:
1. **Source-Label Confounding Remains Absolute ($V = 1.0000$):** In all available curated road datasets (Manifests V3 and V4), positive flood imagery originates exclusively from Clemson University ($N=739$), while negative road imagery originates exclusively from Virenbr11 ($N=739$). Zero sources contain both classes.
2. **Metadata Shortcuts Outperform Random Chance Without Pixels:** A non-semantic Random Forest classifier trained solely on metadata (`file_size_kb`, `width`, `height`, `aspect_ratio`) achieves **85.97% test accuracy** (ROC-AUC: 0.9066). A single-feature decision stump on `file_size_kb` alone achieves **80.09% test accuracy**. Neural networks trained on these splits learn low-level camera and compression signatures rather than water surface physics.
3. **Historical Test Set Reuse & Exhaustion:** The reserved Test V3 split ($N=222$) was repeatedly used for model selection, augmentation tuning, and threshold calibration across Phases 3, 9, 10, and 11. It can no longer serve as an unbiased, held-out evaluation set.
4. **Zero Authorized Real-World Hyderabad Street Observations:** The master acquisition register ([`data/collection_v4/acquisition_register.csv`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/collection_v4/acquisition_register.csv)) contains exactly **0 real-world street observations** (3 synthetic test fixtures). All four candidate acquisition streams in [`data/collection_v4/permission_register.csv`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/collection_v4/permission_register.csv) remain unapproved (2 pending, 2 not started).
5. **No Defensible Evaluation Cohort Exists:** Every existing evaluation candidate is either single-class (Clemson 200), contaminated by historical duplicate leakage (V1/V2), perfectly source-confounded (V3/V4), or aerial/inaccessible (FloodNet, EU-Flood).
6. **Existing Model Checkpoints Retained for Research Only:** Historical checkpoints (`model_v1`, `model_v2`, `model_v3_clean`, `model_v3_monsoon`) are documented and preserved. `model_v3_monsoon` remains the best available advisory prototype under severe weather augmentations, but its metrics reflect an artificial laboratory benchmark, not real-world Hyderabad operational reliability.

---

## 1. Dataset Inventory & Provenance (Phase 14.1)

An exhaustive audit of local directories, Kagglehub caches, manifests, and scripts was performed to establish empirical counts, provenance, and license boundaries.

### 1.1 Checkpoint Inventory & Cryptographic Hashes
All four historical vision model checkpoints were located, verified, and hashed:

| Checkpoint Identifier | File Location | File Size (Bytes) | Size (MB) | MD5 Checksum | Historical Evaluation Status & Known Vulnerability |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **`mobilenet_v3_small_v1`** | [`models/vision/best_model.pt`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/best_model.pt) | 18,493,276 | 17.64 MB | `82b57acf92942266b4a6a26713515ee4` | **Disqualified:** Contaminated by 23 train-test exact duplicate MD5 leaks; negatives contain non-road objects (pets, rooms). |
| **`mobilenet_v3_small_v2`** | [`models/vision/v2/model_v2.pt`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v2/model_v2.pt) | 18,493,276 | 17.64 MB | `88e117abbc123bd6299e22c6374bd8c7` | **Disqualified:** Collapsed to 53.15% on road benchmark; 94.0% False Positive Rate on dry roads due to 100% 224x224 thumbnail shortcut. |
| **`mobilenet_v3_small_v3_clean`** | [`models/vision/v3/model_v3_clean.pt`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v3/model_v3_clean.pt) | 18,493,276 | 17.64 MB | `b553eee151c66f96b809204a638fd30e` | **Research Baseline:** 97.30% accuracy on Test V3; vulnerable to rain spray degradation (93.24% acc, 13.51% FNR). Underlying data source-confounded. |
| **`mobilenet_v3_small_v3_monsoon`** | [`models/vision/v3/model_v3_monsoon.pt`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v3/model_v3_monsoon.pt) | 18,493,276 | 17.64 MB | `818ae953fc264badf86e14e08bf9f26b` | **Advisory Research Only:** 97.75% accuracy on Test V3; 96.85% under rain blur; low ECE (0.0237). Retained strictly for advisory shadow mode. |

### 1.2 Local Raw Image Repositories & Caches

| Source Identifier | Local Path | Total Files | Image Count | Ground Truth Class | Native Perspective & Camera Types | Confirmed License & Usage Rights |
| :--- | :--- | :---: | :---: | :---: | :--- | :--- |
| **`roham1_flood`** | `~/.cache/kagglehub/.../roham1/.../Flood` | 1,500 | 1,500 | Flooded (1) | Mixed ground-level, aerial, and rescue scenes | ODbL / Kaggle Open Dataset (web scrape) |
| **`roham1_non_flood`** | `~/.cache/kagglehub/.../roham1/.../Non_Flood` | 1,500 | 1,500 | Non-Flooded (0) | Arbitrary objects (indoor rooms, portraits, cats); all $224 \times 224$ thumbnails | ODbL / Kaggle Open Dataset (web scrape) |
| **`clemson_flood`** | `~/.cache/kagglehub/.../hhrclemson/.../Flood Images` | 9,296 | 9,296 | Flooded (1) | Ground-level roads, DOT traffic cams, Twitter/X storm posts | Academic Research / Open Access (Data in Brief 2023) |
| **`virenbr11_plain`** | `~/.cache/kagglehub/.../virenbr11/.../Plain` | 366 | 366 | Non-Flooded (0) | Vehicle dashcam & smartphone road pavement inspection | Open Database License (ODbL) |
| **`virenbr11_pothole`** | `~/.cache/kagglehub/.../virenbr11/.../Pothole` | 357 | 357 | Non-Flooded (0) | Vehicle dashcam & smartphone road pavement inspection | Open Database License (ODbL) |
| **`collection_v4_raw`** | [`data/collection_v4/raw`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/collection_v4/raw) | 0 | 0 | None | Intended: GHMC CCTV, citizen upload, field crew, dashcam | 0 approved permissions (quarantined) |
| **`floodnet`** | `C:\Users\MahendraReddy\Downloads\...` | 2 | 1 sample | Multi-class segmentation | High-altitude aerial drone (DJI Mavic Pro); nadir perspective | CDLA-Permissive-1.0 (code repo only; raw archives missing) |
| **`eu_flood`** | `C:\Users\MahendraReddy\Downloads\...` | 2 | 1 sample | Image retrieval | Central European street-level photos | CC BY-SA 3.0 (metadata only; Wikimedia URLs return HTTP 403) |

### 1.3 Manifest Versions & Split Partition Inventory

| Manifest Version | Full Manifest Path | Total Rows | Train Count | Val Count | Test Count | Class Balance (Train / Val / Test) | Sources Included |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Manifest V1** | [`data/processed/full_manifest.csv`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/processed/full_manifest.csv) | 3,000 | 2,100 | 450 | 450 | $50\% / 50\%$ across all splits | `roham1_binary_ground` (3,000) |
| **Manifest V2** | [`data/processed/manifest_v2/full_manifest_v2.csv`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/processed/manifest_v2/full_manifest_v2.csv) | 3,000 | 2,100 | 450 | 450 | $50\% / 50\%$ across all splits | `roham1_binary_ground` (3,000) |
| **Manifest V3** | [`data/processed/manifest_v3/full_manifest_v3.csv`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/processed/manifest_v3/full_manifest_v3.csv) | 1,478 | 1,034 | 222 | 222 | $50\% / 50\%$ across all splits | Clemson (739), Viren Plain (374), Viren Pothole (365) |
| **Manifest V4** | [`data/processed/manifest_v4/full_manifest_v4.csv`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/processed/manifest_v4/full_manifest_v4.csv) | 1,478 | 1,034 | 223 | 221 | Tr: 517/517; Val: 112/111; Te: 110/111 | Clemson (739), Viren Plain (374), Viren Pothole (365) |

---

## 2. Leakage and Confounding Audit (Phase 14.2)

### 2.1 Cryptographic (MD5) Duplicate Leakage Across Splits
Using [`scripts/audit_phase14_vision_data_readiness.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/scripts/audit_phase14_vision_data_readiness.py), every image path across all historical and current manifests was cryptographically hashed:

```
Exact MD5 Cross-Split Overlap Audit:
├── Manifest V1 (Initial Baseline Split):
│   ├── Train ∩ Val  : 17 exact duplicate image pairs
│   ├── Train ∩ Test : 23 exact duplicate image pairs  <-- SEVERE LEAKAGE (Explains 100% test accuracy)
│   └── Val ∩ Test   : 3 exact duplicate image pairs
├── Manifest V2 (Deduplicated Clean Split):
│   ├── Train ∩ Val  : 0 pairs (PASS)
│   ├── Train ∩ Test : 0 pairs (PASS)
│   └── Val ∩ Test   : 0 pairs (PASS)
├── Manifest V3 (Road & Pothole Balanced Split):
│   ├── Train ∩ Val  : 0 pairs (PASS)
│   ├── Train ∩ Test : 0 pairs (PASS)
│   └── Val ∩ Test   : 0 pairs (PASS)
└── Manifest V4 (Globally Clustered Split):
    ├── Train ∩ Val  : 0 pairs (PASS)
    ├── Train ∩ Test : 0 pairs (PASS)
    └── Val ∩ Test   : 0 pairs (PASS)
```

### 2.2 Perceptual Near-Duplicate Leakage (dhash Hamming Distance $\le 2$)
While Manifest V3 eliminated exact byte-level MD5 leaks, audit of perceptual 64-bit difference hashes revealed multi-frame burst and CCTV video capture overlap crossing split boundaries:

| Manifest Split Comparison | Near-Duplicate Pairs ($d_H \le 2$) | Cross-Split Violation Status | Root Cause |
| :--- | :---: | :---: | :--- |
| **Manifest V3: Train $\cap$ Test** | **7 pairs** | **LEAKAGE DETECTED** | Sequential CCTV frames from Clemson storm events split across Train and Test |
| **Manifest V3: Train $\cap$ Val** | **4 pairs** | **LEAKAGE DETECTED** | Sequential burst photography from same flood scene split across Train and Val |
| **Manifest V3: Val $\cap$ Test** | **5 pairs** | **LEAKAGE DETECTED** | Identical scene cameras split across Val and Test |
| **Manifest V4: Train $\cap$ Test** | **0 pairs** | **ZERO LEAKAGE (PASS)** | Resolved via global single-linkage clustering at $d_H \le 2$ |
| **Manifest V4: Train $\cap$ Val** | **0 pairs** | **ZERO LEAKAGE (PASS)** | Resolved via global single-linkage clustering at $d_H \le 2$ |
| **Manifest V4: Val $\cap$ Test** | **0 pairs** | **ZERO LEAKAGE (PASS)** | Resolved via global single-linkage clustering at $d_H \le 2$ |

#### Verification of the 5 Historical Clemson Leak Pairs in V3
Audited via [`scripts/verify_v3_leak_pairs.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/scripts/verify_v3_leak_pairs.py):
1. Test `v3_00914` (`flood_7940.png`) vs Train `v3_00486` (`flood_7963.png`): $d_H = 1$ bit (near duplicate).
2. Test `v3_00116` (`flood_7210.png`) vs Train `v3_01247` (`flood_9328.png`): $d_H = 0$ bits (perceptual clone).
3. Test `v3_00116` (`flood_7210.png`) vs Train `v3_00706` (`flood_7283.png`): $d_H = 1$ bit (near duplicate).
4. Test `v3_00236` (`flood_7295.png`) vs Train `v3_01247` (`flood_9328.png`): $d_H = 1$ bit (near duplicate).
5. Test `v3_00834` (`flood_7186.png`) vs Train `v3_00141` (`flood_7184.png`): $d_H = 2$ bits (near duplicate).

In Manifest V4, all five pairs and their transitive closure components were merged into unified clusters (`cluster_id`) and assigned atomically to single splits, eliminating cross-split near-duplicate contamination.

### 2.3 Source-Label Confounding Audit
In both Manifest V3 and Manifest V4, source dataset identity is **strictly collinear** with the ground truth classification label:

#### Source $\times$ Label Contingency Matrix ([`reports/phase14/phase14_vision_data_audit.json`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/phase14/phase14_vision_data_audit.json))
```csv
source_dataset,label_0 (non_flood),label_1 (flooded),total,flood_ratio
clemson_flood,0,739,739,1.0000 (100.0%)
virenbr11_plain,374,0,374,0.0000 (0.0%)
virenbr11_pothole,365,0,365,0.0000 (0.0%)
Total,739,739,1478,0.5000 (50.0%)
```

- **Cramér's $V$:** **`1.0000`** *(Project Gate Threshold: $\le 0.30$)* $\implies$ **FAILED**.
- **Mutual Information $I(\text{Source}; \text{Label})$:** **`1.0000 bits`** *(Gate Threshold: $\le 0.20\text{ bits}$)* $\implies$ **FAILED**.
- **Uncertainty Coefficient:** **`1.0000`** *(Source identity perfectly determines label).*
- **Cross-Source Representation:** **0 sources** contribute both flooded and non-flooded images.

### 2.4 Non-Semantic Metadata Shortcut Diagnostics
Because Clemson cameras and scraping pipelines operated differently from Virenbr11 road pavement cameras, non-semantic image properties (file dimensions, aspect ratios, JPEG compression file sizes) contain strong label shortcuts.

Diagnostic machine learning classifiers were evaluated on Manifest V4 without observing image pixels:

| Diagnostic Model | Input Features | Train Accuracy | Test Accuracy ($N=221$) | Macro-F1 | Test ROC-AUC | Gate Limit |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Decision Stump (Depth 1)** | `file_size_kb` only | $80.85\%$ | **$80.09\%$** | $0.7885$ | $0.8280$ | $\le 65.0\%$ (**FAILED**) |
| **Decision Tree (Depth 2)** | `width`, `height` | $68.47\%$ | **$67.42\%$** | $0.6129$ | $0.7583$ | $\le 65.0\%$ (**FAILED**) |
| **Random Forest (100 trees, depth 4)** | `file_size_kb`, `width`, `height`, `aspect_ratio` | $86.56\%$ | **$85.97\%$** | **$0.8426$** | **$0.9066$** | $\le 65.0\%$ (**FAILED**) |

#### Feature Importances in Non-Semantic Random Forest:
- **`file_size_kb`:** **$54.17\%$** (Clemson flood mean = $1,215.4\text{ KB}$ vs Virenbr11 non-flood mean = $328.7\text{ KB}$; $3.7\times$ larger).
- **`width`:** **$24.61\%$** (Clemson mean = $1,375.1\text{px}$ vs Virenbr11 mean = $983.4\text{px}$).
- **`height`:** **$14.99\%$** (Clemson mean = $918.9\text{px}$ vs Virenbr11 mean = $646.1\text{px}$).
- **`aspect_ratio`:** **$6.23\%$**.

**Scientific Implication:** Any standard convolutional network (e.g. MobileNetV3, ResNet) will inevitably latch onto low-frequency JPEG compression artifacts, high-frequency camera noise profiles, and aspect-ratio resampling boundaries. Reported high accuracy does not validate water detection.

---

## 3. Representativeness & Label Quality (Phase 14.3)

### 3.1 Road Scene & Environmental Attribute Representation

| Scene / Environmental Condition | Representation in Manifest V4 | Source(s) | Quality & Realism Assessment | Operational Risk if Deployed |
| :--- | :---: | :--- | :--- | :--- |
| **Inundated Roads (Curb submersion)** | 739 images | Clemson FloodIMG | Authentic street floods; predominantly US highways and residential streets | Overfits to US road infrastructure; lacks Indian monsoon urban density |
| **Dry Asphalt Roads** | 374 images | Virenbr11 Plain | Clean, well-paved highway surfaces; distinct camera angle | Lacks typical Hyderabad road textures, debris, lane encroachments |
| **Wet Asphalt Without Inundation** | Partially present | Virenbr11 Pothole | Wet patches around cracks; no heavy standing water | Good negative control, but camera sensor is entirely disjoint from flood set |
| **Puddles & Potholes (Hard Negatives)** | 365 images | Virenbr11 Pothole | Shallow puddles, water-filled potholes | Excellent hard negatives, but compressed differently from floods |
| **Reflections & Wet Glare** | Rare | Clemson / Virenbr11 | Occasional sky reflections on wet asphalt | High false-positive trigger risk under streetlights |
| **Nighttime & Severe Storm Darkness** | Very rare ($<2\%$) | Clemson | Few overcast storm scenes; almost 0 night scenes | High false-negative risk during night monsoon downpours |
| **Indian Monsoon Streetscapes** | **0 images** | None | **Completely Absent** (0 auto-rickshaws, 0 bilingual signs, 0 open drains) | Severe domain shift; unvalidated on local Hyderabad corridors |

### 3.2 Distinction Between Visual Classes and Hydrological Ground Truth
The audit verified that no physical water depth measurements exist in any available image dataset.
- In accordance with [`src/sahaay/vision/policy.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/vision/policy.py), visual classifications must remain strictly labeled as `FLOOD_EVIDENCE_DETECTED` or `NO_CURRENT_FLOOD_EVIDENCE`.
- Visual inference **must never** be used to infer millimeter water depth or road passability without direct physical telemetry (e.g. ultrasonic depth sensors, gauge boards, or verified field responder reports).

---

## 4. Evaluation Readiness & Checkpoint Limitations (Phase 14.4)

### 4.1 Historical Checkpoint Metric Limitations

#### 1. `mobilenet_v3_small_v1` (Phase 1):
- **Historical Claim:** $100.0\%$ test accuracy on Manifest V1.
- **Audit Reality:** Contaminated by 23 exact duplicate MD5 leaks across Train and Test splits. Non-flood images were arbitrary web-scraped images (pets, bedrooms). Generalization to real roads is zero.

#### 2. `mobilenet_v3_small_v2` (Phase 2):
- **Historical Claim:** $100.0\%$ test accuracy on Manifest V2 (after deduplication).
- **Audit Reality:** The model learned a 100% dimensional shortcut ($224 \times 224$ thumbnails for non-flood vs $>800\text{px}$ for flood). When evaluated on unseen real roads in Test V3, it collapsed to **53.15% accuracy**, triggering a **94.0% False Positive Rate on dry asphalt** (misclassifying 47 of 50 dry roads as flooded).
- **The Positive Recall Fallacy:** While V2 achieved $100\%$ positive recall on floods, it did so by predicting virtually every image was flooded. In municipal dispatch, this causes immediate alarm fatigue.

#### 3. `mobilenet_v3_small_v3_clean` (Phase 3):
- **Historical Claim:** $97.30\%$ accuracy on Test V3.
- **Audit Reality:** Good hard-negative specificity on puddles (98.36%), but degrades significantly under simulated rain mist blur (93.24% acc, 13.51% false negative rate). Furthermore, Test V3 is confounded by source and contains near-duplicate leaks to Train V3.

#### 4. `mobilenet_v3_small_v3_monsoon` (Phase 3):
- **Historical Claim:** $97.75\%$ accuracy on Test V3, $100\%$ specificity on dry roads, $96.85\%$ accuracy under synthetic rain blur.
- **Audit Reality:** While physically regularized and exhibiting low calibration error ($\text{ECE} = 0.0237$), its metrics reflect performance on a source-confounded split that has been evaluated repeatedly. It cannot be claimed as validated for Hyderabad road corridors.

### 4.2 Defensibility Audit of Candidate Evaluation Cohorts

| Candidate Evaluation Cohort | Sample Size ($N$) | Positive / Negative Composition | Independent Source Status | Defensibility Verdict |
| :--- | :---: | :---: | :--- | :--- |
| **Test V1 (`test.csv`)** | 450 | 225 Flood / 225 Non-Flood | Same web scrape as Train V1 | **NOT DEFENSIBLE:** 23 exact MD5 leaks; non-road negatives. |
| **Test V2 (`test_v2.csv`)** | 450 | 225 Flood / 225 Non-Flood | Same web scrape as Train V2 | **NOT DEFENSIBLE:** 100% thumbnail shortcut. |
| **Test V3 (`test_v3.csv`)** | 222 | 111 Flood / 111 Non-Flood | Clemson Floods + Virenbr11 Negatives | **NOT DEFENSIBLE:** 7 near-duplicate leaks with Train; $V = 1.0$; reused repeatedly. |
| **Test V4 (`test_v4.csv`)** | 221 | 110 Flood / 111 Non-Flood | Clemson Floods + Virenbr11 Negatives | **NOT DEFENSIBLE:** Leakage-free, but $V = 1.0$; metadata classifier achieves 85.97%. |
| **Clemson 200 (Historical Eval)** | 200 | 200 Flood / 0 Non-Flood | Clemson FloodIMG | **NOT DEFENSIBLE:** Positive-only; overlaps with Train V1 (36 MD5s) & Train V2 (37 MD5s). |
| **EU-Flood / FloodNet** | 1 usable | Aerial or 403 Forbidden | External archives missing locally | **NOT DEFENSIBLE:** Inaccessible or severe perspective mismatch. |
| **Hyderabad Collection V4** | 0 real | 0 real images acquired | GHMC CCTV / Field team | **NOT DEFENSIBLE:** Collection has not commenced (0 real images). |

**Formal Conclusion:** **NO DEFENSIBLE INDEPENDENT EVALUATION SET CURRENTLY EXISTS IN THE REPOSITORY.**

---

## 5. Formal Gate Decisions & Prerequisites

### 5.1 Vision V4 Training Gate Decision: **NO-GO**

```
========================================================================================
DECISION: NO-GO FOR VISION V4 MODEL TRAINING
========================================================================================
Readiness Evaluation Tool: scripts/check_v4_data_readiness.py
Exit Status: BLOCKED (NO-GO)

Active Blocking Reasons:
[X] 1. ZERO authorized real-world observations acquired in data/collection_v4/ (0 images).
[X] 2. Severe source-label confounding active across all road data (Cramér's V = 1.0000 > 0.30).
[X] 3. Non-semantic metadata Random Forest achieves 85.97% test accuracy (> 65.0% threshold).
[X] 4. Insufficient multi-source representation: 0 sources provide both classes >= 100 images
       (requires >= 2 independent balanced sources).
[X] 5. Zero acquisition streams have approved legal/governance permissions (2 pending, 2 not started).
========================================================================================
```

### 5.2 Independent Evaluation Readiness Decision: **NOT READY**
No independent evaluation benchmark can be defended until multi-source balanced road data from the deployment geography (Hyderabad) is acquired and held out under strict key-lock isolation.

### 5.3 Explicit Prerequisites to Unlock Vision V4 Training:
Before Vision V4 training can be authorized, the following evidence must be committed to the repository:
1. **Multi-Source Road Representation:** At least **two (2) independent image sources** must each contribute both flooded and non-flooded road scenes (minimum 200 real-world street images per class across sources).
2. **Confounding Suppression:** Cramér's $V$ between source identity and classification label must satisfy $V \le 0.30$, and mutual information $I(\text{Source}; \text{Label}) \le 0.20\text{ bits}$.
3. **Metadata Shortcut Ceiling:** A non-semantic Random Forest trained on image metadata must achieve **$\le 65.0\%$ test accuracy** on the candidate training split.
4. **Legal & Governance Authorization:** At least one municipal or research data stream (e.g. STREAM-01 GHMC CCTV or STREAM-03 Field Crew) must achieve formal `approved` status with an archived consent/MOU agreement reference.
5. **Zero Split Leakage:** Complete cryptographic ($d_H = 0$) and near-duplicate ($d_H \le 2$) disjointness across all splits, verified by exhaustive $N \times N$ clustering.

---

## 6. Prioritized Data Acquisition Plan (Phase 14.4.9)

To close the identified data readiness gaps, acquisition must prioritize balanced classes from shared sensors in the target operational environment:

```mermaid
flowchart TD
    subgraph Stream_01["STREAM-01: GHMC & Traffic Police CCTV"]
        A1["Fixed Road CCTV Feeds (4 Pilot Corridors)"] --> A2["Collect Dry Weather Baseline (Class 0)"]
        A1 --> A3["Collect Monsoon Downpour Inundation (Class 1)"]
        A2 & A3 --> A4["Shared Camera Sensor (Zero Source Shortcut)"]
    end

    subgraph Stream_03["STREAM-03: Field-Team Ground Vantage"]
        B1["Dedicated Research Field Crews"] --> B2["Dry Asphalt & Normal Traffic (Class 0)"]
        B1 --> B3["Wet Asphalt, Puddles & Potholes (Hard Negatives)"]
        B1 --> B4["Active Waterlogging & Curb Submersion (Class 1)"]
        B2 & B3 & B4 --> B5["Calibrated Smartphone Cameras"]
    end

    A4 & B5 --> C["Automated Privacy & Quality Pipeline"]
    C --> D["Face & License Plate Redaction (Blurred-Verified)"]
    D --> E["Image Quality Gate (Luminance, Blur, Resolution)"]
    E --> F["Dual-Blind Human Annotation (Cohen's Kappa >= 0.85)"]
    F --> G["Defensible Vision V4 Dataset & Held-Out Test Set"]
```

### Prioritized Acquisition Phases:

| Priority | Acquisition Stream | Target Corridors | Target Sample Intake | Class Balance Target | Governance Prerequisite |
| :---: | :--- | :--- | :---: | :---: | :--- |
| **P1** | **STREAM-01: Municipal CCTV** | Tolichowki Flyover Underpass, Shaikpet Main Road, Musi River Causeway | 600 frames (150 per corridor) | $50\%$ Dry / $50\%$ Inundated from identical cameras | GHMC / Traffic Police Data Access Agreement |
| **P2** | **STREAM-03: Field Team Ground Vantage** | Gachibowli-ORR Junction, Tolichowki, Lakdikapul | 400 photos | 200 Flooded / 100 Dry / 100 Wet Potholes | Field Safety Protocol sign-off & PPE procurement |
| **P3** | **STREAM-02: Citizen Upload Portal** | City-wide community reporting | Ad-hoc (quarantined) | Organic community distribution | Terms of Service & explicit consent flow deployment |
| **P4** | **STREAM-04: Commercial Fleet Dashcam** | Public transit / delivery routes | 1,000 video snippets | Natural driving distribution | Bilateral fleet data agreement |

---

## 7. Audit Verification & Test Execution Summary (Phase 14.4.10)

The entire automated test suite and diagnostic scripts were executed using `.venv\Scripts\pytest` with `PYTHONPATH="."`:

### 7.1 Test Suite Execution Results

```
========================================================================================
FULL TEST SUITE EXECUTION SUMMARY
Command: $env:PYTHONPATH="."; .\.venv\Scripts\pytest -q
Collected Tests: 288 tests across 23 modules
Result: 284 PASSED, 4 FAILED, 6 WARNINGS (Duration: 16.72s)
========================================================================================
```

#### Detailed Test Module Breakdown:

| Test Module File | Category / Domain | Total Tests | Passed | Failed | Error / Failure Rationale |
| :--- | :--- | :---: | :---: | :---: | :--- |
| [`tests/test_vision_v4.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_vision_v4.py) | Vision V4 Integrity & Disjointness | 9 | 9 | 0 | All split disjointness and leak-pair unification tests PASS. |
| [`tests/test_vision_v4_collection.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_vision_v4_collection.py) | V4 Data Collection & Privacy | 15 | 15 | 0 | Privacy redaction, duplicate clustering, NO-GO gate tests PASS. |
| [`tests/test_vision_v4_phase3.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_vision_v4_phase3.py) | V4 Permissions & Onboarding | 7 | 7 | 0 | Zero unverified approvals, NO-GO gate tests PASS. |
| [`tests/test_vision_v3.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_vision_v3.py) | Vision V3 Regression & Policy | 10 | 10 | 0 | V3 baseline, quality gate, and advisory policy tests PASS. |
| [`tests/test_split_integrity.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_split_integrity.py) | Split Disjointness Unit Tests | 5 | 5 | 0 | V2 split disjointness tests PASS. |
| [`tests/test_phase9_split_and_audit.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_phase9_split_and_audit.py) | Phase 9 Split Integrity & ML Baselines | 8 | 8 | 0 | Exhaustive clustering and collinearity tests PASS. |
| [`tests/test_external_provenance_reconciliation.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_external_provenance_reconciliation.py) | External Provenance Reconciliation | 3 | 3 | 0 | Reconciled report and historical Clemson leaks PASS. |
| [`tests/test_model.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_model.py) | MobileNetV3 Architecture | 2 | 2 | 0 | Architecture creation tests PASS. |
| [`tests/test_dataset.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_dataset.py) | FloodDataset PyTorch Loader | 1 | 1 | 0 | Dataset loading tests PASS. |
| [`tests/test_transforms.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_transforms.py) | Transform Pipelines | 3 | 3 | 0 | Eval and monsoon transform shapes PASS. |
| [`tests/test_inference.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_inference.py) | FloodVisionInference Service | 3 | 3 | 0 | Checkpoint loading and prediction format PASS. |
| [`tests/test_phase12_data_contracts.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_phase12_data_contracts.py) | Phase 12 Data Contracts | 28 | 28 | 0 | Decision contracts and missingness tests PASS. |
| [`tests/test_phase13_contracts_and_mock.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_phase13_contracts_and_mock.py) | Phase 13 Pipeline & Contracts | 22 | 22 | 0 | Rainfall pipeline and freshness tests PASS. |
| [`tests/test_phase13_pipeline_integration.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_phase13_pipeline_integration.py) | Phase 13 Integration | 38 | 38 | 0 | Live pipeline integration tests PASS. |
| [`tests/test_phase13_provider_adapter.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_phase13_provider_adapter.py) | Phase 13 Provider Adapters | 20 | 20 | 0 | HTTP error handling and telemetry tests PASS. |
| [`tests/test_api_contract.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_api_contract.py) | REST API Schemas | 4 | 4 | 0 | API response schema tests PASS. |
| [`tests/test_phase6_pilot_readiness.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_phase6_pilot_readiness.py) | Phase 6 Governance & Observations | 13 | 13 | 0 | Truthful zero real observations tests PASS. |
| [`tests/test_phase7_pilot_activation.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_phase7_pilot_activation.py) | Phase 7 Gate & Field Safety | 11 | 11 | 0 | Activation gate fail-closed tests PASS. |
| [`tests/test_phase8_blockers_and_intake.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_phase8_blockers_and_intake.py) | Phase 8 Blocker Lifecycle | 11 | 11 | 0 | Blocker closure and intake tests PASS. |
| [`tests/test_phase10_risk_baselines.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_phase10_risk_baselines.py) | Phase 10 Risk Rule Baselines | 9 | 9 | 0 | Deterministic scoring baselines PASS. |
| [`tests/test_image_quality_gate.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_image_quality_gate.py) | Image Quality Gate Unit Tests | 5 | 3 | **2** | **FAILED (2):** `test_borderline_darkness_rejection` and `test_borderline_whiteout_rejection`. Synthetic solid-color test images run through `predict()` triggered the Phase 12 calibrated ambiguity band abstention ($p \in [0.35, 0.65]$). |
| [`tests/test_hyderabad_risk_pipeline.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_hyderabad_risk_pipeline.py) | Hyderabad Risk Pipeline | 32 | 31 | **1** | **FAILED (1):** `test_decision_engine_synthesis`. Historical test asserted `WATCH`, but Phase 12 safety contracts cap unverified single-source risk at `ADVISORY`. |
| [`tests/test_phase5_integration.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_phase5_integration.py) | Phase 5 Integration & Decision | 16 | 15 | **1** | **FAILED (1):** `test_decision_engine_modeled_risk_vs_observed_flooding`. Historical test asserted `WATCH`, but Phase 12 safety contract requires field confirmation before `WATCH`. |

### 7.2 Dedicated Phase 14 Audit Commands Executed

1. **Phase 14 Comprehensive Audit Script:**
   ```powershell
   $env:PYTHONPATH="."; .\.venv\Scripts\python scripts/audit_phase14_vision_data_readiness.py
   ```
   *Result:* Exited 0. Generated [`reports/phase14/phase14_vision_data_audit.json`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/phase14/phase14_vision_data_audit.json).
2. **Pre-Flight Readiness Gate Check:**
   ```powershell
   $env:PYTHONPATH="."; .\.venv\Scripts\python scripts/check_v4_data_readiness.py --output-report reports/phase14/v4_readiness_gate_report.json
   ```
   *Result:* Exited 1 (Gate status `NO-GO`). Generated [`reports/phase14/v4_readiness_gate_report.json`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/phase14/v4_readiness_gate_report.json).
3. **Cryptographic Checkpoint Verification:**
   ```powershell
   Get-FileHash -Algorithm MD5 models/vision/best_model.pt, models/vision/v2/model_v2.pt, models/vision/v3/model_v3_clean.pt, models/vision/v3/model_v3_monsoon.pt
   ```
   *Result:* All 4 checkpoints intact; sizes and hashes verified.
4. **Metadata Diagnostic Baseline Reproduction:**
   ```powershell
   $env:PYTHONPATH="."; .\.venv\Scripts\python -c "import pandas as pd; from sklearn.ensemble import RandomForestClassifier; ..."
   ```
   *Result:* Reproduced 85.97% test accuracy on non-semantic features on Manifest V4.

---

## 8. Summary of Handover & Repository Invariants

1. **Zero Uncommitted Phase 13 Code Modified:** The working tree remains clean; only new audit artifacts under [`reports/phase14/`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/phase14) and [`scripts/audit_phase14_vision_data_readiness.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/scripts/audit_phase14_vision_data_readiness.py) were created.
2. **No Model Checkpoints Modified:** Checkpoints V1, V2, V3 Clean, and V3 Monsoon remain identical to Phase 11.
3. **No Training Executed:** Vision V4 model training was strictly blocked and NOT run.
4. **Operational Safety Statement:** Sahaay AI does **not** have a live-deployable or field-validated vision flood prediction model. `model_v3_monsoon` is an advisory research baseline for shadow-mode testing with human-in-the-loop verification only.
