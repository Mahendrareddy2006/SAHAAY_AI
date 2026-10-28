"""
Sahaay AI - Phase 17: Leakage-Free Evaluation Splitter & Vision Partition Guard
(src/sahaay/flood_risk/evaluation.py)

Implements event-grouped and spatially-grouped evaluation partitioning to prevent
temporal autocorrelation and spatial geographic target leakage.
Guards against contamination from the sealed Vision V4 evaluation partition.
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple, Optional

from sahaay.flood_risk.schemas import EvaluationSplitSpecification

FORBIDDEN_VISION_PARTITIONS = {
    "test.csv",
    "manifest_v4",
    "evaluation_set_metadata.json",
    "evaluation_set",
}


class EventAndSpatialSplitter:
    """
    Protocol for generating leakage-free training and independent evaluation splits.
    Guarantees:
    1. Zero storm event overlap (temporal group isolation).
    2. Zero road segment overlap (spatial group isolation).
    3. Strict barrier preventing reuse of the sealed Vision evaluation partition.
    """

    def __init__(self):
        pass

    def verify_vision_partition_isolation(self, dataset_path_or_name: str):
        """
        Guards against reuse or leakage of the sealed Vision test partition.
        Raises PermissionError if a forbidden vision partition is referenced.
        """
        p_name = Path(dataset_path_or_name).name.lower()
        for forbidden in FORBIDDEN_VISION_PARTITIONS:
            if forbidden in p_name:
                raise PermissionError(
                    f"SEALED_VISION_PARTITION_VIOLATION: '{dataset_path_or_name}' references the locked "
                    "Vision evaluation set. The vision test set is sealed for optical models only and "
                    "is strictly prohibited from reuse in localized flood-risk modeling."
                )

    def generate_splits(
        self,
        event_ids: List[str],
        segment_ids: List[str],
        split_id: str = "SPLIT-EVENT-SPATIAL-v1.0",
        eval_event_fraction: float = 0.25,
        eval_segment_fraction: float = 0.25,
    ) -> EvaluationSplitSpecification:
        """
        Generates disjoint event and spatial partitions.
        """
        unique_events = sorted(list(set(event_ids)))
        unique_segments = sorted(list(set(segment_ids)))

        if len(unique_events) < 2:
            raise ValueError(
                f"Insufficient independent storm events ({len(unique_events)} provided; minimum 2 required) "
                "to construct a leakage-free temporal evaluation holdout."
            )

        if len(unique_segments) < 2:
            raise ValueError(
                f"Insufficient road segments ({len(unique_segments)} provided; minimum 2 required) "
                "to construct a leakage-free spatial evaluation holdout."
            )

        n_eval_events = max(1, int(len(unique_events) * eval_event_fraction))
        n_eval_segments = max(1, int(len(unique_segments) * eval_segment_fraction))

        # Distinct deterministic partitioning
        eval_events = unique_events[-n_eval_events:]
        train_events = unique_events[:-n_eval_events]

        eval_segments = unique_segments[-n_eval_segments:]
        train_segments = unique_segments[:-n_eval_segments]

        # Invariant checks
        event_overlap = bool(set(train_events).intersection(set(eval_events)))
        spatial_overlap = bool(set(train_segments).intersection(set(eval_segments)))

        return EvaluationSplitSpecification(
            split_id=split_id,
            grouping_dimension="independent_storm_event_and_spatial_corridor",
            train_events=train_events,
            eval_events=eval_events,
            train_segments=train_segments,
            eval_segments=eval_segments,
            event_overlap_detected=event_overlap,
            spatial_overlap_detected=spatial_overlap,
            is_leakage_free=not event_overlap and not spatial_overlap,
        )


def create_leakage_free_evaluation_splits(
    event_ids: List[str],
    segment_ids: List[str],
    split_id: str = "SPLIT-EVENT-SPATIAL-v1.0"
) -> EvaluationSplitSpecification:
    """Convenience factory for leakage-free evaluation splits."""
    splitter = EventAndSpatialSplitter()
    return splitter.generate_splits(event_ids, segment_ids, split_id=split_id)
