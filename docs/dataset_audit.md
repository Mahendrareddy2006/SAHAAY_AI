# Sahaay AI — Flood Vision Dataset Audit Report
**Platform:** Sahaay AI — Predict. Prevent. Protect.  
**Component:** Component 1 — Flood Vision AI  
**Audit Date:** 2026-10-25  
**Author:** Senior AI/ML Engineer (Team Member A)  
**Status:** Complete & Empirically Verified

---

## 1. Executive Summary

A successful, safety-critical computer vision classifier for urban waterlogging requires:
1. **Representative Perspective:** Smartphone camera angles (eye-level, dashcam, pavement level, vehicle hubcap reflections).
2. **Balanced Ground Truth:** High-quality positive examples (inundated roadways, submerged curbs) alongside rigorously verified negative examples (dry roads, damp roads without standing water, parked cars, sidewalks, shadows).
3. **Domain Shift Awareness:** Top-down aerial drone images and street-level citizen smartphone photos cannot be treated as identical data distributions without source-aware conditioning.

This audit evaluates four datasets inspected locally and remotely in our environment.

---

## 2. Quantitative Dataset Comparison

| Dataset Source | Image Count | Primary Perspective | Annotation Format | Positive / Negative Split | Local Availability Status | Primary Risk / Finding |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **FloodNet v1.0** | 2,343 | Aerial (DJI Mavic Pro UAS) | 10-Class Semantic Masks | Mixed pixels (roads, buildings, pools, grass) | Repo clone in `Downloads` (full 13.05 GB on Dropbox) | **Severe Perspective Mismatch:** High-altitude drone shots do not reflect citizen phone angles. |
| **EU Flood 2013** | 3,435 | Ground-Level / Social Media | Task Relevance (`flooding.txt`, `irrelevant.txt`) | 3,151 Flooded / 327 Irrelevant (Non-Flooded) | Repo clone in `Downloads` (1.14 GB archive on Archive.org) | **Excellent Event Realism:** Contains verified negative images from same disaster event; direct Wikimedia scraping rate-limited (HTTP 403). |
| **Clemson FloodIMG** | 9,296 | Ground-Level & CCTV | IoT / Event Feeds (25 files with Labelme JSONs) | 9,296 Flooded / **0 Non-Flooded** | **100% Downloaded** (`.cache/kagglehub/...`, 9,296 images) | **Severe Negative Class Deficit:** Every image is flood-related. Cannot train binary classifier alone without false-positive explosion. |
| **Curated Ground Binary** | 3,000 | Ground-Level Street | Image-level binary folders (`Flood/`, `Non_Flood/`) | **1,500 Flooded / 1,500 Non-Flooded** | **100% Downloaded** (`.cache/kagglehub/...`, 3,000 images) | **Optimal Baseline:** Perfectly balanced, verified street-level perspectives matching mobile uploads. |

---

## 3. In-Depth Dataset Audits

### 3.1 FloodNet — Supervised v1.0 (Aerial UAS Imagery)
- **Official Repository:** `https://github.com/BinaLab/FloodNet-Supervised_v1.0`
- **Citation:** Rahnemoonfar et al., *IEEE Access* (2021), DOI: 10.1109/ACCESS.2021.3090981.
- **License:** CDLA-Permissive-1.0 (Community Data License Agreement).
- **Inspected Files:**
  - `FloodNet-Sample.jpg`: Resolution 5988 x 3521 pixels, RGB, 1.63 MB.
  - `README.md`: Documents 2,343 images collected after Hurricane Harvey in Texas.
  - Segmentation masks: 1) Background, 2) Building Flooded, 3) Building Non-Flooded, 4) Road Flooded, 5) Road Non-Flooded, 6) Water, 7) Tree, 8) Vehicle, 9) Pool, 10) Grass.
  - Download storage: Dropbox archive of 13.05 GB (`FloodNet.zip`). Measured throughput: ~0.84 MB/s (estimated transfer ~4.3 hours).
- **Critical Perspective Mismatch:**
  - High-altitude nadir drone views feature roof-level geometry, tree canopies, and bird’s-eye road grids.
  - Citizen smartphone submissions feature eye-level road surfaces, bumper-level water depth, headlight glare, and close-up curb interactions.
  - **Engineering Decision:** FloodNet will NOT be merged indiscriminately into the primary mobile image classifier. It is reserved for an optional aerial drone surveillance module with a separate model version identifier.

---

### 3.2 European Flood 2013 Dataset
- **Official Repository:** `https://inf-cv.uni-jena.de/home/research/datasets/eu-flood-dataset/`
- **Citation:** Barz et al., *Archives of Data Science* (2018), arXiv: 1908.03361.
- **License:** CC BY-SA 3.0 / Wikimedia Commons licenses.
- **Inspected Files:**
  - `metadata.json`: 3,435 image records with Wikimedia page IDs, titles, original URLs, upload timestamps, capture timestamps, and 883 geocoded entries (lat/lon).
  - `relevance/flooding.txt`: 3,151 image IDs annotated by hydrologists as visibly flooded.
  - `relevance/irrelevant.txt`: 327 image IDs annotated as not relevant / no flooding (e.g. buses, dry squares, unaffected rail lines during June 2013 floods).
  - `important_regions/`: Bounding box annotations indicating key water marks and flood indicators.
- **Network & Access Audit:**
  - Full archive: Available on Archive.org (`european-flood-2013_imgs_small.zip`, 1.14 GB, HTTP 200).
  - Uni Jena mirror: Dead mirror (`HTTP 404 Client Error`).
  - Direct Wikimedia Commons automated downloads: Rate-limited/blocked with HTTP 403 Forbidden without authenticated academic API approval.
- **Engineering Decision:** Used as an external ground-truth benchmark and negative-distribution reference for disaster-event non-flooded scenes.

---

### 3.3 Clemson University Flooding Image Dataset (FloodIMG)
- **Official Paper:** Karanjit, Samadi et al., *Data in Brief* (2023), DOI: 10.1016/j.dib.2023.109164.
- **Kaggle Source:** `hhrclemson/flooding-image-dataset` (Downloaded locally: 9,296 images).
- **Inspected Files:**
  - `Flood Images/`: 9,296 JPEG images ranging from 800x600 to 2048x1365.
  - `Annotation/`: 25 JSON files in Labelme polygon format.
- **Object Class Frequencies in Annotations:**
  - Person: 19
  - Tree: 14
  - House: 13
  - Builbing (Building): 13
  - Traffic Sign: 12
  - Bridge: 10
  - Forest: 8
  - Car: 6
  - Truck: 4
  - Road: 4
- **Critical Negative Deficit Audit:**
  - All 9,296 images were scraped using flood keywords and flood-event cameras.
  - **There are zero non-flooded road images.**
  - **Mandatory Engineering Rule Compliance:** As stipulated in the master guidelines, we *refuse* to treat missing annotations as negative labels, and we *refuse* to train a classifier solely on this dataset, as doing so would train the model to predict "flooded" for any outdoor scene with high confidence.
  - **Role in Platform:** Acts as a large-scale positive flood image reservoir for domain pre-training and hard-positive data augmentation.

---

### 3.4 Curated Ground-Level Binary Classification Dataset
- **Kaggle Source:** `roham1/flood-classification-dataset` (Downloaded locally: 3,000 images).
- **Inspected Files:**
  - `Flood/`: 1,500 images of inundated roads, submerged vehicles, flooded sidewalks, and waterlogging.
  - `Non_Flood/`: 1,500 images of dry asphalt roads, normal urban traffic, dry sidewalks, and parked vehicles.
- **Integrity Check:**
  - Sample of 200 images verified via `PIL.Image.verify()`: 0 corruptions detected.
  - Image formats: JPEG / PNG, RGB.
- **Engineering Decision:** Selected as the **primary training and validation benchmark** for the production Flood Vision baseline classifier.

---

## 4. Common Label Normalization Schema

All ingested images are mapped to the canonical Sahaay AI Vision schema:

```json
{
  "0": "not_flooded",
  "1": "flooded"
}
```

### Label Mapping Table
| Source Dataset | Original Class / Tag | Canonical Class | Target Integer | Inclusion Status |
| :--- | :--- | :--- | :--- | :--- |
| `roham1/flood-classification-dataset` | `Non_Flood` | `not_flooded` | 0 | Supervised Train/Val/Test |
| `roham1/flood-classification-dataset` | `Flood` | `flooded` | 1 | Supervised Train/Val/Test |
| `eu-flood-dataset` | `relevance/irrelevant.txt` | `not_flooded` | 0 | Benchmark Evaluation |
| `eu-flood-dataset` | `relevance/flooding.txt` | `flooded` | 1 | Benchmark Evaluation |
| `clemson_floodimg` | `Flood Images/*` | `flooded` | 1 | Pre-training / Positive Augmentation |
| `FloodNet` | `Road Non-Flooded` (Class 4) | `not_flooded` | 0 | Aerial Classifier Only (Excluded from Mobile Stream) |
| `FloodNet` | `Road Flooded` (Class 3) | `flooded` | 1 | Aerial Classifier Only (Excluded from Mobile Stream) |
| Ambiguous / Corrupt | Corrupt / Unclear | `unknown` | Excluded | Excluded from supervised training |

---

## 5. Splitting Strategy & Leakage Prevention

1. **Stratified Split:**
   - 70% Training: 2,100 images (1,050 flooded, 1,050 not_flooded).
   - 15% Validation: 450 images (225 flooded, 225 not_flooded) — used exclusively for model selection and early stopping.
   - 15% Held-Out Test: 450 images (225 flooded, 225 not_flooded) — untouched until final checkpoint evaluation.
2. **Reproducibility:**
   - Deterministic split via `sklearn.model_selection.train_test_split` with `random_state=42`.
   - Manifest files exported to `data/processed/` with file paths, MD5 checksums, labels, and source dataset attributes.
3. **Leakage Prevention:**
   - Training augmentations (flips, crops, jitter) are strictly isolated from validation and test sets.
   - Evaluation metrics computed only on unaugmented evaluation pipelines.
