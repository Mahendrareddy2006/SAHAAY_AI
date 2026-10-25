# Sahaay AI — Vision V4 Experiment Plan & Dataset Preparation

## Executive Summary & Audit Mandate

This document establishes the dataset architecture, forensic integrity baseline, and experimental protocol for **Sahaay AI Flood Vision V4**. It directly addresses the empirical vulnerabilities identified in [`docs/vision_v3_final_audit.md`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/docs/vision_v3_final_audit.md), specifically:
1. Cross-split near-duplicate leakage in historical V3 splits caused by sliding-window clustering limitations.
2. Complete source-label entanglement between positive instances (Clemson University FloodIMG) and negative instances (Virenbr11 Road Pavement).
3. Confounding of non-semantic metadata (image dimensions and file size) which allows a pixel-free decision tree to achieve 85.97% classification accuracy.
4. Non-transparent confidence and abstention thresholds set by heuristic convention rather than constrained optimization on validation data.

### Immutable Safeguards & Historical Preservation
All historical checkpoints (`models/vision/best_model.pt`, `models/vision/v2/model_v2.pt`, `models/vision/v3/*.pt`), historical manifests (`data/processed/*.csv`, `manifest_v2/`, `manifest_v3/`), and past audit reports remain strictly preserved and unaltered. All V4 artifacts, manifests, and reports are written to independent, versioned paths.

---

## Phase 1 — Preservation and Forensic Audit of V3 Leak Pairs

### 1.1 Historical Artifact Preservation Confirmation
- Historical model checkpoints: `models/vision/best_model.pt` (V1 Baseline), `models/vision/v2/model_v2.pt` (V2 Clean), and `models/vision/v3/model_v3_monsoon.pt` remain unchanged on disk.
- Historical manifests: `data/processed/train.csv`, `val.csv`, `test.csv`, and all subdirectories under `manifest_v2/` and `manifest_v3/` are untouched.
- No files were deleted, renamed, or overwritten.

### 1.2 Identification & Verification of the Five V3 Test/Train Leak Pairs
The V3 audit in [`docs/vision_v3_final_audit.md`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/docs/vision_v3_final_audit.md) documented that 5 perceptual near-duplicate image pairs ($h \le 2$) crossed between `test_v3.csv` and `train_v3.csv`. Using the forensic verification script [`scripts/verify_v3_leak_pairs.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/scripts/verify_v3_leak_pairs.py), every image was verified on disk, re-hashed (MD5 and 64-bit difference hash `dhash`), and compared pairwise:

| Pair # | Split A (Test V3) | Image File A | Native Dimensions | Cryptographic MD5 A | Split B (Train V3) | Image File B | Cryptographic MD5 B | dhash Hamming Dist ($h$) | Verification Status |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1** | `test_v3` (`v3_00914`) | `flood_7940.png` | $800 \times 450$ | `976475dfe42422504ede39343fe748e3` | `train_v3` (`v3_00486`) | `flood_7963.png` | `a4b52e569cc7385dbb37196c36ab1154` | **$h = 1$ bit** | Verified Near-Duplicate |
| **2** | `test_v3` (`v3_00116`) | `flood_7210.png` | $1280 \times 720$ | `764cd4b7dad05e6880f9c22b3410d1d2` | `train_v3` (`v3_01247`) | `flood_9328.png` | `da3453516ef8a7c4d7a92a045f78e7f3` | **$h = 0$ bits** | Verified Visual Exact Clone |
| **3** | `test_v3` (`v3_00116`) | `flood_7210.png` | $1280 \times 720$ | `764cd4b7dad05e6880f9c22b3410d1d2` | `train_v3` (`v3_00706`) | `flood_7283.png` | `a2bba7b770bbf90fb6e3641d5cbc9c7a` | **$h = 2$ bits** | Verified Near-Duplicate |
| **4** | `test_v3` (`v3_00236`) | `flood_7295.png` | $1280 \times 720$ | `c3198cd2e0980b79321e77eced7c3779` | `train_v3` (`v3_01247`) | `flood_9328.png` | `da3453516ef8a7c4d7a92a045f78e7f3` | **$h = 1$ bit** | Verified Near-Duplicate |
| **5** | `test_v3` (`v3_00834`) | `flood_7186.png` | $1280 \times 720$ | `6a779cecc44f0b42ecee8484c57fb67a` | `train_v3` (`v3_00141`) | `flood_7184.png` | `0030d4fe2d43ebf1aaf38d8a2836e07a` | **$h = 2$ bits** | Verified Near-Duplicate |

#### Absolute File Paths on System:
- `flood_7940.png`: `C:\Users\MahendraReddy\.cache\kagglehub\datasets\hhrclemson\flooding-image-dataset\versions\5\Flood Images\flood_7940.png`
- `flood_7963.png`: `C:\Users\MahendraReddy\.cache\kagglehub\datasets\hhrclemson\flooding-image-dataset\versions\5\Flood Images\flood_7963.png`
- `flood_7210.png`: `C:\Users\MahendraReddy\.cache\kagglehub\datasets\hhrclemson\flooding-image-dataset\versions\5\Flood Images\flood_7210.png`
- `flood_9328.png`: `C:\Users\MahendraReddy\.cache\kagglehub\datasets\hhrclemson\flooding-image-dataset\versions\5\Flood Images\flood_9328.png`
- `flood_7283.png`: `C:\Users\MahendraReddy\.cache\kagglehub\datasets\hhrclemson\flooding-image-dataset\versions\5\Flood Images\flood_7283.png`
- `flood_7295.png`: `C:\Users\MahendraReddy\.cache\kagglehub\datasets\hhrclemson\flooding-image-dataset\versions\5\Flood Images\flood_7295.png`
- `flood_7186.png`: `C:\Users\MahendraReddy\.cache\kagglehub\datasets\hhrclemson\flooding-image-dataset\versions\5\Flood Images\flood_7186.png`
- `flood_7184.png`: `C:\Users\MahendraReddy\.cache\kagglehub\datasets\hhrclemson\flooding-image-dataset\versions\5\Flood Images\flood_7184.png`

### 1.3 Root Cause Analysis of the V3 Cluster Leak
The dataset preparation script `prepare_shortcut_resistant_v3.py` sorted images by perceptual hash and performed Union-Find clustering across a sliding window of $\text{window\_size} = 300$ adjacent candidates to bound computational complexity ($O(N \cdot W)$). However:
- Pairs like `flood_7210.png` (hash `c2c27192f06cdc34`) and `flood_9328.png` (hash `c2c27192f06cdc34`) had identical hashes but their sequence indices in the sort array were separated by more than 300 elements due to sorting tie-breakers and intervening hash patterns.
- Consequently, they were assigned to separate clusters and partitioned into different splits (`train_v3` vs `test_v3`).
- **Remediation in V4**: Eliminate windowing shortcuts. Perform an exhaustive global $N \times N$ pairwise Hamming distance comparison ($N=1,478$, producing $\approx 1.09 \times 10^6$ pairwise checks) so that every near-duplicate pair with $h \le 2$ is grouped into an atomic cluster prior to partitioning.

---

## Phase 2 — Source-Diverse Dataset Inventory & Domain Audit

*Machine-readable report: [`reports/vision_integrity/v4_dataset_inventory.json`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/vision_integrity/v4_dataset_inventory.json)*

A systematic inventory of all 7 available dataset repositories was conducted to assess license, provenance, ground-truth label validity, image dimensions, and road-domain relevance:

| Dataset Identifier | Source / Provenance | License | Class Balance | Available Images | Mean Resolution | Mean File Size | Domain Authenticity & Suitability |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **`virenbr11_plain`** | Kaggle Open Dataset (Road Pavement Surface) | ODbL / CC0 | Non-Flood Only | 375 | $291 \times 174$ | $6.8\text{ KB}$ | **Authentic Road Negatives**: Clean dry asphalt, curbs, painted road markings. |
| **`virenbr11_potholes`** | Kaggle Open Dataset (Road Pavement Surface) | ODbL / CC0 | Non-Flood Only | 365 | $663 \times 498$ | $141.0\text{ KB}$ | **Hard Negatives**: Wet asphalt, rain puddles, asphalt cracks without inundation. |
| **`clemson_floodimg`** | Karanjit et al., *Data in Brief* (2023) | CC-BY 4.0 / Academic | Flood Only | 9,296 | $1598 \times 1110$ | $1,193.1\text{ KB}$ | **Authentic Road Floods**: Street-level inundation from USGS/DOT cameras & social media. |
| **`roham1_flood`** | Kaggle Open Dataset (Web Scrape) | Community / ODbL | Flood Only | 1,500 | $1596 \times 1125$ | $1,357.8\text{ KB}$ | **Mixed Flood Imagery**: Real street floods, aerial rivers, emergency rescues. |
| **`roham1_non_flood`** | Kaggle Open Dataset (Web Scrape) | Community / ODbL | Non-Flood Only | 1,500 | $224 \times 224$ (Fixed) | $11.4\text{ KB}$ | **Defective / Confounded**: 100% fixed $224 \times 224$ thumbnails of indoor objects, animals, and landscapes (non-road). |
| **`FloodNet-Supervised`** | Code Repo in `Downloads/FloodNet-Supervised_v1.0-main` | Academic Non-Commercial | Incomplete | 1 (Code only) | N/A | N/A | **Incomplete**: Only code/metadata present; raw images require Google Drive download request. |
| **`eu-flood-dataset`** | Code Repo in `Downloads/eu-flood-dataset-master` | CC-BY-SA | Incomplete | 1 (Metadata only) | N/A | N/A | **Incomplete**: 3,500 Wikimedia Commons URLs; server scraping returned HTTP 403 Forbidden. |

### 2.1 Critical Finding on Source Confounding
Inspection of the inventory establishes that:
1. **ZERO sources contain both flooded and non-flooded road images at native resolutions.**
2. All genuine high-resolution road floods originate from `clemson_floodimg`.
3. All genuine road negatives (clean asphalt and hard-negative puddles/potholes) originate from `virenbr11`.
4. The only multi-class dataset (`roham1`) is severely confounded: its negative class consists of arbitrary $224 \times 224$ web thumbnails, while its positive class consists of megapixel flood photos.
5. Therefore, **source dataset identity and the binary flood label are 100% collinear across all available local imagery.**

---

## Phase 3 — Leakage & Source Shortcut Prevention in Manifest V4

*Machine-readable report: [`reports/vision_integrity/shortcut_diagnosis_v4.json`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/vision_integrity/shortcut_diagnosis_v4.json)*

### 3.1 Global $N \times N$ Perceptual Clustering
To prevent the recurrence of the sliding-window failure of V3:
1. All $N = 1,478$ candidate road images (739 Clemson road floods, 374 Virenbr11 plain roads, 365 Virenbr11 pothole hard-negatives) were indexed.
2. Full $N \times N$ pairwise Hamming distance was computed across 64-bit difference hashes (`dhash`).
3. Disjoint-Set Union-Find grouped all pairs with $h \le 2$ into atomic clusters.
4. Total clusters formed: **1,405 clusters** (1,348 singletons, 57 multi-image clusters containing 2 to 4 duplicate/near-duplicate frames).
5. Multi-image clusters were preserved atomically; all images belonging to a cluster were allocated strictly to the same partition.

### 3.2 Manifest V4 Partitioning
Clusters were stratified across Train (70%), Validation (15%), and Test (15%) partitions:

| Split Name | Manifest File | Flooded Road Images | Non-Flooded Plain Roads | Hard Negative Potholes | Total Non-Flood | Total Images ($N$) | Multi-Image Clusters |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Train V4** | [`train_v4.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/processed/manifest_v4/train_v4.csv) | 517 | 266 | 251 | 517 | **1,034** | 41 |
| **Validation V4** | [`val_v4.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/processed/manifest_v4/val_v4.csv) | 112 | 57 | 54 | 111 | **223** | 8 |
| **Test V4 (LOCKED)** | [`test_v4.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/processed/manifest_v4/test_v4.csv) | 110 | 52 | 59 | 111 | **221** | 8 |
| **Total V4** | [`full_manifest_v4.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/processed/manifest_v4/full_manifest_v4.csv) | **739** | **375** | **365** | **740** | **1,478** | **57** |

### 3.3 Proof of Zero Leakage Across Splits
An exhaustive verification audit of Manifest V4 was executed:
- **Exact Image ID Overlap**: **0 pairs** ($0.0\%$).
- **Exact MD5 Hash Overlap**: **0 pairs** ($0.0\%$).
- **Perceptual Near-Duplicate Overlap ($h \le 2$)**: **0 pairs** ($\min(h_{\text{cross-split}}) \ge 3$).
- **Resolution of Historical V3 Leak Pairs**:
  - `flood_7210.png`, `flood_7295.png`, `flood_7283.png`, `flood_9328.png` $\rightarrow$ Unified into **`cluster_v4_00116`** strictly within **`train_v4.csv`**.
  - `flood_7184.png`, `flood_7186.png` $\rightarrow$ Unified into **`cluster_v4_00141`** strictly within **`test_v4.csv`**.
  - `flood_7940.png`, `flood_7963.png` $\rightarrow$ Unified into **`cluster_v4_00479`** strictly within **`test_v4.csv`**.
  - **Zero cross-split leakage exists.**

### 3.4 Non-Semantic Metadata Diagnostic Baseline
To test whether the dataset allows shortcut learning, a decision tree / Random Forest classifier was trained on `train_v4.csv` and evaluated on `val_v4.csv` and `test_v4.csv` using strictly 4 non-semantic metadata features (`width`, `height`, `aspect_ratio`, `file_size_kb`) without looking at pixel values:

| Model Configuration | Features Used | Train Accuracy | Validation Accuracy | Test Accuracy | Test Precision | Test Recall | Test Macro-F1 | Test ROC-AUC |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`file_size_only`** | `file_size_kb` | 85.01% | 87.44% | **80.09%** | 83.67% | 74.55% | 0.7885 | 0.8280 |
| **`dimensions_only`** | `width`, `height` | 75.63% | 70.40% | **67.42%** | 75.00% | 51.82% | 0.6129 | 0.7583 |
| **`all_metadata_rf`** | `width`, `height`, `aspect_ratio`, `file_size_kb` | **88.10%** | **88.34%** | **85.97%** | **95.40%** | **75.45%** | **0.8426** | **0.9066** |

#### Gini Feature Importances:
- `file_size_kb`: **54.17%**
- `width`: **24.61%**
- `height`: **14.99%**
- `aspect_ratio`: **6.23%**

#### Implication:
Even with complete deduplication and split disjointness, **non-semantic metadata alone predicts the flood label with 85.97% test accuracy and an AUC of 0.9066**. This confirms that the Clemson vs Virenbr11 domain difference presents a severe shortcut opportunity for any computer vision model trained on this data.

---

## Phase 4 — Specification of Vision V4 Experiments

### 4.1 Training Pipeline & Preprocessing Protocol
- **Input Resolution**: $224 \times 224$ pixels.
- **Normalization**: Standard ImageNet mean $[0.485, 0.456, 0.406]$ and standard deviation $[0.229, 0.224, 0.225]$.
- **Monsoon Robustness Augmentation Suite**:
  - Random Horizontal Flip ($p = 0.50$).
  - Color Jitter ($p = 0.60$, brightness $= 0.30$, contrast $= 0.30$, saturation $= 0.30$) to simulate overcast sky turbidity.
  - Gaussian Blur ($p = 0.30$, kernel $= 3$, $\sigma \in [0.1, 2.0]$) to simulate windshield water droplet distortion.
- **Loss Function**: Focal Loss ($\gamma = 2.0$, $\alpha = 0.50$) to heavily penalize hard false positives on road potholes and reflections.
- **Optimizer**: AdamW ($\beta_1 = 0.9, \beta_2 = 0.999$, weight decay $= 10^{-4}$, initial learning rate $\eta = 10^{-4}$ with cosine annealing).
- **Candidate Architectures**:
  - `MobileNetV3-Small`: Low-latency mobile/edge inference (target deployment on citizen smartphones and traffic cameras).
  - `ResNet18`: High-capacity convolutional baseline for feature transfer comparison.
- **Random Seeds**: Deterministic seed `42` (`torch.manual_seed(42)`, `numpy.random.seed(42)`).

### 4.2 Validation-Only Threshold Tuning Protocol
Under no circumstances will the test set be accessed during threshold tuning or model selection:
1. The trained model produces continuous probabilities $P(\text{flood} \mid x) \in [0, 1]$ on `val_v4.csv`.
2. A constrained threshold search sweeps $\tau \in [0.30, 0.95]$ in increments of $0.02$.
3. **Optimization Objective**:
   $$\tau^* = \arg\max_{\tau} \text{Macro-F1}(\tau) \quad \text{subject to } \text{FPR}_{\text{potholes}}(\tau) \le 0.05$$
4. Once $\tau^*$ is fixed on validation data, it is frozen and recorded in model metadata.

### 4.3 Predefined Acceptance Criteria for V4 Deployment
To be accepted as a production-grade candidate, the model must simultaneously satisfy:
1. **Hard Negative Specificity**: $\text{FPR}_{\text{hard\_negatives}} \le 0.05$ (False positive rate on wet asphalt, potholes, and rain puddles $< 5\%$).
2. **Flood Sensitivity**: $\text{FNR}_{\text{flood}} \le 0.02$ (Inundation false negative rate $< 2\%$).
3. **Model Calibration**: Expected Calibration Error ($\text{ECE}$) $\le 0.08$ on 10-bin validation reliability diagram.
4. **Generalization Parity**: Accuracy gap between distinct test sources $\le 10\%$.
5. **Quality Gate Compliance**: $100\%$ abstention on blurred, underexposed, or low-resolution imagery.

### 4.4 Final Test Set Lockdown
The partition `data/processed/manifest_v4/test_v4.csv` ($N=221$) is locked. It will only be evaluated once after all model development, architecture selection, and validation threshold tuning are complete.

---

## Phase 5 — Safety Policy & System Integration

### 5.1 Preservation of the Image Quality Gate
The automated pre-inference quality gate implemented in `src/sahaay/vision/inference.py` is preserved intact:
- **Darkness Filter**: Mean pixel luminance $< 15.0$ $\rightarrow$ Inconclusive (`underexposed_darkness`).
- **Whiteout Filter**: Mean pixel luminance $> 240.0$ $\rightarrow$ Inconclusive (`overexposed_whiteout`).
- **Blur Filter**: Laplacian variance $< 100.0$ $\rightarrow$ Inconclusive (`severe_motion_or_focus_blur`).
- **Resolution Filter**: Width $< 128$ or Height $< 128$ $\rightarrow$ Inconclusive (`insufficient_native_resolution`).
- When triggered, inference returns `is_inconclusive = True`, `predicted_class = "inconclusive"`, and `confidence = 0.0`.

### 5.2 Advisory-Only Semantics & Decision Engine Safety Contracts
In accordance with Sahaay AI core governance rules:
- **Vision is strictly advisory**: A photo classification alone CANNOT trigger an `EMERGENCY` alert or autonomous municipal road closures.
- An `EMERGENCY` alert requires corroboration from severe rainfall forecast ($> 70\text{ mm/hr}$ on high-vulnerability roads) or human field verification by GHMC/traffic police crews.
- Ambiguous or inconclusive vision inputs decay gracefully to `ADVISORY` or `CLEAR` with non-actionable status (`is_actionable_for_crews = False`).

### 5.3 Automated Test Suite Coverage
Regression tests in [`tests/test_vision_v4.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_vision_v4.py) assert:
- Total disjointness of image IDs, MD5 hashes, and cluster IDs across V4 splits.
- Zero cross-split near-duplicate pairs ($h \le 2$).
- Unification of all 5 historical V3 leak pairs within single splits.
- Rejection of corrupted/blurred inputs by the quality gate.
- Adherence to non-emergency advisory contracts by the Decision Engine.

*Full test suite pass rate: **46 / 46 passed (100%)**.*

---

## Deliverable 4 — Written Decision on Training V4 Now

### Formal Decision: **NO-GO FOR TRAINING PRODUCTION V4 MODEL NOW**

#### Detailed Scientific Justification:
1. **Structural Confounding Unresolved in Available Data**:
   While `manifest_v4` successfully cures all cross-split leakage, near-duplicate clustering bugs, and evaluation independence issues that afflicted V1, V2, and V3, the fundamental limitation of the local data remains: **every flood image comes from Clemson, and every road negative comes from Virenbr11**.
2. **High Shortcut Exploitability**:
   Our non-semantic metadata classifier achieves **85.97% test accuracy** (with `file_size_kb` driving 54.2% and `width` driving 24.6% of importance). Training a deep convolutional or vision transformer network on this split today would produce a model that achieves apparent high test scores by learning camera acquisition signatures and compression artifacts rather than floodwater physics.
3. **Integrity Mandate**:
   Sahaay AI is engineered for public safety and life-critical urban intelligence. Training and claiming a "Vision V4" model on source-entangled data violates the non-negotiable integrity standards of this platform.
4. **Prerequisite**:
   Training the final production Vision V4 model is deferred until **paired, source-matched road imagery** is acquired in accordance with the Hyderabad Monsoon Field Acquisition Plan detailed below.

---

## Hyderabad Monsoon Field Acquisition Plan

To unlock valid, source-independent Vision V4 training, Sahaay AI will execute a targeted monsoon field data acquisition campaign in Hyderabad:

### 1. Target Corridors & Hotspots (20 Monitored Locations)
- **Central Zone**: Khairatabad Flyover, Panjagutta Underpass, Lakdikapul Junction, Raj Bhavan Road.
- **West Zone**: Tolichowki Flyover Underpass, Shaikpet Nala Road, Gachibowli Bio-Diversity Junction, Madhapur Cyber Towers Corridor.
- **North & East Zones**: Begumpet Rasoolpura Underpass, Secunderabad Clock Tower Subway, Malakpet Railway Underbridge, Musarambagh Bridge Causeway.

### 2. Multi-Modal Source Pairing Protocol
For every target camera/viewport, capture three matched condition classes across identical camera optics and angles:
1. **Condition A (Dry Baseline)**: Clean asphalt, dry curbs, daytime and nighttime traffic.
2. **Condition B (Hard Negative / Rain Wet)**: Wet asphalt, headlight reflections, puddles, potholes filled with water without road inundation.
3. **Condition C (True Positive / Inundated)**: Curb-to-curb standing water, submerged lane markings, vehicular water displacement.

### 3. Data Acquisition Streams
- **Stream 1 (Traffic CCTV)**: Partner with Hyderabad Traffic Police (HTP) and GHMC Command & Control Centre (ICCC) for RTSP snapshot extractions at 10-minute intervals during July–September monsoons.
- **Stream 2 (Field Crew Photo App)**: Equip GHMC emergency monsoon response teams with the Sahaay Field App to upload geo-tagged photos during road maintenance operations.
- **Stream 3 (Citizen Crowd-Sourcing)**: Mobile web upload portal with automated GPS and EXIF verification.

### 4. Annotation, Privacy & Gating Standards
- **Anonymization**: Automated blurring of faces and vehicle license plates prior to ingestion.
- **Dual Blind Annotation**: Every image annotated by two independent annotators with Cohen's Kappa $\kappa \ge 0.85$ required for inclusion.
- **Depth Tier Classification**: Tier 1 (Ankle-deep $< 15\text{ cm}$), Tier 2 (Knee-deep $15\text{--}45\text{ cm}$), Tier 3 (Impassable $> 45\text{ cm}$).

---

## Deliverable 5 — Reproducible Commands & Verification Results

### Reproducible Execution Commands

#### 1. Audit and Verification of Historical V3 Leak Pairs:
```bash
.\.venv\Scripts\python.exe scripts/verify_v3_leak_pairs.py
```
*Output: All 5 pairs verified with Hamming distance $\le 2$ bits.*

#### 2. Comprehensive Dataset Inventory & Domain Audit:
```bash
.\.venv\Scripts\python.exe scripts/audit_dataset_inventory.py
```
*Output: Machine-readable inventory saved to `reports/vision_integrity/v4_dataset_inventory.json`.*

#### 3. Exhaustive $N \times N$ Clustering and Manifest V4 Partitioning:
```bash
.\.venv\Scripts\python.exe scripts/prepare_source_aware_v4.py
```
*Output: Manifests written to `data/processed/manifest_v4/` (1,034 train, 223 val, 221 test; 0 leaks).*

#### 4. Non-Semantic Metadata Diagnostic Baseline:
```bash
.\.venv\Scripts\python.exe scripts/diagnostics_shortcut_baseline_v4.py
```
*Output: Diagnostic metrics saved to `reports/vision_integrity/shortcut_diagnosis_v4.json` (85.97% RF test accuracy).*

#### 5. Pre-Flight Readiness Gate Check:
```bash
.\.venv\Scripts\python.exe scripts/train_eval_v4_protocol.py --check-readiness-only
```
*Output: Confirms NO-GO status due to active source confounding.*

#### 6. Automated Unit and Regression Test Suite:
```bash
.\.venv\Scripts\python.exe -m pytest -v
```
*Output: 46 passed, 0 failed in 6.90s (100% pass rate).*
