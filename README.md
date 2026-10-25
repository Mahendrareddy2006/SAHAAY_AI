# Sahaay AI: Predict. Prevent. Protect.
### Production-Ready AI Flood Intelligence Platform for Hyderabad

---

## Overview
**Sahaay AI** is a modular, AI-powered flood intelligence and early-warning platform designed for Hyderabad. The system synthesizes visual flood evidence from citizen photos, municipal drainage maintenance logs, rainfall observations/forecasts, and geospatial road vulnerability into actionable, explainable risk intelligence.

---

## System Architecture & Components
1. **Flood Vision AI:** MobileNetV3-Small transfer learning baseline for street-level visible flood classification.
2. **Rainfall Risk AI:** Time-aligned rainfall accumulation and forecast hazard projection.
3. **Road Vulnerability AI:** Long-term road segment vulnerability index incorporating historical flood frequency, nala proximity, and verified municipal desilting records.
4. **Decision Engine:** Multi-factor evidence synthesis layer combining visual evidence, rainfall, vulnerability, and freshness decay.

---

## Directory Structure
```
sahaay-ai/
├── data/
│   ├── processed/
│   │   ├── dataset_audit_report.json   # Full empirical audit of all 4 datasets
│   │   ├── full_manifest.csv          # 3,000 verified images
│   │   ├── train.csv                  # 70% stratified training split
│   │   ├── val.csv                    # 15% validation split
│   │   └── test.csv                   # 15% held-out test split
├── docs/
│   ├── architecture.md               # End-to-end system architecture
│   ├── dataset_audit.md              # Detailed dataset audit report
│   └── model_card_flood_vision.md    # Production model card for Flood Vision AI
├── models/
│   └── vision/
│       ├── best_model.pt             # Trained MobileNetV3-Small PyTorch checkpoint
│       ├── model_metadata.json       # Training hyperparameters & metrics
│       └── test_evaluation_results.json # Held-out test evaluation results
├── scripts/
│   ├── audit_datasets.py             # Empirical dataset inspection script
│   ├── prepare_data.py               # Image validation & stratified splitting
│   ├── train_baseline.py             # Reproducible model training script
│   └── evaluate_model.py             # Held-out test set evaluation script
├── src/
│   └── sahaay/
│       ├── config.py                 # System configuration & hyperparameters
│       ├── vision/                   # Vision transforms, dataset, model, inference
│       ├── rainfall/                 # Rainfall risk schemas & contracts
│       ├── vulnerability/            # Road vulnerability index schemas & contracts
│       ├── decision/                 # Decision Engine synthesis contracts
│       └── api/                      # FastAPI schemas, routes, and main app
├── tests/                            # Unit and API contract test suite
├── pyproject.toml
└── README.md
```

---

## Quickstart & Environment Setup

### 1. Prerequisites
- Python 3.12 (CPython)
- `uv` package manager (or standard `pip`)
- NVIDIA CUDA GPU (optional, automatic CPU fallback supported)

### 2. Environment Activation & Dependencies
```powershell
# Virtual environment is at .venv
.\.venv\Scripts\activate

# Install dependencies (if setting up fresh)
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
uv pip install pandas scikit-learn fastapi uvicorn pydantic pytest httpx pillow kagglehub
```

### 3. Run Dataset Audit
```powershell
.\.venv\Scripts\python.exe scripts\audit_datasets.py
```

### 4. Prepare Data & Splits
```powershell
.\.venv\Scripts\python.exe scripts\prepare_data.py
```

### 5. Train Flood Vision Baseline
```powershell
.\.venv\Scripts\python.exe scripts\train_baseline.py
```

### 6. Evaluate on Held-Out Test Set
```powershell
.\.venv\Scripts\python.exe scripts\evaluate_model.py
```

### 7. Run Test Suite
```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m pytest -v tests
```

### 8. Launch API Server
```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m uvicorn sahaay.api.main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive API documentation will be accessible at `http://localhost:8000/docs`.

---

## Safety & Ethics Statement
- **No False Proof of Safety:** A prediction of `not_flooded` from an image model **never** certifies road passability.
- **Prototype Warning:** All model outputs are labeled as prototype intelligence to avoid confusion with official GHMC/NDRF disaster alerts.
