# Sahaay AI — Vision V4 Phase 2 Completion Report: Hyderabad Field Data Acquisition, Consent, and Annotation Infrastructure

## Executive Summary

This report documents the completion of **Phase 2: Hyderabad Field Data Acquisition, Consent, and Annotation Pipeline** for Sahaay AI.

Following the forensic determinations of Phase 1:
- Production training of Vision V4 was formally established as **NO-GO** due to severe source-label confounding in existing datasets (where non-semantic metadata alone predicts the flood label with 85.97% test accuracy).
- Phase 2 establishes the end-to-end data acquisition, consent, de-identification, technical validation, and annotation infrastructure required to make any future V4 training decision scientifically defensible.

> [!IMPORTANT]
> **Strict Distinction Between Tooling and Data**:
> All acquisition registries, ingestion validators, privacy engines, annotation templates, and readiness gates are **fully implemented and verified**.
> However, **zero real-world municipal or citizen imagery has been captured or ingested yet**.
> All candidate corridors remain in `pending` authorization status pending execution of municipal MOUs.

---

## 1. Inventory of Phase 2 Artifacts Created

| Artifact Path | Category | Purpose |
| :--- | :--- | :--- |
| [`docs/vision_v4_hyderabad_acquisition_plan.md`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/docs/vision_v4_hyderabad_acquisition_plan.md) | Policy & Architecture | Operational plan defining 20 candidate corridors, location verification, modalities, privacy, retention, and field safety. |
| [`docs/vision_v4_annotation_guidelines.md`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/docs/vision_v4_annotation_guidelines.md) | Annotation Guidelines | Taxonomy definitions (5 classes), observable evidence requirements, prohibition on depth guessing, and dual-review protocol. |
| [`docs/vision_v4_source_independent_evaluation.md`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/docs/vision_v4_source_independent_evaluation.md) | Evaluation Protocol | Pre-flight criteria, contingency tables, metadata diagnostics, grouped splits, and tri-level evaluation hierarchy. |
| [`data/collection_v4/acquisition_register.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/collection_v4/acquisition_register.csv) | Data Registry | Master registry schema tracking 21 metadata, legal, privacy, and technical fields. (Contains synthetic examples only). |
| [`data/collection_v4/annotation_template.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/collection_v4/annotation_template.csv) | Annotation Template | Standardized dual-annotation template tracking water extent, obstruction evidence, visibility, and confidence. |
| [`data/collection_v4/README.md`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/collection_v4/README.md) | Documentation | Operational guidelines, privacy vaulting, and synthetic fixture demarcation. |
| [`src/sahaay/data_collection_v4/schemas.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/data_collection_v4/schemas.py) | Python Ingestion | Strict Pydantic models and Enums for acquisition records, annotations, and image auditing. |
| [`src/sahaay/data_collection_v4/privacy.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/data_collection_v4/privacy.py) | Python Ingestion | Privacy verification, non-destructive Gaussian blurring, geolocation coarsening, and legal disclaimers. |
| [`src/sahaay/data_collection_v4/validate.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/data_collection_v4/validate.py) | Python Ingestion | Technical image auditing, cryptographic/dhash hashing, exhaustive $N \times N$ duplicate clustering, and exclusion reporting. |
| [`src/sahaay/data_collection_v4/manifest.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/data_collection_v4/manifest.py) | Python Ingestion | Semantic model input isolation, grouped partitioning, and ambiguous cohort preservation. |
| [`scripts/check_v4_data_readiness.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/scripts/check_v4_data_readiness.py) | Audit Tool | Automated decision gate script evaluating sample counts, permissions, privacy, duplicate leaks, and source confounding. |
| [`reports/vision_integrity/v4_annotation_summary.json`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/vision_integrity/v4_annotation_summary.json) | Audit Report | Machine-readable annotation status report documenting zero real images annotated and inter-annotator agreement status. |
| [`reports/vision_integrity/v4_readiness_gate_report.json`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/vision_integrity/v4_readiness_gate_report.json) | Audit Report | Machine-readable readiness report documenting the formal `NO-GO` status and actionable blocking reasons. |
| [`tests/test_vision_v4_collection.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_vision_v4_collection.py) | Test Suite | 15 unit and integration tests covering schemas, corrupt bytes, duplicate clustering, privacy, and readiness. |

---

## 2. Real-World Data Status vs Planned Inventory

To ensure complete scientific integrity, the table below contrasts planned data streams with empirical assets currently in possession:

| Modality / Source | Planned Target | Actual Ingested | Authorization Status | Blocker / Dependency |
| :--- | :---: | :---: | :---: | :--- |
| **GHMC / HTP Municipal CCTV** | 800 images | **0** | `pending` | Formal institutional MOU with GHMC Command & Control (ICCC) undergoing legal review. |
| **Citizen Community Uploads** | 400 images | **0** | `pending` | Citizen upload web interface and terms of service acceptance portal scheduled for launch. |
| **Field Team Public Vantages** | 500 images | **0** | `pending` | Pre-collection safety audits and PPE procurement for 20 candidate corridors. |
| **Commercial Dashcam Fleets** | 300 images | **0** | `pending` | Transit partner data-sharing agreement pending approval. |
| **Total Real-World Assets** | **2,000 images** | **0** | **Pending** | **Real data collection has not commenced.** |

---

## 3. Real-World Ingestion & Exclusion Breakdown

Because real-world data collection has not commenced, counts across all operational categories are strictly zero:

| Category | Dimension | Real-World Count ($N$) | Notes |
| :--- | :--- | :---: | :--- |
| **Class Distribution** | `flooded_road` | **0** | True positive road inundation |
| | `wet_no_visible_inundation` | **0** | Hard negative wet road control |
| | `dry_road` | **0** | Baseline negative control |
| | `ambiguous` | **0** | Preserved for abstention / safety gate evaluation |
| | `out_of_scope` | **0** | Preserved for out-of-distribution evaluation |
| **Corridors** | 20 Candidate Corridors | **0** | Tolichowki, Shaikpet, Begumpet, etc. (all pending) |
| **Exclusions** | Unauthorized / Unapproved | **0** | Ingestion pipeline rejects records with pending/rejected status |
| | Unprocessed Privacy / PII | **0** | Ingestion pipeline rejects unredacted assets |
| | Corrupt / Low Quality | **0** | Ingestion pipeline rejects decode failures or resolution $< 128 \times 128$ |

---

## 4. Annotation Progress & Inter-Annotator Agreement

- **Real Images Annotated**: **0**
- **Inter-Annotator Agreement Status**: `INSUFFICIENT_REAL_DATA`
- **Methodological Ruling**:
  As documented in [`reports/vision_integrity/v4_annotation_summary.json`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/vision_integrity/v4_annotation_summary.json), Cohen's Kappa ($\kappa$) requires paired annotations on genuine field data. Sahaay AI has established a target threshold of $\kappa \ge 0.85$, but **this target is a quality requirement, NOT an empirical finding**. Claiming high agreement prior to collecting real data is scientifically prohibited.

---

## 5. Current Readiness Gate Evaluation

Executing [`scripts/check_v4_data_readiness.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/scripts/check_v4_data_readiness.py) evaluates the current repository state:

```
DECISION: NO-GO
```

### Actionable Blocking Reasons:
1. `Acquisition register contains 0 authorized real-world records. Real-world data collection has not commenced.`
2. `Source-label confounding active: Non-semantic metadata classifier achieves 85.97% test accuracy (threshold limit: 65.0%). Floods and negatives originate from distinct datasets (Clemson vs Virenbr11).`
3. `Insufficient multi-source cross-representation: 0 sources have both classes >= 100 (requires >= 2).`

### Checks Successfully Passed:
- Manifest V4 partitions exist and are intact (`train_v4.csv`, `val_v4.csv`, `test_v4.csv`).
- Zero exact MD5 duplicate leakage crosses V4 split boundaries.
- Historical checkpoints (`best_model.pt`, `model_v2.pt`, `model_v3_monsoon.pt`) and manifests remain 100% preserved.

---

## 6. Verification and Test Suite Execution

The automated test suite was expanded with 15 new unit and integration tests in [`tests/test_vision_v4_collection.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_vision_v4_collection.py).

### Test Suite Execution Output:
```bash
.\.venv\Scripts\python.exe -m pytest -q
```
```
61 passed, 1 warning in 7.09s (100% pass rate)
```

### Coverage Highlights:
- Validation of Pydantic models for permissions, consent references, and geographic bounds.
- Technical file auditing detecting missing files, non-zero file sizes, and corrupt byte sequences.
- Exhaustive $N \times N$ perceptual hashing grouping near-duplicates separated across arbitrary index distances.
- Non-destructive privacy redaction refusing to overwrite raw source files.
- Group-aware split partitioning preventing cluster leakage across train, val, and test splits.
- Readiness gate confirming `NO-GO` on current repo state and validating criteria checks.
- Verification that historical checkpoints and historical manifests have non-zero size and remain unmodified.

---

## 7. Outstanding Dependencies & Recommended Next Steps

To transition the readiness gate from `NO-GO` to `GO`:

1. **Institutional Access**: Finalize and execute the formal Memorandum of Understanding (MOU) with GHMC ICCC and Hyderabad Traffic Police for research access to designated CCTV cameras at candidate locations.
2. **Citizen Upload Portal**: Deploy the public web submission form with mandatory consent checkboxes, privacy notices, and automatic client-side EXIF geotagging.
3. **Field Team Dispatch**: Complete site safety verification on the 20 candidate corridors and conduct the first dry-weather baseline survey.
4. **Monsoon Event Capture**: Capture paired condition imagery (Condition A: dry baseline, Condition B: wet pavement/potholes, Condition C: road inundation) during the upcoming Hyderabad monsoon rainfall events.
5. **Ingestion & Dual Annotation**: Run the ingested images through `validate_acquisition_register()`, `apply_privacy_redaction()`, dual-annotator labeling, and Cohen's Kappa evaluation.
6. **Re-evaluate Readiness Gate**: Re-run `check_v4_data_readiness.py` to confirm that multi-source balance is achieved and source confounding is eliminated before authorizing Vision V4 model training.
