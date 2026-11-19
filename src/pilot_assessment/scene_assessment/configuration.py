"""Upgrade known frame-configuration metadata into the sole current method."""

from __future__ import annotations

import copy

SEQUENTIAL_INFERENCE_METHOD = "sequential_bayes_compensation_v1"
_RETIRED_FRAME_METHOD = "demo_normalized_grade_likelihood_v1"


def normalize_configuration(configuration, catalog):
    """Return a detached configuration; never invent missing priors or CPTs.

    Only known pre-upgrade v3 metadata is migrated. Unknown methods, current
    parameters and invalid structures remain unchanged so validation can reject
    them. Removed process parameters cannot select a second inference engine.
    """
    normalized = copy.deepcopy(configuration)
    if (
        not isinstance(normalized, dict)
        or catalog.get("schema_version") != "3.0"
        or normalized.get("schema_version") != "3.0"
    ):
        return normalized
    models = normalized.get("skill_models")
    if not isinstance(models, dict):
        return normalized
    for model in models.values():
        if not isinstance(model, dict):
            continue
        if model.get("inference_method") in (None, _RETIRED_FRAME_METHOD):
            model["inference_method"] = SEQUENTIAL_INFERENCE_METHOD
            model.pop("process_model", None)
            model.setdefault("compensation", {"alpha": 0.2})
    return normalized
