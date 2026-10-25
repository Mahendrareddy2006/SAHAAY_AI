"""
Regression test for External Provenance Reconciliation:
- Verifies that reconciled external provenance report exists and is valid.
- Verifies that zero exact MD5 leaks exist between V3 Test and Train/Val manifests.
- Verifies that historical Clemson 200 overlap is formally recorded.
"""

import os
import json
import pytest

def test_reconciled_provenance_report_exists():
    path = "reports/vision_integrity/reconciled_external_provenance.json"
    assert os.path.exists(path), f"Report not found at {path}"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "methodological_audit_findings" in data
    assert "comparisons" in data

def test_v3_test_exact_md5_independence():
    path = "reports/vision_integrity/reconciled_external_provenance.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    findings = data["methodological_audit_findings"]
    assert findings["exact_md5_overlap_test_v3_vs_train_v3"] == 0
    assert findings["exact_md5_overlap_test_v3_vs_val_v3"] == 0

def test_historical_clemson_200_leakage_is_documented():
    path = "reports/vision_integrity/reconciled_external_provenance.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    leaks = data["methodological_audit_findings"]["historical_clemson_200_leaks"]
    # 36 in Train V1, 37 in Train V2
    assert leaks["exact_md5_train_v1"] == 36
    assert leaks["exact_md5_train_v2"] == 37
