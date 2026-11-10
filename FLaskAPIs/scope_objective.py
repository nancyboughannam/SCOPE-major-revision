"""Shared, training-derived target normalization for SCOPE and EXP3.

The legacy support is retained only to reproduce the submitted experiments.
New training writes its support into model_manifest.json; both services must
load the same manifest when comparing revised experiments.
"""
import json
import math
from pathlib import Path

LEGACY_SUPPORT = {
    "failure_min": 0.0,
    "failure_max": 0.7353648757016841,
    "dnst_min": 0.5327461065548065,
    "dnst_max": 1.6538610651089858,
}
CPU_FEATURES = {"state_avg_edge_cpu", "state_max_edge_cpu"}
LEGACY_TELEMETRY = "legacy_first_vm_v1"
CURRENT_TELEMETRY = "vm_percent_all_vms_v1"


def validate_support(support):
    result = {key: float(support[key]) for key in LEGACY_SUPPORT}
    if not all(math.isfinite(value) for value in result.values()):
        raise ValueError("Normalization support must be finite")
    if not 0 <= result["failure_min"] < result["failure_max"] <= 1:
        raise ValueError("Failure support must satisfy 0 <= min < max <= 1")
    if not 0 <= result["dnst_min"] < result["dnst_max"]:
        raise ValueError("Service support must satisfy 0 <= min < max")
    return result


def training_support(frame):
    """Call with the training partition only, never validation/test records."""
    return validate_support({
        "failure_min": frame.target_failure_rate.min(),
        "failure_max": frame.target_failure_rate.max(),
        "dnst_min": frame.target_deadline_norm_service_time.min(),
        "dnst_max": frame.target_deadline_norm_service_time.max(),
    })


def manifest_support(manifest):
    if "normalization" not in manifest:
        return dict(LEGACY_SUPPORT), "legacy_reference"
    return validate_support(manifest["normalization"]), "model_manifest"


def load_support(path):
    return manifest_support(json.loads(Path(path).read_text(encoding="utf-8")))


def check_telemetry(manifest, received_schema):
    uses_cpu = any(CPU_FEATURES.intersection(model["features"])
                   for model in manifest["models"])
    if not uses_cpu:
        return
    expected = manifest.get("telemetry_schema", LEGACY_TELEMETRY)
    received = received_schema or LEGACY_TELEMETRY
    if received != expected:
        raise ValueError(f"CPU telemetry mismatch: model={expected}, simulator={received}. "
                         "Retrain with matching telemetry or exclude the two CPU features.")
