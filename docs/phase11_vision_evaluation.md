# Sahaay AI — Phase 11: Final Vision Model Evaluation & Benchmark Report

## 1. Executive Summary

This document presents the final scientific evaluation of all computer vision flood classification models developed across Phases 1 through 10 of **Sahaay AI**.

The evaluation benchmarks four historical deep learning checkpoints (`mobilenet_v3_small_v1`, `mobilenet_v3_small_v2`, `mobilenet_v3_small_v3_clean`, `mobilenet_v3_small_v3_monsoon`), audits non-semantic metadata shortcuts, evaluates the Image Quality Gate, and documents the experimental decision regarding Vision V4 production training.

### Core Scientific Findings:
1. **Reproduced Benchmark Verification:** Using the reserved Test V3 split ($N=222$ balanced road imagery), historical model evaluations were independently reproduced using CUDA.
2. **Historical V2 Collapse on Real Roads:** Despite achieving $100.0\%$ accuracy on its own internal split, `model_v2` collapsed to **53.15% accuracy** on unseen road imagery, exhibiting a **94.0% False Positive Rate on plain dry roads** (misclassifying 47 of 50 dry asphalt images as flooded).
3. **V3 Monsoon Robustness Benchmark:** `model_v3_monsoon` demonstrated superior weather and hard-negative robustness: **97.75% accuracy**, **100% specificity on dry roads**, **98.36% specificity on wet potholes and puddles**, and **96.85% accuracy under synthetic rain mist blur**. Calibration error was low ($\text{ECE} = 0.0237$).
4. **Source-Label Confounding Remains Active:** In all available road datasets, source identity perfectly predicts class (**Cramér's $V = 1.0000$**; all floods from Clemson, all negatives from Virenbr11). A non-semantic Random Forest trained strictly on file metadata achieves **85.97% test accuracy**.
5. **Vision V4 Training Status:** Retained strictly as **`NOT_RUN`**. The Vision V4 readiness gate remains locked in **`NO-GO`** status until multi-source balanced field imagery is collected.

---

## 2. Dataset Composition & Source-Label Confounding

Across the evolution of Sahaay AI vision datasets, data curation progressed through four distinct phases:

### 2.1 Dataset Evolution Summary
| Manifest Version | Total Images | Flood Source(s) | Negative Source(s) | Negative Image Content | Known Vulnerability |
| :--- | :---: | :--- | :--- | :--- | :--- |
| **Manifest V1** | 2,246 | roham1 flood (web scrape) | roham1 non-flood | Arbitrary non-road images (pets, rooms) | Duplicate leakage + non-road class bias |
| **Manifest V2** | 2,246 | roham1 flood | roham1 non-flood | Deduplicated via 64-bit dhash | 100% dimensional thumbnail shortcut |
| **Manifest V3** | 1,478 | Clemson University Road Floods ($N=739$) | Virenbr11 Road Pavements ($N=739$) | Genuine roads (374 dry asphalt, 365 wet potholes) | Source-label confounding ($V = 1.0$) |
| **Manifest V4** | 1,478 | Clemson University Road Floods ($N=739$) | Virenbr11 Road Pavements ($N=739$) | Globally clustered, zero cross-split leakage | Source-label confounding ($V = 1.0$) |

### 2.2 Source-Class Contingency Table ([`reports/phase9/source_class_matrix.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/phase9/source_class_matrix.csv))
```csv
source_dataset,non_flood,flood,total,flood_ratio
clemson_flood,0,739,739,1.0
virenbr11_plain,374,0,374,0.0
virenbr11_pothole,365,0,365,0.0
```

- **Cramér's $V$:** **`1.0000`** *(Gate threshold: $\le 0.30$)* $\implies$ **FAILED**.
- **Mutual Information:** **`1.0000 bits`** *(Gate threshold: $\le 0.20\text{ bits}$)* $\implies$ **FAILED**.
- **Cross-Source Representation:** Exactly **0** sources contribute both positive (flooded) and negative (non-flooded) road imagery.

---

## 3. Metadata Shortcut Diagnostics

To prove empirically that high classification accuracy on source-confounded datasets is driven by non-semantic camera artifacts, diagnostic classifiers were evaluated on Manifest V4 using only file metadata (`width`, `height`, `aspect_ratio`, `file_size_kb`, `megapixels`, `bytes_per_pixel`) without observing pixel content:

```
Non-Semantic Metadata Diagnostic Results (Test V4, N=221):
├── File Size Only Decision Stump:
│   └── Test Accuracy: 80.09% | Macro-F1: 0.7885 | ROC-AUC: 0.8280
├── Dimensions Only Decision Stump (Width/Height):
│   └── Test Accuracy: 67.42% | Macro-F1: 0.6129 | ROC-AUC: 0.7583
└── Multi-Feature Random Forest (All 6 Metadata Features):
    ├── Test Accuracy: 85.97% | Macro-F1: 0.8426 | ROC-AUC: 0.9066
    ├── Precision (Flooded): 95.40% | Recall (Flooded): 75.45%
    └── Feature Importances: File Size (54.2%), Width (24.6%), Height (15.0%), Aspect Ratio (6.2%)
```

### Scientific Takeaway:
An algorithm observing only the file size in kilobytes achieves over $80\%$ test accuracy because Clemson cameras compressed JPEGs differently from Virenbr11 cameras. Deep neural networks trained on these splits will exploit these low-level sensor signatures rather than learning water surface physics.

---

## 4. Controlled Benchmark on Reserved Road Test Set (Test V3, $N=222$)

Using [`scripts/evaluate_comparative_v3.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/scripts/evaluate_comparative_v3.py) and [`scripts/evaluate_realistic_robustness.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/scripts/evaluate_realistic_robustness.py), the models were independently benchmarked on the unseen, balanced Test V3 set (111 Clemson flooded streets, 50 plain dry roads, 61 wet potholes/puddles):

### 4.1 Overall Performance Comparison
| Model Checkpoint | Test Accuracy (95% CI) | Macro-F1 | False Positive Rate | False Negative Rate | Test ECE | Brier Score | High-Conf Errors ($\ge 0.85$) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`model_v2_historical`** | $53.15\%$ ($0.4659\text{--}0.5961$) | $0.3998$ | **$93.69\%$** | $0.00\%$ | $0.4526$ | $0.4485$ | 96 |
| **`model_v3_clean`** | $97.30\%$ ($0.9423\text{--}0.9876$) | $0.9730$ | $3.60\%$ | $1.80\%$ | $0.0134$ | $0.0187$ | 1 |
| **`model_v3_monsoon`** | **$97.75\%$** ($0.9484\text{--}0.9903$) | **$97.75\%$** | **$0.90\%$** | $3.60\%$ | $0.0237$ | $0.0255$ | 5 |

---

### 4.2 Granular Real-World Cohort Breakdown
Evaluating per-condition cohorts isolates how models handle specific road conditions:

#### Cohort A: Plain Dry Roads ($N=50$, All Non-Flooded)
- **`model_v2_historical`:** **Accuracy $= 6.00\%$** (Misclassified 47 of 50 dry asphalt roads as flooded! Mean flood probability $= 0.9173$).
- **`model_v3_clean`:** Accuracy $= 94.00\%$ (3 false positives, mean flood prob $= 0.0843$).
- **`model_v3_monsoon`:** **Accuracy $= 100.00\%$** (0 false positives, mean flood prob $= 0.0150$).

#### Cohort B: Wet Roads, Potholes & Puddles Hard Negatives ($N=61$, All Non-Flooded)
- **`model_v2_historical`:** **Accuracy $= 6.56\%$** (Misclassified 57 of 61 puddles/potholes as flooded! Mean flood prob $= 0.9193$).
- **`model_v3_clean`:** Accuracy $= 98.36\%$ (1 false positive, mean flood prob $= 0.0443$).
- **`model_v3_monsoon`:** Accuracy $= 98.36\%$ (1 false positive, mean flood prob $= 0.0455$).

#### Cohort C: Flooded Streets ($N=111$, All Flooded)
- **`model_v2_historical`:** Accuracy $= 100.00\%$ (111/111 detected, mean flood prob $= 0.9991$).
- **`model_v3_clean`:** Accuracy $= 98.20\%$ (109/111 detected, 2 false negatives, mean flood prob $= 0.9730$).
- **`model_v3_monsoon`:** Accuracy $= 96.40\%$ (107/111 detected, 4 false negatives, mean flood prob $= 0.9435$).

#### Cohort D: Low Light & Overcast Imagery ($N=21$)
- **`model_v2_historical`:** Accuracy $= 42.86\%$ (100% false positive rate on dry scenes).
- **`model_v3_clean`:** Accuracy $= 95.24\%$ (1 false positive).
- **`model_v3_monsoon`:** Accuracy $= 95.24\%$ (0 false positives, 1 false negative).

---

## 5. Synthetic Perturbation Robustness Benchmarks

To evaluate robustness against adverse camera conditions typical of Indian monsoon downpours, five realistic physical perturbations were simulated across all 222 Test V3 images:

| Perturbation Type | Simulated Physical Condition | `model_v2` Accuracy | `model_v3_clean` Accuracy | `model_v3_monsoon` Accuracy |
| :--- | :--- | :---: | :---: | :---: |
| **Synthetic Rain Mist Blur** | Droplet condensation & heavy spray ($\sigma=3.5$) | $70.72\%$ | $93.24\%$ | **$96.85\%$** |
| **Synthetic Night Darkness** | Heavy dark storm clouds / night ($0.25\times$ brightness) | $55.41\%$ | $87.39\%$ | **$91.89\%$** |
| **Synthetic Headlight Glare** | Specular reflection & oncoming glare ($1.8\times$ brightness, $1.4\times$ contrast) | $54.50\%$ | $92.34\%$ | **$94.59\%$** |
| **Synthetic Lens Droplets** | Water droplets obstructing camera lens surface | $51.80\%$ | $88.74\%$ | **$92.34\%$** |
| **Synthetic Motion Blur** | Moving vehicle dashcam vibration ($k=15$) | $78.38\%$ | $95.95\%$ | **$96.85\%$** |

### Key Diagnostic Observation:
`model_v3_monsoon` outperforms both `model_v2` and `model_v3_clean` across every single adverse weather perturbation. The physical augmentations introduced during Phase 3 successfully regularized the network against monsoon-induced visual distortions.

---

## 6. Positive Recall vs Overall Flood-Detection Performance

A critical distinction emphasized in Phase 11 is between **positive-class recall** and **overall flood-detection performance**:

> [!WARNING]
> ### The Positive Recall Fallacy
> `model_v2_historical` achieved a **$100.0\%$ recall** on flooded streets (111 out of 111 flooded scenes detected).
> 
> However, this $100\%$ recall was achieved because the model classified virtually **everything as flooded** (94.0% false positive rate on dry roads and 93.4% false positive rate on puddles). A model that screams "FLOOD" at dry asphalt has perfect recall but is completely worthless in municipal operations.
> 
> In real-world urban deployments where $>95\%$ of street scenes are non-flooded, a model with $94\%$ False Positive Rate will trigger hundreds of false alarms per hour, leading to operator alarm fatigue and system abandonment. Overall flood-detection performance requires high specificity and low false positive rate on hard negatives.

---

## 7. Image Quality Gate Pre-Filter Performance

The automated `ImageQualityGate` ([`src/sahaay/data_collection_v4/quality.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/data_collection_v4/quality.py)) was tested across degraded image cohorts:

```
Image Quality Gate Test Results:
├── Severe Motion Blur (Laplacian variance < 80.0): 100% Rejected (Code: BLURRY)
├── Pitch Black Night (Mean pixel intensity < 35.0): 100% Rejected (Code: UNDEREXPOSED)
├── Specular Glare Whiteout (Mean pixel intensity > 230.0): 100% Rejected (Code: OVEREXPOSED)
├── Low Native Resolution (< 640x480 pixels): 100% Rejected (Code: LOW_RESOLUTION)
└── Normal Valid Road Scenes: 100% Passed to inference
```

- **Non-Silent Rejection Policy:** Every rejected image explicitly returns an informative diagnostic reason rather than being silently discarded or imputed.

---

## 8. Final Decision on Vision V4 Production Training

### Formal Decision: **EXPERIMENT STATUS = `NOT_RUN` (Gate Status: `NO-GO`)**

In adherence to Phase 9 and Phase 10 readiness criteria:
1. **Gate 1 (Multi-Source Representation):** FAILED (0 multi-class road imagery sources).
2. **Gate 2 (Statistical Independence):** FAILED (Cramér's $V = 1.0000$, Mutual Information $= 1.0000\text{ bits}$).
3. **Gate 3 (Metadata Shortcut Ceiling):** FAILED (Random Forest test accuracy $= 85.97\% > 65.0\%$).
4. **Gate 4 (Real Field Imagery):** FAILED (0 real field observations acquired; pilot activation gate remains `BLOCKED_NOT_READY_FOR_LIVE_PILOT`).

Training a production Vision V4 model on the current dataset would violate scientific integrity by claiming to solve a problem whose training data is completely confounded. The production training experiment is formally recorded as **`NOT_RUN`**.
