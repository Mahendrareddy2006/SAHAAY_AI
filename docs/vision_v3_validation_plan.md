# Sahaay AI — Vision V3: Shortcut-Resistant Validation and Monsoon Robustness Plan

## 1. Executive Summary & Forensic Context

The initial Flood Vision AI baseline (V1) reported a 100% test score, which subsequent forensic auditing in `docs/training_data_provenance.md` proved to be an artifact of severe cross-split duplicate leakage and dimensional confounding: 100% of non-flood images in the `roham1` dataset were artificially resized to $224 \times 224$ pixels, while 96% of flood images retained variable camera resolutions ($300\text{--}6999\text{ px}$). 

While the V2 pipeline eliminated cross-split leakage and introduced group-partitioning, V2 still inherited the $224 \times 224$ dimensional confounding from `roham1`, and external validation on 200 Clemson flood images tested recall exclusively without evaluating specificity or false-positive behavior.

**Vision V3** fundamentally resolves these integrity risks:
1. **Audits External Evaluation Independence**: Formally inspects the external Clemson cohort, demonstrating exact hash overlaps with historical splits and proving that positive-only cohorts cannot measure false-positive rate, precision, or calibration.
2. **Eliminates Dimensional Shortcuts with Genuine Hard Negatives**: Incorporates 739 non-flood images from `virenbr11/pothole-and-plain-rode-images` (365 rain puddles, wet asphalt, and water reflections without flooding + 374 plain dry roads) featuring overlapping camera resolutions (widths $160\text{--}5760\text{ px}$) and balanced with 739 strictly independent Clemson ground-level flood images.
3. **Controlled Model Comparison**: Proves that historical Model V2 collapses to **53.15% accuracy** with a **93.69% False Positive Rate** on genuine non-flooded road images, whereas Model V3 Monsoon achieves **97.75% accuracy (95% CI: 94.84%–99.03%)**, Macro-F1 of **0.9775**, and a False Positive Rate of **0.0090 (0.9%)**.
4. **Monsoon Robustness & Calibration**: Demonstrates superior resilience under torrential rain mist blur (96.85% vs 70.72% for V2), headlight glare (94.59% vs 54.50%), and night darkness (91.89% vs 55.41%).
5. **Operational Safety Gate**: Implements an automated Image Quality Gate (Laplacian blur variance and luminance bounds) intercepting degraded inputs and returning explicit `inconclusive` verdicts to prevent autonomous road-closure errors.

---

## 2. Phase 1: External Evaluation Independence Audit

The independence of the external Clemson evaluation cohort was audited using MD5 digests and 64-bit perceptual difference hashes (`dhash`) against all splits across V1 and V2. Full machine-readable results are recorded in `reports/vision_integrity/external_independence_audit.json`.

### 2.1 Provenance and Licensing
- **Source**: Clemson University FloodIMG (`hhrclemson/flooding-image-dataset`, Version 5)
- **Academic Citation**: Karanjit et al., *Data in Brief* (2023), DOI: [10.1016/j.dib.2023.109164](https://doi.org/10.1016/j.dib.2023.109164).
- **License**: Academic Research / Open Access.
- **Acquisition Nature**: Scraped from Twitter/X and USGS/DOT traffic cameras during hurricane and storm events.
- **Ground Truth**: 100% positive flood photography (contains zero negative or dry road instances).

### 2.2 Leakage & Overlap Audit Findings
| Split Target | Exact MD5 Matches | Perceptual Near-Duplicates ($\text{Hamming} \le 2$) | Leaked Image Sample |
| :--- | :---: | :---: | :--- |
| **Train V1** | 8 | 1 | `Flood_1002.jpg`, `Flood_1023.jpg`, `Flood_1075.jpg` |
| **Val V1** | 4 | 0 | `flood_1037.jpg`, `flood_1042.jpg`, `flood_1113.jpg` |
| **Test V1** | 1 | 0 | `flood_117.jpg` |
| **Train V2** | 0 | 1 | `flood_10.jpg` $\leftrightarrow$ `flood_5175.jpg` |
| **Val V2** | 5 | 7 | `Flood_1002.jpg`, `Flood_1023.jpg`, `Flood_1075.jpg` |
| **Test V2** | 6 | 8 | `Flood_1036.jpg`, `Flood_1099.jpg`, `flood_1037.jpg` |

### 2.3 Methodological Limitations of the 200-Image Positive Cohort
1. **Zero Specificity Measurement**: Evaluating an image classifier on a positive-only dataset ($N=200$ flooded images) provides an estimate of **Recall only**. It cannot compute Precision, False Positive Rate (FPR), True Negative Rate (TNR), Specificity, or Macro-F1.
2. **False Calibration**: Expected Calibration Error (ECE) and Brier scores computed on a 100% positive sample are structurally biased because the model is never evaluated against true negatives.
3. **Deployment Non-Readiness**: Claiming 100% recall on Clemson proved feature transfer for Western flood imagery, but did not establish deployment readiness for urban Hyderabad, where rain-slicked asphalt, open storm drains, and monsoon puddles trigger false alarms if not explicitly trained against.

---

## 3. Phase 2: Shortcut-Resistant Dataset Design (V3)

### 3.1 Source Distribution and Confounding Elimination
To break the artificial $224 \times 224$ dimension confounding, we curated non-flood imagery with authentic ground-level street characteristics:
- **`virenbr11_plain`**: 374 plain asphalt roads, lane markings, curbs, traffic, and dry asphalt.
- **`virenbr11_pothole` (Hard Negatives)**: 365 real road inspection photos capturing rain puddles, standing water in road cracks, wet asphalt reflections, and rain-slick surfaces without flood inundation.
- **`clemson_flood`**: 739 ground-level flooded streets sampled from Clemson FloodIMG, filtered to guarantee **zero MD5 and zero perceptual dhash overlap** with any historical split.

```
Total Curated Images: 1,478 (739 Flood, 739 Non-Flood — 50.0% Exact Balance)
```

### 3.2 Distribution Analysis (Dimensions, Compression, and Color Statistics)
*Detailed analysis recorded in `reports/vision_integrity/v3_source_distribution_analysis.json`:*

| Source Cohort | Count | Mean Width $\pm$ Std | Mean Height $\pm$ Std | Mean File Size | Mean RGB Channels (R, G, B) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Plain Roads (Dry Negatives)** | 374 | $976.3 \pm 691.0\text{ px}$ | $639.7 \pm 504.6\text{ px}$ | $294.4\text{ KB}$ | $(120.2, 121.9, 114.3)$ |
| **Potholes & Puddles (Hard Negatives)** | 365 | $990.6 \pm 718.9\text{ px}$ | $652.6 \pm 512.2\text{ px}$ | $363.8\text{ KB}$ | $(123.0, 120.1, 117.5)$ |
| **Clemson Street Flood (Positives)** | 739 | $1465.0 \pm 744.7\text{ px}$ | $1028.1 \pm 526.0\text{ px}$ | $1036.2\text{ KB}$ | $(119.5, 120.9, 111.4)$ |

**Key Findings:**
1. **Color Statistics Overlap**: All three classes exhibit overlapping RGB channel means ($\approx 120$) and standard deviations ($\approx 50\text{--}60$), preventing trivial color tint shortcuts.
2. **Dimension Overlap**: Both flood and non-flood cohorts feature natural high-resolution camera photography (widths ranging up to $5,760\text{ px}$ and $6,999\text{ px}$).
3. **Unresolved Limitation (Documented with Full Scientific Honesty)**: While the $224 \times 224$ artificial confounding was removed, web-scraped flood images from Clemson average higher resolution than road inspection photos. A metadata decision stump on all dimensions and file size achieves $83.78\%$ test accuracy (down from $97.80\%$ in V1/V2). Thus, visual augmentations and consistent preprocessing remain essential to force semantic feature learning.

### 3.3 Duplicate Clustering & Group-Aware Partitioning
Perceptual difference hashing (`dhash`) and Union-Find graph clustering identified 43 multi-image duplicate and scene clusters. The dataset was partitioned ensuring that **no cluster spans multiple splits**:
- **`train_v3.csv`**: 1,034 images (517 Non-Flood [261 plain, 256 puddles], 517 Flood)
- **`val_v3.csv`**: 222 images (111 Non-Flood [54 plain, 57 puddles], 111 Flood)
- **`test_v3.csv`**: 222 images (111 Non-Flood [50 plain, 61 puddles], 111 Flood)

---

## 4. Phase 3: Controlled Model Comparisons

Four models were compared under identical evaluation on the reserved, unseen `test_v3.csv` ($N=222$):
1. **Model V2 (Historical Checkpoint)**: Trained on `train_v2.csv` (which had $224 \times 224$ non-flood shortcut).
2. **Dimensional Metadata Baseline**: Decision stump using image width, height, aspect ratio, and file size.
3. **Model V3 Clean**: Trained on `train_v3.csv` with standard ImageNet augmentations.
4. **Model V3 Monsoon**: Trained on `train_v3.csv` with realistic monsoon degradation augmentations (Gaussian blur, rain spray jitter, contrast attenuation).

### 4.1 Comparative Evaluation Results Table
*Machine-readable report in `models/vision/v3/comparative_evaluation_v3.json`:*

| Model Baseline | Test Acc | 95% Wilson CI | Macro-F1 | Precision (Flood) | Recall (Flood) | FPR (False Alarm) | FNR (Missed Flood) | ROC-AUC |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Model V2 (Historical)** | **0.5315** | [0.4659, 0.5961] | 0.3998 | 0.5163 | 1.0000 | **0.9369** | 0.0000 | 0.7669 |
| **Dimension Metadata Stump** | 0.8378 | [0.7842, 0.8797] | 0.8163 | 0.9412 | 0.7207 | 0.0450 | 0.2793 | 0.8658 |
| **Model V3 Clean** | **0.9730** | [0.9423, 0.9876] | 0.9730 | 0.9646 | 0.9820 | 0.0360 | 0.0180 | 0.9982 |
| **Model V3 Monsoon** | **0.9775** | [0.9484, 0.9903] | **0.9775** | **0.9907** | 0.9640 | **0.0090** | 0.0360 | 0.9912 |

### 4.2 Confusion Matrices ($N=222$)
- **Model V2 Historical**: $\text{TN}=7,\ \text{FP}=104,\ \text{FN}=0,\ \text{TP}=111$
- **Model V3 Clean**: $\text{TN}=107,\ \text{FP}=4,\ \text{FN}=2,\ \text{TP}=109$
- **Model V3 Monsoon**: $\text{TN}=110,\ \text{FP}=1,\ \text{FN}=4,\ \text{TP}=107$

### 4.3 Subcohort Breakdown: The Hard-Negative Test
When tested specifically on genuine hard negatives (**wet roads, rain puddles, and water reflections without flooding**, $N=61$):
- **Model V2 Historical Accuracy**: **0.0656** (Mean flood probability: **0.9193**). Model V2 misclassified **57 out of 61** wet road images as severe floods!
- **Model V3 Clean Accuracy**: **0.9836** (Mean flood probability: **0.0443**). Only 1 false alarm.
- **Model V3 Monsoon Accuracy**: **0.9836** (Mean flood probability: **0.0455**). Only 1 false alarm.

---

## 5. Phase 4: Realistic Robustness Evaluation

*Full report saved in `reports/vision_integrity/robustness_cohorts_report.json`.*

### 5.1 Real-World Subcohorts
| Cohort Name | Sample $N$ | Selection Criterion | Model V2 Acc (FPR) | Model V3 Clean Acc (FPR) | Model V3 Monsoon Acc (FPR) |
| :--- | :---: | :--- | :---: | :---: | :---: |
| **Puddles & Wet Asphalt** | 61 | Real hard-negative puddle scenes | 0.0656 (0.9344) | 0.9836 (0.0164) | **0.9836 (0.0164)** |
| **Plain Dry Roads** | 50 | Dry asphalt, curbs, street markings | 0.0600 (0.9400) | 0.9400 (0.0600) | **1.0000 (0.0000)** |
| **Flooded Streets** | 111 | Real ground-level flood photography | 1.0000 (0.0000) | 0.9820 (0.0000) | 0.9640 (0.0000) |
| **Real Low-Light** | 21 | Natural images with mean luminance $< 85$ | 0.4286 (1.0000) | 0.9524 (0.0833) | **0.9524 (0.0000)** |

### 5.2 Synthetic Perturbation Cohorts ($N=222$ each)
To isolate vulnerability to optical and environmental degradation during Hyderabad monsoon downpours, controlled perturbations were evaluated across the entire test set:

| Perturbation Cohort | Physical Scenario Simulated | Model V2 Acc | Model V3 Clean Acc | Model V3 Monsoon Acc |
| :--- | :--- | :---: | :---: | :---: |
| **Rain Mist & Spray Blur** | Lens condensation, heavy spray ($\sigma=3.5$) | 0.7072 | 0.9324 | **0.9685** |
| **Night Darkness** | Severe monsoon clouds, darkness ($25\%$ luminance) | 0.5541 | 0.8739 | **0.9189** |
| **Headlight Glare** | Night traffic glare, specular wet reflections | 0.5450 | 0.9234 | **0.9459** |
| **Droplet Obstruction** | Large raindrops adhering to camera lens | 0.5180 | 0.8874 | **0.9234** |
| **Motion Blur** | Vehicle camera vibration / moving shutter | 0.7838 | 0.9595 | **0.9685** |

**Monsoon Augmentation Advantage**: Under severe rain mist blur, Model V2's False Negative Rate rose to $51.35\%$ (missing more than half of flooded streets). Model V3 Clean's FNR rose to $13.51\%$. In contrast, **Model V3 Monsoon maintained an FNR of only 4.50%** and an accuracy of **96.85%**.

---

## 6. Phase 5: Confidence Calibration, Ambiguity Policy & Safety Gate

### 6.1 Calibration Metrics
- **Expected Calibration Error (ECE)**:
  - Model V2: $\text{Test ECE} = \mathbf{0.4526}$ (severely overconfident and miscalibrated).
  - Model V3 Clean: $\text{Test ECE} = \mathbf{0.0134}$ (exceptionally well-calibrated).
  - Model V3 Monsoon: $\text{Test ECE} = \mathbf{0.0237}$.
- **Brier Score**:
  - Model V2: $0.4485$
  - Model V3 Clean: $0.0187$
  - Model V3 Monsoon: $0.0255$
- **High-Confidence Errors ($\text{Confidence} \ge 0.85$ while prediction is wrong)**:
  - Model V2: **96 high-confidence errors** out of 222 samples!
  - Model V3 Clean: **1 high-confidence error**.
  - Model V3 Monsoon: **5 high-confidence errors**.

### 6.2 Empirical Evaluation of the 0.65 Ambiguity Threshold
The platform enforces that any prediction with confidence $< 0.65$ is flagged as `is_ambiguous = True`.
- On Model V3 Clean, predictions in the ambiguous band $[0.50, 0.65)$ had an accuracy of **exactly 50.0%** (equivalent to a random guess).
- Predictions above the $0.65$ threshold achieved **$98.61\%$ accuracy**.
- **Conclusion**: The $0.65$ threshold is mathematically justified and effectively isolates low-confidence guesses for human inspection.

### 6.3 Automated Image Quality Gate
Implemented in `src/sahaay/vision/inference.py`:
1. **Blur Estimation via Laplacian Variance**: Calculates $\text{Var}(\Delta * I)$. If $\text{Var} < 15.0$ and $\sigma_{\text{lum}} > 12.0$, the image is flagged for severe optical blur or lens condensation.
2. **Exposure Boundaries**:
   - Underexposed / Pitch Black: $\mu_{\text{lum}} < 10.0$.
   - Overexposed / Whiteout: $\mu_{\text{lum}} > 248.0$ and $\sigma_{\text{lum}} < 8.0$.
3. **Resolution Minimum**: Rejects images smaller than $64 \times 64$ pixels.

When triggered, the inference service returns:
```json
{
  "predicted_class": "inconclusive",
  "confidence": 0.0,
  "is_inconclusive": true,
  "inconclusive_reasons": ["Image has severe motion smearing or lens condensation blur."],
  "warnings": [
    "IMAGE QUALITY GATE TRIGGERED: Image is too degraded for reliable flood inference.",
    "Inconclusive imagery must NOT trigger autonomous road closure or emergency action."
  ]
}
```

### 6.4 Advisory Policy & Multi-Factor Decision Synthesis
In accordance with municipal flood response best practices:
1. **Visual Evidence is Strictly Advisory**: A vision prediction never directly closes a road.
2. **Autonomous Action Prevention**: Inconclusive or ambiguous visual predictions are clamped to `ADVISORY` in `src/sahaay/decision/contracts.py`, requiring on-site field verification or corroborating high-risk rainfall telemetry before crews are dispatched.

---

## 7. Verification & Regression Tests

The complete test suite runs in PyTorch/pytest (`tests/`):
```powershell
.\.venv\Scripts\python.exe -m pytest -v
```
**Results: 29 passed out of 29 tests (100% pass rate)**.
- `tests/test_vision_v3.py` (10 tests):
  - Split disjointness (zero image ID, hash, or cluster leaks).
  - Strict independence from historical V1 and V2 splits.
  - Class and hard-negative balance verification.
  - Image quality gate rejection of pitch black, low resolution, and severe blur.
  - Decision engine inconclusive safety clamping.
- Existing suites (`test_api_contract`, `test_inference`, `test_dataset`, `test_model`, `test_split_integrity`, `test_transforms`): All 19 passing.
