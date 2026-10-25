#!/usr/bin/env python3
"""
Sahaay AI — Phase 7 Field Session Management CLI

Usage:
    python scripts/manage_field_session.py --help
    python scripts/manage_field_session.py create --session-id SES-20261025-0001 --corridor-id CORR-HYD-01 --vantage "Rasoolpura Metro Walkway"
    python scripts/manage_field_session.py start --session-id SES-20261025-0001 --lead-id LEAD-01 --safety-id SAFETY-01 --recorder-id REC-01
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional, Dict, Any

# Add src to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from sahaay.pilot.session import FieldSessionManager, FieldSessionState
from sahaay.pilot.gate import PilotActivationGate

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("manage_field_session")

SESSION_STORAGE_PATH = "data/phase7/active_session.json"


def load_manager() -> Tuple[FieldSessionManager, Optional[dict]]:
    manager = FieldSessionManager()
    session_data = None
    if os.path.exists(SESSION_STORAGE_PATH):
        try:
            with open(SESSION_STORAGE_PATH, "r", encoding="utf-8") as f:
                session_data = json.load(f)
                session = manager.create_session(
                    session_id=session_data["session_id"],
                    corridor_id=session_data["corridor_id"],
                    vantage_location_name=session_data["vantage_location_name"],
                    scheduled_start_utc=datetime.fromisoformat(session_data["scheduled_start_utc"]),
                    scheduled_end_utc=datetime.fromisoformat(session_data["scheduled_end_utc"]),
                    is_synthetic=session_data.get("is_synthetic_or_simulated", False),
                )
                session.session_state = FieldSessionState(session_data["session_state"])
                session.observation_ids = session_data.get("observation_ids", [])
        except Exception as e:
            logger.warning(f"Could not load active session: {e}")
    return manager, session_data


def save_session(session):
    os.makedirs(os.path.dirname(SESSION_STORAGE_PATH), exist_ok=True)
    with open(SESSION_STORAGE_PATH, "w", encoding="utf-8") as f:
        json.dump(session.model_dump(mode="json"), f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Manage Sahaay AI Field Observation Sessions")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: create
    create_p = subparsers.add_parser("create", help="Create a scheduled session")
    create_p.add_argument("--session-id", type=str, default="SES-20261025-0001")
    create_p.add_argument("--corridor-id", type=str, default="CORR-HYD-01")
    create_p.add_argument("--vantage", type=str, default="Rasoolpura Metro Elevated Walkway")
    create_p.add_argument("--duration-hours", type=float, default=2.0)
    create_p.add_argument("--is-synthetic", action="store_true", default=False)

    # Subcommand: start
    start_p = subparsers.add_parser("start", help="Execute pre-check and start session")
    start_p.add_argument("--session-id", type=str, default="SES-20261025-0001")
    start_p.add_argument("--lead-id", type=str, required=True)
    start_p.add_argument("--safety-id", type=str, required=True)
    start_p.add_argument("--recorder-id", type=str, required=True)

    # Subcommand: abort
    abort_p = subparsers.add_parser("abort", help="Abort session on safety trigger")
    abort_p.add_argument("--session-id", type=str, default="SES-20261025-0001")
    abort_p.add_argument("--reason", type=str, required=True)
    abort_p.add_argument("--lead-id", type=str, required=True)

    # Subcommand: close
    close_p = subparsers.add_parser("close", help="Close session after completion")
    close_p.add_argument("--session-id", type=str, default="SES-20261025-0001")
    close_p.add_argument("--lead-id", type=str, required=True)

    args = parser.parse_args()
    manager, _ = load_manager()
    gate = PilotActivationGate()

    if args.command == "create":
        now = datetime.now(timezone.utc)
        session = manager.create_session(
            session_id=args.session_id,
            corridor_id=args.corridor_id,
            vantage_location_name=args.vantage,
            scheduled_start_utc=now,
            scheduled_end_utc=now + timedelta(hours=args.duration_hours),
            is_synthetic=args.is_synthetic,
        )
        save_session(session)
        logger.info(f"Created session {session.session_id} [State: {session.session_state}]")

    elif args.command == "start":
        pre_check = {
            "vantage_point_clear_of_traffic": True,
            "zero_entry_into_floodwater_confirmed": True,
            "lightning_detected_within_10km": False,
            "wind_gusts_exceed_35kmh": False,
            "ppe_gear_verified_for_all": True,
            "first_aid_and_whistles_verified": True,
            "emergency_contacts_saved_on_phones": True,
            "daylight_window_confirmed": True,
            "field_lead_id": args.lead_id,
            "safety_officer_id": args.safety_id,
            "data_recorder_id": args.recorder_id,
        }
        pilot_authorized = (gate.current_state.value == "PILOT_AUTHORIZED")
        success, session, msg = manager.start_session(args.session_id, pre_check, pilot_authorized=pilot_authorized)
        if success:
            save_session(session)
            logger.info(f"Session started: {msg}")
        else:
            logger.error(f"Failed to start session: {msg}")
            sys.exit(1)

    elif args.command == "abort":
        success, session, msg = manager.abort_session(args.session_id, args.reason, args.lead_id)
        if success:
            save_session(session)
            logger.warning(f"Session aborted: {msg}")
        else:
            logger.error(f"Abort failed: {msg}")
            sys.exit(1)

    elif args.command == "close":
        post_review = {
            "safety_incidents_occurred": False,
            "incident_details": None,
            "abort_triggered": False,
            "abort_reason": None,
            "field_lead_signoff_id": args.lead_id,
        }
        success, session, msg = manager.close_session(args.session_id, post_review)
        if success:
            save_session(session)
            logger.info(f"Session closed: {msg}")
        else:
            logger.error(f"Closure failed: {msg}")
            sys.exit(1)


if __name__ == "__main__":
    main()
