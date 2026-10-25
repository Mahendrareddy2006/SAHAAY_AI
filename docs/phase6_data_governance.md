# Sahaay AI — Phase 6 Data Governance & Compliance Specification

**Document Version:** 1.0.0  
**Status:** Approved Data Governance Framework  
**Date:** 2026-10-25  
**Governing Standard:** Digital Personal Data Protection (DPDP) Act 2023 (India)  

---

## 1. Overview and Core Governance Mandates

The Phase 6 data governance framework establishes the physical, logical, and cryptographic boundaries protecting data collected by, ingested into, or evaluated within Sahaay AI.

### Core Governance Principles:
1. **Separation of Raw, Restricted, and Analysis-Ready Data:** Raw observations and identifiable buffers must never mix directly with sanitized machine learning datasets.
2. **Immutable Provenance Tracking:** Every record preserves its ingestion timestamp, schema version (`2.0.0`), pipeline version, observer pseudonym, and raw hash.
3. **Non-Destructive Deduplication:** Duplicates are flagged with links to their canonical counterpart (`DUPLICATE_OF: ID`); the original raw submission is never silently purged.
4. **Quarantine of Synthetic and Simulated Records:** Synthetic fixtures (e.g. demonstration scenarios, unit test inputs) are strictly partitioned and cannot enter ground-truth benchmark vaults.
5. **Privacy and Right to Erasure:** Under Section 12 of the DPDP Act 2023, data principals have the right to withdrawal and erasure. Citizen submissions must support de-identification and automated deletion workflows within 14 days of an erasure request.

---

## 2. Data Tier Architecture

```
+--------------------------------------------------------------------------------------------------+
|                                      DATA TIER ARCHITECTURE                                      |
+--------------------------------------------------------------------------------------------------+
|                                                                                                  |
|   TIER 0: QUARANTINE VAULT (`data/phase6/vault/quarantine/`)                                     |
|   - Holds malformed, corrupted, unauthorized, or synthetic test records.                         |
|   - Fully isolated from analytical engines and evaluation benchmarks.                            |
|                                                                                                  |
|   TIER 1: RAW RESTRICTED VAULT (`data/phase6/vault/raw/`)                                        |
|   - Immutable append-only write store for verified ground-truth submissions.                     |
|   - Encrypted with AES-256; restricted to authorized data stewards.                              |
|   - Preserves original raw coordinates, timestamped sensor headers, and audit trails.            |
|                                                                                                  |
|   TIER 2: DE-IDENTIFIED & REDACTED REPOSITORY (`data/phase6/vault/deidentified/`)                |
|   - Coordinates coarsened to 3 decimal places (~110m residential privacy perimeter).            |
|   - Reporter phone/email hashed with HMAC-SHA-256 (`ANON-xxxxxxxx`).                             |
|   - Observer IDs pseudonymized (`OBSERVER-F01`).                                                 |
|   - Imagery processed through pedestrian face and vehicle license plate blurring.                |
|                                                                                                  |
|   TIER 3: ANALYSIS-READY GROUND-TRUTH BENCHMARK (`data/phase6/vault/analysis_ready/`)            |
|   - Cleaned, quality-flagged, supervisor-verified observation sets.                              |
|   - Spatially and temporally partitioned for unbiased, leak-free model evaluation.               |
|                                                                                                  |
+--------------------------------------------------------------------------------------------------+
```

---

## 3. Handling Synthetic and Simulated Data

To avoid scientific pollution where simulated test cases are mistakenly counted as empirical evidence:
- Every synthetic file must declare `"is_synthetic_or_simulated": true`.
- The `ObservationIngestionPipeline` automatically routes any record with this flag to `TIER 0: QUARANTINE VAULT`.
- The audit report explicitly outputs:
  ```json
  "real_world_field_data_acquired": 0
  ```
  ensuring no dashboard or audit can misrepresent synthetic test fixtures as real Hyderabad ground-truth observations.

---

## 4. Retention and Deletion Lifecycle

| Data Stream | Active Retention | Archival Limit | Deletion / Redaction Standard |
| :--- | :---: | :---: | :--- |
| **Field Observations** | 12 months | 36 months | De-identified tabular logs preserved; unredacted raw buffer purged after 30 days. |
| **Citizen Reports** | 6 months | 12 months | Immediate coordinate coarsening; right-to-erasure purged within 14 days. |
| **Telemetry Replay** | 24 months | 60 months | Archived historical AWS records; zero PII. |
| **CCTV Feeds (Quarantined)** | 0 days (Live buffer) | 30 days | Strictly quarantined; on-edge face/plate redaction required prior to persistence. |
