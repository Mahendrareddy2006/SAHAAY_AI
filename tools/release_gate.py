#!/usr/bin/env python3
r"""
Sahaay AI — Release Gate Verification Script
(tools/release_gate.py)

Deterministic release gate for Sahaay AI:
1. Environment & Tooling Audit (linting, type checking) with explicit SKIP reporting
2. Runtime Configuration & Secrets Hygiene Validation (no secrets exposed)
3. Safety-Critical Regression Verification (decision contracts, abstention, disarmed actuation)
4. Complete Test Suite Execution

Exit Code:
  0: All mandatory release gates passed
  1: One or more release gates failed

Usage:
  python tools/release_gate.py
  # Or via PowerShell from repository root:
  # $env:PYTHONPATH="src;."; .venv/Scripts/python tools/release_gate.py
"""

import os
import sys
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Tuple, Any

# Configure standard streams for cross-platform encoding resilience
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure repository root and src directory are on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Color formatting helpers (ANSI)
USE_COLOR = os.name != "nt" or "WT_SESSION" in os.environ or "TERM" in os.environ
def _c(text: str, color_code: str) -> str:
    return f"\033[{color_code}m{text}\033[0m" if USE_COLOR else text

def green(t: str) -> str: return _c(t, "32")
def red(t: str) -> str: return _c(t, "31")
def yellow(t: str) -> str: return _c(t, "33")
def cyan(t: str) -> str: return _c(t, "36")
def bold(t: str) -> str: return _c(t, "1")


class ReleaseGateRunner:
    def __init__(self):
        self.results: List[Tuple[str, str, str]] = []  # (Stage, Status, Message)
        self.has_failure: bool = False
        self.start_time: float = time.time()

    def record(self, stage: str, status: str, details: str = ""):
        self.results.append((stage, status, details))
        if status == "FAILED":
            self.has_failure = True
            print(f"  {red('[FAILED]')} {stage}: {details}")
        elif status == "PASSED":
            print(f"  {green('[PASSED]')} {stage}: {details}")
        elif status == "SKIPPED":
            print(f"  {yellow('[SKIPPED]')} {stage}: {details}")
        elif status == "INFO":
            print(f"  {cyan('[INFO]')} {stage}: {details}")

    def run_stage_1_lint_and_format(self):
        """Checks for linting and code formatting tools without failing if uninstalled."""
        print(bold("\n=== Stage 1: Code Quality & Linting Tooling Audit ==="))
        
        linters = [
            ("ruff", ["ruff", "check", "src", "tests"]),
            ("flake8", ["flake8", "src", "tests"]),
            ("black", ["black", "--check", "src", "tests"]),
        ]
        
        found_any = False
        for name, cmd in linters:
            bin_path = shutil.which(cmd[0])
            if bin_path:
                found_any = True
                try:
                    res = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=60)
                    if res.returncode == 0:
                        self.record(f"Linting ({name})", "PASSED", "Clean check")
                    else:
                        self.record(f"Linting ({name})", "FAILED", f"Issues detected:\n{res.stdout[:400]}")
                except Exception as e:
                    self.record(f"Linting ({name})", "FAILED", str(e))
            else:
                self.record(f"Linting ({name})", "SKIPPED", f"'{name}' executable not installed in environment")

        if not found_any:
            self.record("Linting Overall", "SKIPPED", "No external linter (ruff/flake8/black) installed in virtualenv")

    def run_stage_2_type_checks(self):
        """Checks for static type analysis tooling without failing if uninstalled."""
        print(bold("\n=== Stage 2: Static Type Analysis Audit ==="))
        
        mypy_bin = shutil.which("mypy")
        if mypy_bin:
            try:
                cmd = ["mypy", "src/sahaay/config.py", "src/sahaay/decision/contracts.py"]
                res = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=60)
                if res.returncode == 0:
                    self.record("Type Checking (mypy)", "PASSED", "Core contracts clean")
                else:
                    self.record("Type Checking (mypy)", "FAILED", f"Type errors:\n{res.stdout[:400]}")
            except Exception as e:
                self.record("Type Checking (mypy)", "FAILED", str(e))
        else:
            self.record("Type Checking (mypy)", "SKIPPED", "'mypy' executable not installed in current environment")

    def run_stage_3_config_and_secrets_validation(self):
        """Validates configuration contracts and ensures zero credentials/secrets exposure."""
        print(bold("\n=== Stage 3: Runtime Configuration & Secrets Hygiene ==="))
        
        try:
            from sahaay.config import get_runtime_config, mask_secret, EnvironmentMode
            cfg = get_runtime_config()
            
            # 1. Verify secrets masking function works and never prints raw values
            dummy_secret = "ghmc_super_secret_auth_token_xyz999"
            masked = mask_secret(dummy_secret)
            if dummy_secret in masked:
                self.record("Secrets Hygiene", "FAILED", "mask_secret() failed to conceal secret payload!")
                return
            if not (masked.startswith("ghm") and masked.endswith("999")):
                self.record("Secrets Hygiene", "FAILED", f"mask_secret format unexpected: {masked}")
                return
            self.record("Secrets Hygiene", "PASSED", f"Secret masking verified: '{masked}'")

            # 2. Safety invariants: Autonomous operations must be strictly barred
            op = cfg.operational
            if op.autonomous_dispatch_enabled:
                self.record("Operational Invariant", "FAILED", "autonomous_dispatch_enabled is TRUE! Must be False.")
                return
            if op.autonomous_closures_enabled:
                self.record("Operational Invariant", "FAILED", "autonomous_closures_enabled is TRUE! Must be False.")
                return
            if op.live_telemetry_stream_enabled:
                self.record("Operational Invariant", "FAILED", "live_telemetry_stream_enabled is TRUE! Must be False.")
                return
            self.record("Safety Invariants", "PASSED", "Autonomous dispatch, closures, and live stream strictly disarmed")

            # 3. Model and labeling metadata
            from sahaay.config import CLASS_NAMES, LABEL_MAP, DEFAULT_CHECKPOINT_PATH
            if CLASS_NAMES != ["not_flooded", "flooded"]:
                self.record("Model Config", "FAILED", f"Unexpected CLASS_NAMES: {CLASS_NAMES}")
                return
            if not DEFAULT_CHECKPOINT_PATH.exists():
                self.record("Model Checkpoint", "FAILED", f"Baseline model not found at {DEFAULT_CHECKPOINT_PATH}")
                return
            self.record("Model Metadata", "PASSED", f"V3 Monsoon checkpoint verified: {DEFAULT_CHECKPOINT_PATH.name}")

            # 4. Pilot gate status check
            from sahaay.pilot.gate import PilotActivationGate, PilotState
            gate = PilotActivationGate()
            current_state = gate._current_state
            if current_state != PilotState.BLOCKED_NOT_READY_FOR_LIVE_PILOT:
                self.record("Pilot Governance Gate", "FAILED", f"Gate state is {current_state}, expected BLOCKED_NOT_READY_FOR_LIVE_PILOT")
                return
            report = gate.generate_activation_status_report()
            summary = report.get("overall_readiness_summary", {})
            total_mand = summary.get("mandatory_prerequisites_total", 0)
            sat_mand = summary.get("mandatory_prerequisites_satisfied", 0)
            pending_count = total_mand - sat_mand
            self.record("Pilot Governance Gate", "PASSED", f"State: {current_state.value} (Mandatory blockers: {pending_count})")

        except Exception as e:
            self.record("Configuration Validation", "FAILED", f"Exception during config inspection: {e}")

    def run_stage_4_safety_regression_tests(self):
        """Runs targeted test suites protecting critical safety and non-inference boundaries."""
        print(bold("\n=== Stage 4: Safety-Critical Regression Suite ==="))
        
        safety_suites = [
            ("Proximity Tier Contracts & Synthesis", "tests/test_hyderabad_risk_pipeline.py"),
            ("Modeled Risk vs Inundation Contracts", "tests/test_phase5_integration.py"),
            ("Image Quality Gate & Abstention Band", "tests/test_image_quality_gate.py"),
            ("End-to-End Workflow Reliability", "tests/test_end_to_end_workflow_reliability.py"),
            ("Production Hardening & Pilot Gates", "tests/test_phase_f_production_hardening_and_pilot_readiness.py"),
        ]
        
        for name, suite_path in safety_suites:
            target = REPO_ROOT / suite_path
            if not target.exists():
                self.record(f"Safety Suite ({name})", "FAILED", f"Missing test file: {suite_path}")
                continue
                
            cmd = [sys.executable, "-m", "pytest", "-q", suite_path]
            env = os.environ.copy()
            env["PYTHONPATH"] = f"{SRC_DIR}{os.pathsep}{REPO_ROOT}"
            
            try:
                res = subprocess.run(cmd, cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=90)
                if res.returncode == 0:
                    summary_line = [l for l in res.stdout.strip().splitlines() if "passed" in l]
                    info = summary_line[-1] if summary_line else "All passed"
                    self.record(f"Safety Suite ({name})", "PASSED", info)
                else:
                    self.record(f"Safety Suite ({name})", "FAILED", f"Test failure:\n{res.stdout[:500]}\n{res.stderr[:300]}")
            except Exception as e:
                self.record(f"Safety Suite ({name})", "FAILED", str(e))

    def run_stage_5_full_test_suite(self):
        """Runs the complete pytest suite across the entire repository."""
        print(bold("\n=== Stage 5: Full Repository Test Suite Execution ==="))
        
        cmd = [sys.executable, "-m", "pytest", "-q"]
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{SRC_DIR}{os.pathsep}{REPO_ROOT}"
        
        try:
            res = subprocess.run(cmd, cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=180)
            lines = res.stdout.strip().splitlines()
            summary_line = [l for l in lines if "passed" in l or "failed" in l]
            summary = summary_line[-1] if summary_line else "Execution finished"
            
            if res.returncode == 0:
                self.record("Complete Test Suite", "PASSED", summary)
            else:
                self.record("Complete Test Suite", "FAILED", f"Failures detected: {summary}\n{res.stdout[-600:]}")
        except Exception as e:
            self.record("Complete Test Suite", "FAILED", f"Test runner execution error: {e}")

    def summarize(self) -> int:
        elapsed = round(time.time() - self.start_time, 2)
        print(bold("\n" + "=" * 70))
        print(bold(f"  SAHAAY AI — RELEASE GATE SUMMARY (Elapsed: {elapsed}s)"))
        print(bold("=" * 70))
        
        passed_count = sum(1 for _, st, _ in self.results if st == "PASSED")
        failed_count = sum(1 for _, st, _ in self.results if st == "FAILED")
        skipped_count = sum(1 for _, st, _ in self.results if st == "SKIPPED")
        
        for stage, status, details in self.results:
            badge = green("[PASS]") if status == "PASSED" else (red("[FAIL]") if status == "FAILED" else yellow("[SKIP]"))
            short_details = details.replace("\n", " ")[:60]
            print(f"  {badge} {stage:<42} | {short_details}")

        print("-" * 70)
        print(f"  Total Checks: {len(self.results)} | Passed: {green(str(passed_count))} | Failed: {red(str(failed_count))} | Skipped: {yellow(str(skipped_count))}")
        
        if self.has_failure:
            print(bold(red("\n[X] RELEASE GATE VERDICT: REJECTED (Mandatory checks failed)")))
            return 1
        else:
            print(bold(green("\n[OK] RELEASE GATE VERDICT: PASSED (All release quality gates satisfied)")))
            return 0


def main():
    runner = ReleaseGateRunner()
    runner.run_stage_1_lint_and_format()
    runner.run_stage_2_type_checks()
    runner.run_stage_3_config_and_secrets_validation()
    runner.run_stage_4_safety_regression_tests()
    runner.run_stage_5_full_test_suite()
    exit_code = runner.summarize()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
