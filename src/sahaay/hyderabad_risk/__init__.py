"""
Sahaay AI - Hyderabad Geospatial & Rainfall Risk AI Package
Implements data validation, geospatial feature engineering, and explainable risk baselines.
"""

from sahaay.hyderabad_risk.schemas import (
    DrainLine,
    FloodingHotspot,
    GeospatialRiskFeatureVector,
    IMDRainfallObservation,
    IMDStationType,
    MeasurementMode,
    ObservationQCFlag,
    RainfallRiskResult,
    RoadVulnerabilityResult,
    WaterBody,
)
from sahaay.hyderabad_risk.rainfall_engine import (
    evaluate_rainfall_risk_engine,
    evaluate_rainfall_risk_from_adapter,
    evaluate_rainfall_risk_from_observations,
)
from sahaay.hyderabad_risk.vulnerability_engine import evaluate_road_vulnerability_engine
from sahaay.hyderabad_risk.counter_conversion import (
    CounterConversionResult,
    convert_consecutive_gauge_observations,
    convert_cumulative_counter_to_interval,
)
from sahaay.hyderabad_risk.features import (
    aggregate_observations_to_rolling_windows,
    normalize_and_deduplicate_observations,
)

__all__ = [
    "FloodingHotspot",
    "DrainLine",
    "WaterBody",
    "GeospatialRiskFeatureVector",
    "RainfallRiskResult",
    "RoadVulnerabilityResult",
    "IMDRainfallObservation",
    "IMDStationType",
    "MeasurementMode",
    "ObservationQCFlag",
    "CounterConversionResult",
    "convert_cumulative_counter_to_interval",
    "convert_consecutive_gauge_observations",
    "normalize_and_deduplicate_observations",
    "aggregate_observations_to_rolling_windows",
    "evaluate_rainfall_risk_engine",
    "evaluate_rainfall_risk_from_observations",
    "evaluate_rainfall_risk_from_adapter",
    "evaluate_road_vulnerability_engine",
]
