"""
Sahaay AI - Rainfall Counter Conversion & Quality Control Module
Converts cumulative rain gauge counter readings (Ct) to interval rainfall (ΔR)
with strict preservation of physical invariants, reset handling, and rollover detection.
"""

import math
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from sahaay.hyderabad_risk.schemas import (
    IMDRainfallObservation,
    ObservationQCFlag,
)

# Project Quality Control Threshold: 250.0 mm/hr
# Note: This is an internal project safety QC threshold calibrated against extreme precipitation rates
# (world record ~305 mm/hr, Shangdi 1975), NOT an official IMD universal statutory limit.
DEFAULT_MAX_PHYSICAL_RATE_MM_PER_HR = 250.0


class CounterConversionResult(BaseModel):
    """
    Result of converting a pair of cumulative gauge counter readings into an interval delta.
    Preserves input timestamps, validity status, quality flags, and detailed rejection reasons.
    """
    is_valid: bool = Field(..., description="Whether the calculated interval is valid for risk scoring")
    interval_rainfall_mm: Optional[float] = Field(None, ge=0.0, description="Calculated interval rainfall (mm)")
    qc_flag: ObservationQCFlag = Field(..., description="Quality control classification flag")
    qc_reason: str = Field(..., description="Human-readable explanation of calculation or rejection")
    elapsed_minutes: Optional[float] = Field(None, description="Elapsed time between readings in minutes")
    effective_rate_mm_per_hr: Optional[float] = Field(None, ge=0.0, description="Rate normalized to mm/hr")
    current_time_utc: Optional[datetime] = None
    previous_time_utc: Optional[datetime] = None
    current_counter_mm: Optional[float] = None
    previous_counter_mm: Optional[float] = None


def convert_cumulative_counter_to_interval(
    current_counter_mm: Optional[float],
    current_time_utc: Optional[datetime],
    previous_counter_mm: Optional[float],
    previous_time_utc: Optional[datetime],
    counter_max_mm: Optional[float] = None,
    max_physical_rate_mm_per_hr: float = DEFAULT_MAX_PHYSICAL_RATE_MM_PER_HR,
    configured_daily_reset_utc: Optional[time] = None,
    reset_tolerance_minutes: int = 15,
) -> CounterConversionResult:
    """
    Safely converts two cumulative gauge counter readings into interval rainfall.

    Safety Rules:
    1. Normal non-decreasing counters produce non-negative delta (Ct - Ct-1).
    2. Negative counter deltas must NEVER be clamped to 0.0 mm.
    3. If counter decreases and rollover capacity is unknown and not in a configured reset window,
       return is_valid=False with QC_NEGATIVE_DELTA.
    4. Verified rollover is handled only when counter_max_mm is explicitly supplied and positive.
    5. Daily reset is handled only when configured_daily_reset_utc is explicitly supplied.
    6. Identical or out-of-order timestamps yield QC_TIMESTAMP_ANOMALY with is_valid=False.
    7. Deltas exceeding max_physical_rate_mm_per_hr yield QC_UNPHYSICAL_SPIKE with is_valid=False.
    """
    # 1. Missing inputs check
    if (
        current_counter_mm is None
        or previous_counter_mm is None
        or current_time_utc is None
        or previous_time_utc is None
    ):
        return CounterConversionResult(
            is_valid=False,
            interval_rainfall_mm=None,
            qc_flag=ObservationQCFlag.QC_MISSING_VALUE,
            qc_reason="Missing current or previous counter reading or observation timestamp",
            current_time_utc=current_time_utc,
            previous_time_utc=previous_time_utc,
            current_counter_mm=current_counter_mm,
            previous_counter_mm=previous_counter_mm,
        )

    # 2. Non-finite values check
    if (
        math.isnan(current_counter_mm)
        or math.isinf(current_counter_mm)
        or math.isnan(previous_counter_mm)
        or math.isinf(previous_counter_mm)
    ):
        return CounterConversionResult(
            is_valid=False,
            interval_rainfall_mm=None,
            qc_flag=ObservationQCFlag.QC_MISSING_VALUE,
            qc_reason="Non-finite (NaN or Inf) counter reading encountered",
            current_time_utc=current_time_utc,
            previous_time_utc=previous_time_utc,
            current_counter_mm=current_counter_mm,
            previous_counter_mm=previous_counter_mm,
        )

    # 3. Negative raw counter check
    if current_counter_mm < 0.0 or previous_counter_mm < 0.0:
        return CounterConversionResult(
            is_valid=False,
            interval_rainfall_mm=None,
            qc_flag=ObservationQCFlag.QC_NEGATIVE_VALUE,
            qc_reason=f"Raw counter reading cannot be negative (curr={current_counter_mm}, prev={previous_counter_mm})",
            current_time_utc=current_time_utc,
            previous_time_utc=previous_time_utc,
            current_counter_mm=current_counter_mm,
            previous_counter_mm=previous_counter_mm,
        )

    # 4. Timezone awareness check
    if current_time_utc.tzinfo is None or previous_time_utc.tzinfo is None:
        return CounterConversionResult(
            is_valid=False,
            interval_rainfall_mm=None,
            qc_flag=ObservationQCFlag.QC_TIMESTAMP_ANOMALY,
            qc_reason="Naive datetimes provided; observation timestamps must be timezone-aware UTC",
            current_time_utc=current_time_utc,
            previous_time_utc=previous_time_utc,
            current_counter_mm=current_counter_mm,
            previous_counter_mm=previous_counter_mm,
        )

    # 5. Elapsed time check
    diff_sec = (current_time_utc - previous_time_utc).total_seconds()
    if diff_sec == 0.0:
        return CounterConversionResult(
            is_valid=False,
            interval_rainfall_mm=None,
            qc_flag=ObservationQCFlag.QC_TIMESTAMP_ANOMALY,
            qc_reason="Zero elapsed time between consecutive readings (identical timestamp)",
            elapsed_minutes=0.0,
            effective_rate_mm_per_hr=0.0,
            current_time_utc=current_time_utc,
            previous_time_utc=previous_time_utc,
            current_counter_mm=current_counter_mm,
            previous_counter_mm=previous_counter_mm,
        )
    if diff_sec < 0.0:
        elapsed_m = round(diff_sec / 60.0, 2)
        return CounterConversionResult(
            is_valid=False,
            interval_rainfall_mm=None,
            qc_flag=ObservationQCFlag.QC_TIMESTAMP_ANOMALY,
            qc_reason=f"Negative elapsed time ({elapsed_m} min); observations are out-of-order",
            elapsed_minutes=elapsed_m,
            current_time_utc=current_time_utc,
            previous_time_utc=previous_time_utc,
            current_counter_mm=current_counter_mm,
            previous_counter_mm=previous_counter_mm,
        )

    elapsed_minutes = diff_sec / 60.0
    elapsed_hours = diff_sec / 3600.0
    raw_delta_mm = current_counter_mm - previous_counter_mm

    # 6. Monotonic Non-decreasing Case (raw_delta >= 0.0)
    if raw_delta_mm >= 0.0:
        rate = raw_delta_mm / elapsed_hours
        max_physical_delta = max_physical_rate_mm_per_hr * elapsed_hours

        if raw_delta_mm > max_physical_delta:
            return CounterConversionResult(
                is_valid=False,
                interval_rainfall_mm=None,
                qc_flag=ObservationQCFlag.QC_UNPHYSICAL_SPIKE,
                qc_reason=(
                    f"Calculated rainfall {round(raw_delta_mm, 2)} mm over {round(elapsed_minutes, 1)} min "
                    f"({round(rate, 1)} mm/hr) exceeds project QC threshold of {max_physical_rate_mm_per_hr} mm/hr"
                ),
                elapsed_minutes=round(elapsed_minutes, 2),
                effective_rate_mm_per_hr=round(rate, 2),
                current_time_utc=current_time_utc,
                previous_time_utc=previous_time_utc,
                current_counter_mm=current_counter_mm,
                previous_counter_mm=previous_counter_mm,
            )

        return CounterConversionResult(
            is_valid=True,
            interval_rainfall_mm=round(raw_delta_mm, 2),
            qc_flag=ObservationQCFlag.VALID,
            qc_reason="Normal monotonic counter accumulation",
            elapsed_minutes=round(elapsed_minutes, 2),
            effective_rate_mm_per_hr=round(rate, 2),
            current_time_utc=current_time_utc,
            previous_time_utc=previous_time_utc,
            current_counter_mm=current_counter_mm,
            previous_counter_mm=previous_counter_mm,
        )

    # 7. Counter Decrease Case (raw_delta < 0.0) - NEVER CLAMP TO ZERO!
    
    # Check 7a: Configured source-specific daily reset schedule
    if configured_daily_reset_utc is not None:
        # Check proximity of current_time_utc to the daily reset time
        nominal_reset = current_time_utc.replace(
            hour=configured_daily_reset_utc.hour,
            minute=configured_daily_reset_utc.minute,
            second=configured_daily_reset_utc.second,
            microsecond=0,
        )
        reset_diff_min = abs((current_time_utc - nominal_reset).total_seconds()) / 60.0
        # Also check boundary across midnight (if reset is at 00:00)
        reset_diff_min = min(reset_diff_min, abs(1440.0 - reset_diff_min))

        if reset_diff_min <= reset_tolerance_minutes:
            return CounterConversionResult(
                is_valid=False,
                interval_rainfall_mm=None,
                qc_flag=ObservationQCFlag.QC_GAUGE_RESET,
                qc_reason=(
                    f"Source-documented daily reset window ({configured_daily_reset_utc.strftime('%H:%M')} UTC "
                    f"±{reset_tolerance_minutes}m) detected; counter transition from {previous_counter_mm} mm "
                    f"to {current_counter_mm} mm withheld without fabricating zero rainfall"
                ),
                elapsed_minutes=round(elapsed_minutes, 2),
                current_time_utc=current_time_utc,
                previous_time_utc=previous_time_utc,
                current_counter_mm=current_counter_mm,
                previous_counter_mm=previous_counter_mm,
            )

    # Check 7b: Verified, configured hardware counter rollover
    if counter_max_mm is not None and counter_max_mm > 0.0:
        rollover_delta = (counter_max_mm - previous_counter_mm) + current_counter_mm
        if rollover_delta >= 0.0:
            rollover_rate = rollover_delta / elapsed_hours
            max_physical_delta = max_physical_rate_mm_per_hr * elapsed_hours

            if rollover_delta <= max_physical_delta:
                return CounterConversionResult(
                    is_valid=True,
                    interval_rainfall_mm=round(rollover_delta, 2),
                    qc_flag=ObservationQCFlag.QC_COUNTER_ROLLOVER,
                    qc_reason=(
                        f"Verified hardware counter rollover at capacity {counter_max_mm} mm; "
                        f"delta {round(rollover_delta, 2)} mm is physically plausible"
                    ),
                    elapsed_minutes=round(elapsed_minutes, 2),
                    effective_rate_mm_per_hr=round(rollover_rate, 2),
                    current_time_utc=current_time_utc,
                    previous_time_utc=previous_time_utc,
                    current_counter_mm=current_counter_mm,
                    previous_counter_mm=previous_counter_mm,
                )
            else:
                return CounterConversionResult(
                    is_valid=False,
                    interval_rainfall_mm=None,
                    qc_flag=ObservationQCFlag.QC_UNPHYSICAL_SPIKE,
                    qc_reason=(
                        f"Rollover delta {round(rollover_delta, 2)} mm over {round(elapsed_minutes, 1)} min "
                        f"exceeds project QC threshold of {max_physical_rate_mm_per_hr} mm/hr"
                    ),
                    elapsed_minutes=round(elapsed_minutes, 2),
                    effective_rate_mm_per_hr=round(rollover_rate, 2),
                    current_time_utc=current_time_utc,
                    previous_time_utc=previous_time_utc,
                    current_counter_mm=current_counter_mm,
                    previous_counter_mm=previous_counter_mm,
                )

    # Check 7c: Unexplained counter decrease (unknown cause / sensor malfunction / unconfigured reset)
    return CounterConversionResult(
        is_valid=False,
        interval_rainfall_mm=None,
        qc_flag=ObservationQCFlag.QC_NEGATIVE_DELTA,
        qc_reason=(
            f"Unexplained counter decrease from {previous_counter_mm} mm to {current_counter_mm} mm; "
            f"sensor fault, voltage drop, or unconfigured reset. Negative delta withheld without clamping."
        ),
        elapsed_minutes=round(elapsed_minutes, 2),
        current_time_utc=current_time_utc,
        previous_time_utc=previous_time_utc,
        current_counter_mm=current_counter_mm,
        previous_counter_mm=previous_counter_mm,
    )


def convert_consecutive_gauge_observations(
    current_obs: IMDRainfallObservation,
    previous_obs: Optional[IMDRainfallObservation],
    counter_max_mm: Optional[float] = None,
    max_physical_rate_mm_per_hr: float = DEFAULT_MAX_PHYSICAL_RATE_MM_PER_HR,
    configured_daily_reset_utc: Optional[time] = None,
    reset_tolerance_minutes: int = 15,
) -> CounterConversionResult:
    """
    Convenience wrapper converting two consecutive IMDRainfallObservation records.
    Ensures station identity matches before delegating to convert_cumulative_counter_to_interval.
    """
    if previous_obs is not None and current_obs.station_id != previous_obs.station_id:
        return CounterConversionResult(
            is_valid=False,
            interval_rainfall_mm=None,
            qc_flag=ObservationQCFlag.QC_TIMESTAMP_ANOMALY,
            qc_reason=(
                f"Station mismatch in consecutive readings: current '{current_obs.station_id}' "
                f"vs previous '{previous_obs.station_id}'"
            ),
            current_time_utc=current_obs.observation_time_utc,
            previous_time_utc=previous_obs.observation_time_utc,
            current_counter_mm=current_obs.raw_counter_value_mm,
            previous_counter_mm=previous_obs.raw_counter_value_mm,
        )

    prev_counter = previous_obs.raw_counter_value_mm if previous_obs else None
    prev_time = previous_obs.observation_time_utc if previous_obs else None

    return convert_cumulative_counter_to_interval(
        current_counter_mm=current_obs.raw_counter_value_mm,
        current_time_utc=current_obs.observation_time_utc,
        previous_counter_mm=prev_counter,
        previous_time_utc=prev_time,
        counter_max_mm=counter_max_mm,
        max_physical_rate_mm_per_hr=max_physical_rate_mm_per_hr,
        configured_daily_reset_utc=configured_daily_reset_utc,
        reset_tolerance_minutes=reset_tolerance_minutes,
    )
