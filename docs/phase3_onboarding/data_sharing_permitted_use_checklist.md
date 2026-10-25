# DRAFT: Data-Sharing & Permitted-Use Verification Checklist

> [!IMPORTANT]
> **NOTICE**: This checklist establishes the minimum legal, technical, and operational conditions required before executing any data-sharing agreement with municipal, institutional, or commercial partners.

### 1. Legal & Governance Scope Checklist
- [ ] **Research Purpose Exclusivity**: Agreement explicitly restricts data use to non-commercial public safety research, urban disaster resilience, and scientific benchmark publication.
- [ ] **Surveillance Prohibition**: Express contractual prohibition against using data for facial recognition, biometric tracking, speed enforcement, or personal surveillance.
- [ ] **Machine Learning Training Rights**: Explicit clause granting Sahaay AI the non-exclusive right to use de-identified imagery for training, validating, and testing computer vision models.
- [ ] **Open Weights / Derivative Policy**: Agreement defines ownership of trained neural network weights. Model weights must be releasable under open scientific licenses (e.g., Apache 2.0 or CC-BY 4.0) without exposing underlying proprietary raw pixels.
- [ ] **No Commercial Resale**: Agreement prohibits selling, licensing, or commercializing raw or derivative imagery to third parties.

### 2. Privacy & Technical Ingestion Checklist
- [ ] **Non-Destructive Vault Storage**: Unredacted raw frames are isolated in an encrypted, restricted vault; only anonymized derivatives are exposed to annotators and training pipelines.
- [ ] **Automated PII Redaction**: Agreement acknowledges that all human faces ($\ge 16 \times 16\text{ px}$) and vehicle license plates will be blurred using automated filters prior to annotation.
- [ ] **Secure Transmission**: Transfers must occur over authenticated TLS 1.3 / HTTPS or secure sFTP. Public cloud buckets without access control are prohibited.
- [ ] **Zero Scraping Mandate**: Ingestion must rely strictly on authorized APIs or scheduled batch drops. Automated scraping of public web streams is strictly forbidden.

### 3. Retention, Audit & Termination Checklist
- [ ] **Defined Retention Schedule**: Maximum storage duration of 36 months from capture timestamp.
- [ ] **Right to Revoke / Termination**: Partner reserves the right to terminate agreement upon 30 days written notice.
- [ ] **Purge Guarantee**: Upon agreement termination, Sahaay AI commits to purging all raw partner imagery within 14 calendar days, retaining only aggregated evaluation metrics and open-source model weights.
- [ ] **Annual Compliance Audit**: Partner retains the right to request an annual machine-readable audit report confirming compliance with privacy redaction and deletion schedules.

---
**Completed By**: ____________________________________  
**Date Reviewed**: ________________________  
**Status**: [ ] Approved for Onboarding  [ ] Revisions Required
