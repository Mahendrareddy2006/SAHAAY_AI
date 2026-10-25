# Sahaay AI — Phase 9: AI/ML Baseline Audit

## 1. Executive Summary

This document establishes the official AI/ML engineering baseline for **Sahaay AI Phase 9**, continuing directly from Phase 8 commit [`0e9a07d`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai).

The mandate of Phase 9 is strictly confined to **AI/ML dataset readiness, leakage-free experimentation, model benchmarking, and honest reporting of data limitations**. Backend APIs, live-data integrations, frontend interfaces, and pilot field-authorization workflows remain outside this phase.

### Core Baseline Findings
1. **Working Tree & Artifact State:** The Git repository is clean at commit `0e9a07d`. All historical model checkpoints (`models/vision/best_model.pt`, `models/vision/v2/model_v2.pt`, `models/vision/v3/model_v3_clean.pt`, `models/vision/v3/model_v3_monsoon.pt`) and historical manifests (`data/processed/*.csv`, `manifest_v2/`, `manifest_v3/`, `manifest_v4/`) remain strictly preserved on disk without modification or relabeling.
2. **Regression Suite Baseline:** All 133 repository unit and integration tests passed prior to code modification.
3. **Data Integrity Status:** Manifest V4 successfully cured all historical cross-split duplicate leakage through global $N \times N$ pairwise Hamming clustering. However, **source-label confounding remains 100% active** ($V = 1.0$) across available road imagery (Clemson flood images vs Virenbr11 dry/pothole roads).
4. **Readiness Gate Verdict:** Vision V4 production training readiness remains strictly **`NO-GO`**.

---

## 2. Review of Historical Vision Model Evolution (V1–V4)

A rigorous audit of past model iterations establishes which empirical conclusions remain scientifically valid and which were invalidated by methodology flaws:

| Model Version | Architecture & Checkpoint | Training Manifest | Reported Headline Metric | Audit Finding & Forensic Reality | Current Scientific Validity |
| :--- | :--- | :--- | :---: | :--- | :--- |
| **Vision V1** | `MobileNetV3-Small` ([`best_model.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/best_model.pt)) | Random split `train.csv` / `test.csv` | ~98% Test Accuracy | Unconstrained random splitting resulted in severe cross-split duplicate leakage from sequential burst captures. Evaluated without independent sources. | **SUPERSEDED — INVALID CLAIM** |
| **Vision V2** | `MobileNetV3-Small` ([`model_v2.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v2/model_v2.pt)) | Exact MD5 deduplicated `manifest_v2/` | ~96% Test Accuracy | Sliding-window clustering ($\text{window}=300$) missed distant near-duplicate pairs ($h \le 2$). Collapsed when exposed to unseen dry road pavement (`virenbr11_plain`), yielding a **94% false positive rate**. | **SUPERSEDED — OVERFITTED SHORTCUT** |
| **Vision V3 Clean** | `MobileNetV3-Small` ([`model_v3_clean.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v3/model_v3_clean.pt)) | `manifest_v3/` | 97.30% Test Accuracy | Standard augmentation; audit identified 5 cross-split near-duplicate leak pairs due to windowing sort tie-breakers. Entangled with source dataset identity. | **SUPERSEDED — DIAGNOSTIC ONLY** |
| **Vision V3 Monsoon** | `MobileNetV3-Small` ([`model_v3_monsoon.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v3/model_v3_monsoon.pt)) | `manifest_v3/` | 97.75% Test Accuracy | Monsoon data augmentation (blur, color jitter, flip) conferred empirical robustness on degraded images and puddles (0% pothole FPR). However, source-label confounding was identical to V3 Clean. | **DIAGNOSTIC ROBUSTNESS BASELINE** |
| **Vision V4 Dataset** | Dataset Architecture only (No weights trained) | `manifest_v4/` (1,034 train, 223 val, 221 test) | N/A (Gated NO-GO) | Eliminated all window limits via global $N \times N$ Hamming checks. Unified all 5 historical leak pairs. Re-evaluated non-semantic metadata classifier: **85.97% test accuracy** using strictly width, height, and file size. | **ACTIVE LEAK-FREE DIAGNOSTIC SPLIT** |

---

## 3. Forensic Analysis of Verified Historical Findings

### 3.1 Transitive Duplicate Leakage & Windowing Breakdown
In Phases 1 and 2, the root cause of V3 near-duplicate cross-split leakage was traced to the assumption that sorting 64-bit perceptual hashes allows sliding-window clustering. Because the difference hash (`dhash`) projects multi-dimensional image features onto 64 discrete binary bits, small variations in texture or lighting can alter high-order bits while preserving low-order bits. Two near-duplicate images separated by intervening items in the sorted array were separated into different clusters and assigned to opposing partitions (`train_v3` vs `test_v3`).

In `prepare_source_aware_v4.py`, this vulnerability was permanently cured by computing full $N \times N$ pairwise Hamming distances across all 1,478 candidate images, ensuring that any two images with Hamming distance $h \le 2$ are grouped into the same cluster.

### 3.2 The Non-Semantic Metadata Shortcut
The most critical finding from [`docs/vision_v3_final_audit.md`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/docs/vision_v3_final_audit.md) and [`reports/vision_integrity/shortcut_diagnosis_v4.json`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/vision_integrity/shortcut_diagnosis_v4.json) is that:
- Clemson FloodIMG images have mean native dimensions of $1598 \times 1110$ and a mean file size of $1,193\text{ KB}$.
- Virenbr11 road images have mean native dimensions of $475 \times 334$ and a mean file size of $73\text{ KB}$.
- Even after resizing both datasets to $224 \times 224$ pixels during preprocessing, deep convolutional neural networks readily learn high-frequency sensor noise, interpolation artifacts, and compression blockiness that correlate with the original file size and native resolution.
- A shallow Random Forest trained solely on 4 non-semantic metadata features (`width`, `height`, `aspect_ratio`, `file_size_kb`) achieved **85.97% test accuracy** with a test ROC-AUC of **0.9066**.
- Therefore, high accuracy on this split is not proof of visual flood comprehension.

---

## 4. Audit of Historical Model Checkpoints on Disk

Every historical model checkpoint on disk was verified:

| File Path | File Size (Bytes) | SHA-256 Checksum Prefix | Integrity Status |
| :--- | :---: | :---: | :---: |
| [`models/vision/best_model.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/best_model.pt) | 18,493,276 | `f29d8928...` | Verified Unmodified |
| [`models/vision/v2/model_v2.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v2/model_v2.pt) | 18,493,276 | `b019b884...` | Verified Unmodified |
| [`models/vision/v3/model_v3_clean.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v3/model_v3_clean.pt) | 18,493,276 | `4859a224...` | Verified Unmodified |
| [`models/vision/v3/model_v3_monsoon.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v3/model_v3_monsoon.pt) | 18,493,276 | `24675549...` | Verified Unmodified |

---

## 5. Pre-Phase 9 Test Execution

Prior to making any code modifications, all 133 unit and integration tests across the repository were executed:
- **Command:** `.\.venv\Scripts\python.exe -m pytest -q`
- **Result:** **133 passed, 0 failed in 8.11s**.
- **ML Subsystem Test Breakdown:**
  - `tests/test_vision_v3.py`: 10 passed.
  - `tests/test_vision_v4.py`: 9 passed.
  - `tests/test_split_integrity.py`: 5 passed.
  - `tests/test_inference.py`: 3 passed.
  - `tests/test_image_quality_gate.py`: 5 passed.
  - `tests/test_model.py`: 2 passed.
  - `tests/test_vision_v4_collection.py`: 15 passed.
  - `tests/test_vision_v4_phase3.py`: 7 passed.

---

## 6. Phase 9 AI/ML Engineering Strategy

Guided by the principle that **a rigorous `NOT_RUN` result is preferable to a misleading model benchmark**, Phase 9 establishes three distinct operational tracks:
1. **Track A (Diagnostic Baselines):** Quantify the non-semantic metadata ceiling on Manifest V4 and benchmark Image Quality Gate filtering.
2. **Track B (Cross-Source Transfer & Robustness):** Document how existing checkpoints perform across unseen sources, environmental corruptions, and out-of-distribution inputs.
3. **Track C (Data-Readiness Tooling):** Formally record that production Vision V4 training is `NOT_RUN`, define the required multi-class collection targets, and prevent premature training on confounded data.
