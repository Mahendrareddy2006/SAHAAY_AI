# Sahaay AI — Flood Vision Training Data Provenance & Baseline Audit
**Platform:** Sahaay AI — Predict. Prevent. Protect.  
**Component:** Component 1 — Flood Vision AI  
**Audit Date:** 2026-10-25  
**Auditor:** Senior AI/ML Engineer (Team Member A)  
**Status:** Forensic Verification Complete

---

## 1. Executive Summary

This audit rigorously verifies the exact lineage, image paths, checksums, and dataset origins for the Flood Vision baseline checkpoint located at:  
`models/vision/best_model.pt`

### Key Verified Facts
1. **100% Single-Source Training:** All **3,000 images** across `train.csv`, `val.csv`, and `test.csv` originate exclusively from `roham1/flood-classification-dataset`.
2. **Status of Other Audited Datasets:**
   - **Clemson FloodIMG (`hhrclemson/flooding-image-dataset`):** Audited and downloaded (9,296 images), but **NOT used** for training or pre-training the checkpoint.
   - **FloodNet Supervised v1.0:** Audited from repository clone, but **NOT used** for training.
   - **European Flood 2013:** Audited from repository clone (`relevance/`, `metadata.json`), but **NOT used** for training.
3. **Reason for 100% Test Accuracy:**
   - Forensic analysis revealed **41 cross-split exact duplicates** (identical MD5 hashes across train and test/val) and **59 cross-split near-duplicate clusters** (perceptual difference hash) caused by lack of scene-grouping metadata in the source dataset.
   - **Source Resolution Artifact Shortcut:** 100% of the non-flooded images in `roham1` were pre-cropped to `(224, 224)` from external web datasets, whereas flooded images possess varied high-resolution dimensions (`1707x1280`, `800x450`, `1280x720`). The model learned both flood visual features and subtle sub-source compression/scaling signatures.

---

## 2. Dataset Split Breakdown & Path Provenance

Inspection of `data/processed/train.csv`, `data/processed/val.csv`, and `data/processed/test.csv`:

| Split Manifest | Total Images | Not-Flooded | Flooded | Source Dataset Origin | Path Root Directory |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `train.csv` | 2,100 | 1,050 (50%) | 1,050 (50%) | `roham1_binary_ground` | `C:\Users\MahendraReddy\.cache\kagglehub\datasets\roham1\...` |
| `val.csv` | 450 | 225 (50%) | 225 (50%) | `roham1_binary_ground` | `C:\Users\MahendraReddy\.cache\kagglehub\datasets\roham1\...` |
| `test.csv` | 450 | 225 (50%) | 225 (50%) | `roham1_binary_ground` | `C:\Users\MahendraReddy\.cache\kagglehub\datasets\roham1\...` |
| **Total** | **3,000** | **1,500 (50%)** | **1,500 (50%)** | **100% roham1** | **Single Local Root** |

### Verified Subdirectory Structure:
- `...\roham1\flood-classification-dataset\versions\1\Flood` (1,500 images, labeled `flooded`)
- `...\roham1\flood-classification-dataset\versions\1\Non_Flood` (1,500 images, labeled `not_flooded`)

---

## 3. Training Lineage & Checkpoint Metadata

Analysis of checkpoint `models/vision/best_model.pt` and `models/vision/model_metadata.json`:

1. **Pretrained Weights Base:**  
   Official Torchvision ImageNet-1K pretrained weights (`mobilenet_v3_small-047dcff4.pth`, SHA-256 verified by PyTorch).
2. **Transfer Learning Procedure:**  
   Head replaced with `Linear(in_features=1024, out_features=2)`.  
   Trained for 5 epochs on `data/processed/train.csv` using AdamW (`lr=3e-4`, `weight_decay=1e-4`, batch size 32).
3. **Checkpoint Selection:**  
   Selected at **Epoch 4** based on highest Validation Macro-F1 (`1.0000`).
4. **Pretraining Clarification:**  
   **Clemson FloodIMG was NOT used for pretraining or fine-tuning.** The checkpoint is purely ImageNet-1K pretrained + fine-tuned on `train.csv`.

---

## 4. Forensic Duplicate & Leakage Audit

A full forensic hash scan across all 3,000 image instances revealed:

```
Total image instances across splits:  3,000
Total unique MD5 checksums:           2,915
Exact duplicate clusters (identical): 78
  - Within-split exact duplicates:    37
  - Cross-split exact duplicates:     41
Perceptual dHash clusters:            105
  - Cross-split near-duplicates:      59
```

### Concrete Evidence of Cross-Split Duplication
The source dataset (`roham1/flood-classification-dataset`) contained duplicate images with different filenames. For example:
- `train`: `Flood/flood_8751.png` (MD5: `d4955b33785140769a7b8b297b0e9b46`)
- `test`:  `Flood/flood_6560.png` (MD5: `d4955b33785140769a7b8b297b0e9b46`)

Because the preparation script performed standard stratified random splitting on filenames rather than content-aware deduplication, **41 identical images leaked across splits**.

---

## 5. Source Artifact & Shortcut Analysis

Why did the test set achieve 100% accuracy?

### 1. The Resolution Shortcut
A dimensional analysis of `train.csv` revealed a severe class-specific shortcut in the underlying `roham1` dataset:
- **`not_flooded` images:** **1,050 out of 1,050 (100.0%)** are exactly `(224, 224)` pixels with generic numeric filenames (`357.jpg`, `20575.jpg`, `6789.jpg`).
- **`flooded` images:** **0 out of 1,050 (0.0%)** are `(224, 224)`. They range from `(1707, 1280)` down to `(800, 450)`.
- When passed through the transform pipeline (Resize to 256x256, Crop to 224x224), images that were originally 224x224 undergo upsampling followed by downsampling, creating distinctive interpolation artifacts that a deep convolutional neural network can easily exploit as an unintended shortcut.

### 2. Scene Near-Duplicates
Multiple frames from continuous flood video clips exist in the `Flood` folder (e.g. `flood_1002.jpg`, `flood_1003.jpg`, `flood_1004.jpg`). Standard random splitting allocated temporally adjacent frames into train and test splits.

### 3. Out-of-Distribution Transfer Verification
To test whether the model learned genuine flood semantics versus purely memorizing resolution shortcuts, we evaluated the model against **100 unseen images from Clemson FloodIMG** (`hhrclemson/flooding-image-dataset`):
- **Result:** **100 out of 100 images (100.0%)** were correctly classified as `flooded`.
- **Average Confidence:** `0.9991`
- **Conclusion:** The model *does* capture genuine visual waterlogging features, but its test accuracy on `roham1` is inflated by dataset shortcuts.

---

## 6. Evaluation Verification

The untouched test set was re-evaluated against the checkpoint:
```
Fresh Evaluation Output:
  Test Accuracy:    1.0000
  Macro-F1:         1.0000
  Confusion Matrix: [[225, 0], [0, 225]]
Saved Evaluation JSON:
  Test Accuracy:    1.0000
  Macro-F1:         1.0000
  Confusion Matrix: [[225, 0], [0, 225]]
Identical Verification: TRUE (Exact match)
```

---

## 7. Actionable Recommendations for Milestone 2

1. **Content-Aware Deduplication:** Deduplicate all images via MD5 and perceptual dHash before splitting.
2. **Negative Class Re-sourcing:** Collect non-flooded street images with native high resolutions matching citizen smartphone profiles (e.g. 1080p, 4K) rather than pre-cropped 224x224 thumbnails.
3. **Local Hyderabad Image Set:** Ingest representative local Hyderabad road photos (underpasses, arterial roads, service lanes) as an external validation split.
