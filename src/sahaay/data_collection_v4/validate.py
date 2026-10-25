"""
Sahaay AI - Ingestion Validation & Integrity Engine (data_collection_v4)

Validates metadata schemas, audits file decodability, computes cryptographic and perceptual hashes,
performs exhaustive global duplicate clustering beyond sliding windows, and generates auditable
exclusion reports.
"""

import os
import hashlib
from typing import List, Dict, Tuple, Optional, Any
import numpy as np
import pandas as pd
from PIL import Image

from sahaay.data_collection_v4.schemas import (
    AcquisitionRecord,
    ImageAuditResult,
    PermissionStatus,
    PrivacyProcessingStatus,
    ReviewStatus,
)


def compute_dhash(image: Image.Image, hash_size: int = 8) -> str:
    """
    Computes a 64-bit difference hash (dhash) for perceptual similarity comparison.
    Resizes to (hash_size + 1, hash_size), converts to grayscale, and compares adjacent pixels.
    """
    resized = image.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    pixels = list(resized.get_flattened_data()) if hasattr(resized, "get_flattened_data") else list(resized.getdata())
    diff = []
    for row in range(hash_size):
        for col in range(hash_size):
            pixel_left = pixels[row * (hash_size + 1) + col]
            pixel_right = pixels[row * (hash_size + 1) + col + 1]
            diff.append(pixel_left > pixel_right)

    decimal_value = 0
    hex_string = []
    for index, value in enumerate(diff):
        if value:
            decimal_value += 2 ** (index % 8)
        if (index % 8) == 7:
            hex_string.append(hex(decimal_value)[2:].rjust(2, "0"))
            decimal_value = 0
    return "".join(hex_string)


def hamming_distance(hex_hash1: str, hex_hash2: str) -> int:
    """Compute bitwise Hamming distance between two hexadecimal hash strings."""
    try:
        val1 = int(hex_hash1, 16)
        val2 = int(hex_hash2, 16)
        return bin(val1 ^ val2).count("1")
    except Exception:
        return 64


def audit_image_file(file_path: str) -> ImageAuditResult:
    """
    Audits physical existence, decodability, dimensions, cryptographic hashes, and dhash.
    """
    if not os.path.exists(file_path):
        return ImageAuditResult(
            file_path=file_path,
            exists=False,
            decodable=False,
            error_message="File does not exist on disk"
        )

    try:
        file_size_kb = os.path.getsize(file_path) / 1024.0

        with open(file_path, "rb") as f:
            bytes_data = f.read()

        md5 = hashlib.md5(bytes_data).hexdigest()
        sha256 = hashlib.sha256(bytes_data).hexdigest()

        with Image.open(file_path) as img:
            img.verify()

        with Image.open(file_path) as img:
            width, height = img.size
            aspect_ratio = round(width / float(height), 4) if height > 0 else 0.0
            dhash = compute_dhash(img)

        return ImageAuditResult(
            file_path=file_path,
            exists=True,
            decodable=True,
            width=width,
            height=height,
            aspect_ratio=aspect_ratio,
            file_size_kb=round(file_size_kb, 2),
            md5=md5,
            sha256=sha256,
            dhash=dhash
        )
    except Exception as e:
        return ImageAuditResult(
            file_path=file_path,
            exists=True,
            decodable=False,
            file_size_kb=round(os.path.getsize(file_path) / 1024.0, 2) if os.path.exists(file_path) else 0.0,
            error_message=f"Decode/corrupt failure: {str(e)}"
        )


class DisjointSetUnion:
    """Disjoint Set Union (Union-Find) with path compression for clustering."""
    def __init__(self, elements):
        self.parent = {el: el for el in elements}

    def find(self, i):
        if self.parent[i] == i:
            return i
        self.parent[i] = self.find(self.parent[i])
        return self.parent[i]

    def union(self, i, j):
        root_i = self.find(i)
        root_j = self.find(j)
        if root_i != root_j:
            self.parent[root_i] = root_j


def cluster_perceptual_duplicates_exhaustive(
    image_records: List[Dict[str, Any]],
    hamming_threshold: int = 2
) -> Dict[str, str]:
    """
    Exhaustively clusters images across the entire collection (all N x N pairs),
    eliminating any sliding window boundary limitation.
    
    Returns a mapping of {image_id: cluster_id}.
    """
    image_ids = [r["acquisition_id"] for r in image_records]
    dhashes = [r.get("dhash", "") for r in image_records]
    md5s = [r.get("md5", "") for r in image_records]
    n = len(image_records)

    dsu = DisjointSetUnion(image_ids)

    # 1. Exact MD5 grouping
    md5_to_first = {}
    for i, md5 in enumerate(md5s):
        if not md5:
            continue
        if md5 in md5_to_first:
            dsu.union(image_ids[i], md5_to_first[md5])
        else:
            md5_to_first[md5] = image_ids[i]

    # 2. Exhaustive N x N pairwise perceptual hash check
    for i in range(n):
        h_i = dhashes[i]
        if not h_i:
            continue
        for j in range(i + 1, n):
            h_j = dhashes[j]
            if not h_j:
                continue
            dist = hamming_distance(h_i, h_j)
            if dist <= hamming_threshold:
                dsu.union(image_ids[i], image_ids[j])

    # Assign consistent cluster IDs based on root representative
    cluster_mapping = {}
    root_to_cluster_id = {}
    cluster_counter = 1

    for img_id in image_ids:
        root = dsu.find(img_id)
        if root not in root_to_cluster_id:
            root_to_cluster_id[root] = f"cluster_acq_{cluster_counter:05d}"
            cluster_counter += 1
        cluster_mapping[img_id] = root_to_cluster_id[root]

    return cluster_mapping


def validate_acquisition_register(
    register_df: pd.DataFrame,
    check_disk_files: bool = False
) -> Dict[str, Any]:
    """
    Validates a DataFrame of acquisition records.
    Returns:
    {
        "total_records": int,
        "valid_records": int,
        "excluded_records": int,
        "reasons_summary": Dict[str, int],
        "validated_df": pd.DataFrame,
        "exclusion_report": List[Dict[str, Any]]
    }
    """
    validated_rows = []
    exclusions = []
    reason_counts = {}

    for idx, row in register_df.iterrows():
        row_dict = row.to_dict()
        acq_id = str(row_dict.get("acquisition_id", f"UNKNOWN_ROW_{idx}"))

        # Check Pydantic schema validation
        try:
            record = AcquisitionRecord(**row_dict)
        except Exception as schema_err:
            reason = f"schema_validation_error: {str(schema_err)}"
            exclusions.append({"acquisition_id": acq_id, "reason": reason})
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            row_dict["exclusion_reason"] = reason
            validated_rows.append(row_dict)
            continue

        # Check explicit permission
        if record.permission_status != PermissionStatus.APPROVED:
            reason = f"unauthorized_or_pending_permission ({record.permission_status.value})"
            exclusions.append({"acquisition_id": acq_id, "reason": reason})
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            row_dict["exclusion_reason"] = reason
            validated_rows.append(row_dict)
            continue

        # Check privacy status
        if record.privacy_processing_status != PrivacyProcessingStatus.BLURRED_VERIFIED:
            reason = f"privacy_not_verified ({record.privacy_processing_status.value})"
            exclusions.append({"acquisition_id": acq_id, "reason": reason})
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            row_dict["exclusion_reason"] = reason
            validated_rows.append(row_dict)
            continue

        # Check quality/review status
        if record.review_status != ReviewStatus.APPROVED:
            reason = f"review_not_approved ({record.review_status.value})"
            exclusions.append({"acquisition_id": acq_id, "reason": reason})
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            row_dict["exclusion_reason"] = reason
            validated_rows.append(row_dict)
            continue

        # Check file on disk if requested
        if check_disk_files:
            file_ref = str(record.image_or_clip_reference)
            audit = audit_image_file(file_ref)
            if not audit.exists:
                reason = "file_missing_on_disk"
                exclusions.append({"acquisition_id": acq_id, "reason": reason})
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
                row_dict["exclusion_reason"] = reason
                validated_rows.append(row_dict)
                continue
            if not audit.decodable:
                reason = f"corrupt_image_bytes: {audit.error_message}"
                exclusions.append({"acquisition_id": acq_id, "reason": reason})
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
                row_dict["exclusion_reason"] = reason
                validated_rows.append(row_dict)
                continue
            if audit.width < 128 or audit.height < 128:
                reason = f"resolution_below_safety_gate ({audit.width}x{audit.height})"
                exclusions.append({"acquisition_id": acq_id, "reason": reason})
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
                row_dict["exclusion_reason"] = reason
                validated_rows.append(row_dict)
                continue

            row_dict["width"] = audit.width
            row_dict["height"] = audit.height
            row_dict["file_size_kb"] = audit.file_size_kb
            row_dict["md5"] = audit.md5
            row_dict["sha256"] = audit.sha256
            row_dict["dhash"] = audit.dhash

        # Passed all gates
        row_dict["exclusion_reason"] = "none"
        validated_rows.append(row_dict)

    validated_df = pd.DataFrame(validated_rows)
    valid_count = len(validated_df[validated_df["exclusion_reason"] == "none"])
    excluded_count = len(validated_df[validated_df["exclusion_reason"] != "none"])

    return {
        "total_records": len(register_df),
        "valid_records": valid_count,
        "excluded_records": excluded_count,
        "reasons_summary": reason_counts,
        "validated_df": validated_df,
        "exclusion_report": exclusions,
    }
