# DRAFT: Data Retention, Deletion, and Access-Control Checklist

> [!IMPORTANT]
> **NOTICE**: This operational checklist defines the physical, cryptographic, and procedural access controls governing all visual data collected under Sahaay AI Phase 3 and beyond.

### 1. Data Storage Architecture & Vault Tiering Checklist
- [ ] **Tier 1 (Raw Ingestion Vault)**:
  - Location: `data/collection_v4/raw/` (Restricted).
  - Contains: Original unredacted image files directly as received from contributors or streams.
  - Security: Encrypted at rest using AES-256. Excluded from git version control (`.gitignore`).
  - Access Restriction: Limited strictly to designated Data Compliance Officers (maximum 2 cleared personnel). Software engineers and model training scripts have ZERO access.
- [ ] **Tier 2 (De-Identified Working Repository)**:
  - Location: `data/collection_v4/processed_privacy/`.
  - Contains: Anonymized derivative copies with verified Gaussian blurring of all faces and license plates.
  - Access: Accessible to annotators, model researchers, and evaluation scripts.
- [ ] **Tier 3 (Public Benchmark Cohorts)**:
  - Location: Versioned public release bundles.
  - Security: Coarsened coordinates ($\sim 1\text{ km}$ precision); metadata stripped of pseudonymous contributor tokens.

---

### 2. Role-Based Access Control (RBAC) Matrix Checklist
- [ ] **Data Compliance Officer**: Full read/write access to Tier 1 and Tier 2; authorization to execute deletions and de-identification pipelines.
- [ ] **Annotation Lead & Adjudicator**: Read access to Tier 2; write access to annotation registers; ZERO access to Tier 1 raw unredacted files.
- [ ] **ML Research Engineer**: Read access to Tier 2 clean model manifests (`isolate_semantic_model_inputs()`); ZERO access to Tier 1 or non-semantic contributor tokens.
- [ ] **External Auditor**: Read access to machine-readable audit reports, exclusion logs, and de-identification verification samples.

---

### 3. Scheduled Retention & Automated Purge Checklist
- [ ] **36-Month Expiry Rule**: Every asset recorded in `acquisition_register.csv` has a mandatory `retention_expiry` timestamp exactly 36 months from capture.
- [ ] **Automated Expiry Monitor**: Scheduled script audits `retention_expiry` monthly. Assets exceeding the retention threshold are flagged for immediate purge.
- [ ] **Cryptographic Destruction**: Deletion of expired assets must use secure unlinking and cryptographic overwriting, followed by logging in the machine-readable exclusion report with reason `retention_expired_purged`.

---

### 4. Citizen Right-to-Erasure Workflow Checklist
When a contributor requests deletion via `privacy@sahaay.ai`:
- [ ] **Step 1 (Receipt & Verification)**: Verify contributor's unique `acquisition_id` or timestamp/corridor details. Log ticket in compliance register.
- [ ] **Step 2 (Raw Vault Purge)**: Locate and delete the source file from `data/collection_v4/raw/`.
- [ ] **Step 3 (Processed Derivative Purge)**: Locate and delete the redacted derivative from `data/collection_v4/processed_privacy/`.
- [ ] **Step 4 (Registry De-Indexing)**: Update `acquisition_register.csv` marking `review_status = rejected_safety` and `exclusion_reason = citizen_erasure_request_fulfilled`.
- [ ] **Step 5 (Timeline Compliance)**: Complete Steps 1–4 within 14 calendar days of receipt.
- [ ] **Step 6 (Confirmation Notice)**: Issue cryptographic confirmation certificate to the requesting citizen.

---
**Compliance Lead Reviewer**: ____________________________________  
**Date Inspected**: ________________________  
**Status**: [ ] Active Compliance Verified  [ ] Action Required
