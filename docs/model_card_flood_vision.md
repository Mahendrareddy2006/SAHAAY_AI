# Model Card — Sahaay Flood Vision AI
**Model Name:** `mobilenet_v3_small_flood`  
**Model Version:** `1.0.0`  
**Release Date:** 2026-10-25  
**Model Type:** Binary Image Classification (Visible Flooding vs No Visible Flooding)  
**Framework:** PyTorch 2.6.0+cu124, Torchvision 0.21.0+cu124  
**Maintainer:** Senior AI/ML Engineer (Team Member A)

---

## 1. Model Overview & Purpose

### Intended Use
- **Primary Function:** Analyze citizen-submitted smartphone photos or field team images to determine if visual evidence of standing water, road inundation, or waterlogging is present.
- **Application Context:** Fed into the Sahaay AI Decision Engine alongside rainfall accumulation data and road vulnerability indices to support urban flood monitoring in Hyderabad.
- **Target Audience:** Citizens seeking local road hazard awareness, municipal response teams (GHMC/NDRF), and traffic dispatchers.

### Out-of-Scope & Prohibited Uses
> **CRITICAL SAFETY DIRECTIVE:**
> 1. **No Proof of Safety:** A prediction of `not_flooded` **NEVER** certifies that a road is safe, passable, or devoid of subsurface current, open manholes, or structural damage.
> 2. **Prototype Warning:** This model is an assistive visual triage tool. Predictions **MUST NOT** be broadcast as official emergency evacuations or statutory flood warnings without municipal verification.
> 3. **Aerial Drone Stream Mismatch:** This model is trained for eye-level and street-level photography. It must not be deployed on high-altitude nadir drone or satellite imagery without a domain-specific aerial adapter.

---

## 2. Architecture & Parameters

- **Base Backbone:** `torchvision.models.mobilenet_v3_small` pretrained on ImageNet-1K.
- **Head:** Linear classifier (`1024 -> 2` classes).
- **Total Parameters:** 1,519,906.
- **Trainable Parameters:** 1,519,906.
- **Model Checkpoint Size:** 17.64 MB.
- **Inference Latency:**
  - GPU (NVIDIA RTX 2050): **13.96 ms / image**
  - CPU (Intel/AMD x86_64): **~28.4 ms / image**

---

## 3. Training & Validation Data

- **Primary Source:** Curated ground-level multi-source disaster and street imagery dataset (`roham1/flood-classification-dataset`).
- **Total Dataset Size:** 3,000 images (50% flooded, 50% non-flooded).
- **Partitioning (Disjoint Stratified Split):**
  - **Training Set (70%):** 2,100 images (1,050 flooded, 1,050 not_flooded).
  - **Validation Set (15%):** 450 images (225 flooded, 225 not_flooded).
  - **Held-Out Test Set (15%):** 450 images (225 flooded, 225 not_flooded).
- **Optimization Details:**
  - Loss Function: Cross-Entropy Loss (`nn.CrossEntropyLoss`).
  - Optimizer: AdamW (`lr=3e-4`, `weight_decay=1e-4`).
  - Scheduler: CosineAnnealingLR (T_max=5).
  - Batch Size: 32.
  - Epochs: 5 (Best checkpoint selected at Epoch 4 based on Validation Macro-F1).
  - Random Seed: 42 (fully reproducible).

---

## 4. Evaluation Metrics (Held-Out Test Set)

Evaluated strictly on the untouched 450-image held-out test split:

| Metric | Score | Support |
| :--- | :--- | :--- |
| **Accuracy** | **1.0000** | 450 images |
| **Macro-F1** | **1.0000** | 450 images |
| **Precision (Not-Flooded)** | 1.0000 | 225 images |
| **Recall (Not-Flooded)** | 1.0000 | 225 images |
| **F1-Score (Not-Flooded)** | 1.0000 | 225 images |
| **Precision (Flooded)** | 1.0000 | 225 images |
| **Recall (Flooded)** | 1.0000 | 225 images |
| **F1-Score (Flooded)** | 1.0000 | 225 images |

### Confusion Matrix
```
                    Predicted Not-Flooded    Predicted Flooded
Actual Not-Flooded           225 (TN)                  0 (FP)
Actual Flooded                 0 (FN)                225 (TP)
```
- **False Positives:** 0 (0.0%)
- **False Negatives:** 0 (0.0%)

---

## 5. Input Preprocessing Pipeline

- **Inference Preprocessing:**
  1. Input validation: MIME check (`image/jpeg`, `image/png`, `image/webp`), size <= 15MB, PIL integrity verification.
  2. Color space: Convert to RGB (handles RGBA and grayscale).
  3. Spatial transform: Resize to 256x256, CenterCrop to 224x224.
  4. Tensor normalization: ImageNet Mean `[0.485, 0.456, 0.406]`, Std `[0.229, 0.224, 0.225]`.

---

## 6. Known Limitations & Mitigation

1. **Severe Weather Lighting:** Heavy monsoon downpours, night scenes, or intense water reflections can produce ambiguous visual features.
   - *Mitigation:* Built-in ambiguity detection (`is_ambiguous = True` when confidence < 0.65).
2. **Water vs Puddle vs Inundation:** Shallow puddles on non-sloped asphalt may trigger weak positive scores.
   - *Mitigation:* The Decision Engine does not trigger emergency alerts without corroborating rainfall intensity or multiple citizen reports.
3. **Perspective Shift:** Citizen photos taken from upper-floor balconies exhibit partial oblique views.
   - *Mitigation:* MobileNetV3 random crop training provides scale invariance, but future fine-tuning on Hyderabad-specific community captures is scheduled in Phase 2.
4. **Dataset-Source Confounding & Shortcut Learning:**
   - *Critical Notice:* The 100% held-out test score on `roham1/flood-classification-dataset` reflects benchmark-specific partition artifacts and environmental shortcuts rather than generalized flood physics.
   - *Limitation:* Internal evaluation results **do NOT establish real-world generalization or accuracy on Hyderabad urban roads** during active monsoon cloudbursts.
5. **No Water Depth or Road Passability Assessment:**
   - *Critical Notice:* Binary image classification indicates the visual appearance of surface water only. It **NEVER assesses water depth, flow velocity, manhole displacement, or vehicle passability**.
   - *Mitigation:* The Decision Engine treats vision output as provisional unverified evidence and strictly abstains (`inconclusive`) on underexposed images or confidence scores within the `[0.35, 0.65]` band.

