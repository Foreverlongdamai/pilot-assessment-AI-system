"""Load the packaged scene definition and create empty editing templates."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from importlib.resources import files
from typing import Any

from pilot_assessment.scene_assessment.configuration import SEQUENTIAL_INFERENCE_METHOD


class UnsupportedSceneError(ValueError):
    """The requested scene is absent from the packaged registry."""


class UnsupportedSchemaVersionError(UnsupportedSceneError):
    """Unknown document versions must not be interpreted using a newer schema."""

    path = "/schema_version"


def _load_scn001_catalog() -> dict[str, Any]:
    """Build SCN-001 templates; scientific thresholds never receive defaults."""
    resource = files(__package__).joinpath("scn001.json")
    catalog = json.loads(resource.read_text(encoding="utf-8"))
    parameters = {}
    results = {}
    for metric in catalog["metrics"]:
        metric_id = metric["metric_id"]
        results[metric_id] = None
        if metric["rule"] != "interval":
            continue
        kind = metric["parameter_kind"]
        interval = {
            "lower": 0 if kind == "error" else None,
            "upper": None,
            "unbounded_upper": False,
        }
        parameters[metric_id] = {
            "expected": 0 if kind in {"error", "signed"} else None,
            "desired": copy.deepcopy(interval),
            "acceptable": copy.deepcopy(interval),
        }
    identity = {"schema_version": catalog["schema_version"], "scene_id": catalog["scene_id"]}
    catalog["configuration_template"] = {
        **identity,
        "parameters": parameters,
        "skill_models": {},
    }
    catalog["input_template"] = {**identity, "results": results}
    return catalog


DEFAULT_SCENE_ID = "SCN-001"


def _load_scn001_v2_catalog() -> dict[str, Any]:
    resource = files(__package__).joinpath("scn001_v2.json")
    catalog = json.loads(resource.read_text(encoding="utf-8"))
    identity = {"schema_version": "2.0", "scene_id": catalog["scene_id"]}
    metrics = {metric["metric_id"]: metric for metric in catalog["metrics"]}
    parameters = {}
    for key, metric in metrics.items():
        if metric["rule"] == "interval":
            parameters[key] = {
                "expected": None,
                "desired": {"lower": None, "upper": None, "unbounded_upper": False},
                "acceptable": {"lower": None, "upper": None, "unbounded_upper": False},
            }
    inputs, models = {}, {}
    for item in catalog["items"]:
        inputs[item["item_id"]] = {
            "checkpoints": {
                point["checkpoint_id"]: {
                    "values": {
                        key: None
                        for key in point["metric_ids"]
                        if metrics[key]["input_kind"] == "scalar"
                    },
                    "samples": [],
                }
                for point in item["checkpoints"]
            }
        }
        if item["assessment_kind"] == "checklist":
            item.setdefault("skill_name", "检查单完成性")
            item.setdefault("skill_description", "按必需条目的布尔值评价完成性，不推断熟练度。")
            continue
        item.setdefault("skill_name", item["name"] + "表现")
        item.setdefault("skill_description", "时间占比到贝叶斯后验的方法尚待确定。")
        checkpoints = {}
        for point in item["checkpoints"]:
            binary = all(metrics[key]["rule"] != "interval" for key in point["metric_ids"])
            states = ["D", "U"] if binary else ["D", "A", "U"]
            checkpoints[point["checkpoint_id"]] = {
                "states": states,
                "probabilities": [[None] * len(states) for _ in range(3)],
            }
        models[item["item_id"]] = {
            "model_version": "draft-v2",
            "calibration": "uncalibrated",
            "parameter_source": "unconfigured",
            "prior": [None] * 3,
            "state_scores": [None] * 3,
            "checkpoint_models": checkpoints,
        }
    catalog["configuration_template"] = {
        **identity,
        "parameters": parameters,
        "skill_models": models,
    }
    catalog["input_template"] = {**identity, "items": inputs}
    return catalog


# Register each future scene's complete catalog loader here. Navigation and
# evaluation resolve the same registry rather than keeping separate scene lists.
SCENE_CATALOG_LOADERS: dict[str, Callable[[], dict[str, Any]]] = {
    "SCN-001": _load_scn001_catalog,
}

SCENE_CATALOG_LOADERS_V2: dict[str, Callable[[], dict[str, Any]]] = {
    "SCN-001": _load_scn001_v2_catalog,
}


def _load_frame_catalog(resource_name: str) -> dict[str, Any]:
    """Load a packaged v3 scene with editable targets and item frame templates."""
    catalog = json.loads(files(__package__).joinpath(resource_name).read_text(encoding="utf-8"))
    identity = {"schema_version": "3.0", "scene_id": catalog["scene_id"]}
    metrics = {metric["metric_id"]: metric for metric in catalog["metrics"]}
    parameters = {}
    for key, metric in metrics.items():
        if metric["rule"] != "interval":
            continue
        radial = metric["comparison"] == "radial"
        route = metric["comparison"] == "route_3d"
        parameter = {
            "expected": metric.get("default_expected"),
            "desired": {
                "lower": 0 if radial or route else None, "upper": None, "unbounded_upper": False
            },
            "acceptable": {
                "lower": 0 if radial or route else None, "upper": None, "unbounded_upper": False
            },
        }
        if radial:
            parameter.update(center_u=None, center_v=None, target_radius=None)
        if route:
            parameter.update(expected=0, route_points=[])
        if metric.get("target_mode") == "phase_profile":
            parameter["reference_profiles"] = {phase: [] for phase in metric["phase_ids"]}
        elif metric.get("target_mode") == "item_profile":
            parameter.update(expected=None, reference_profile=[])
        parameters[key] = parameter

    inputs, models = {}, {}
    for item in catalog["items"]:
        item_keys = list(dict.fromkeys(
            key for point in item["checkpoints"] for key in point["metric_ids"]
        ))
        inputs[item["item_id"]] = {
            "frames": [
                {
                    "timestamp_s": None,
                    "phase_id": phase["phase_id"],
                    "values": {
                        key: (
                            {"status": None, "u_m": None, "v_m": None}
                            if metrics[key]["comparison"] == "radial" else (
                                {"x_m": None, "y_m": None, "height_m": None}
                                if metrics[key]["comparison"] == "route_3d" else None
                            )
                        ) for key in item_keys
                        if phase["phase_id"] in metrics[key]["phase_ids"]
                    },
                }
                for phase in item["phases"]
            ]
        }
        if item["assessment_kind"] == "checklist":
            continue
        point_models = {}
        for point in item["checkpoints"]:
            binary = all(metrics[key]["rule"] != "interval" for key in point["metric_ids"])
            states = ["D", "U"] if binary else ["D", "A", "U"]
            point_models[point["checkpoint_id"]] = {
                "states": states,
                "probabilities": [[None] * len(states) for _ in range(3)],
            }
        models[item["item_id"]] = {
            "model_version": "draft-v3",
            "inference_method": SEQUENTIAL_INFERENCE_METHOD,
            "compensation": {"alpha": 0.2},
            "calibration": "uncalibrated",
            "parameter_source": "unconfigured",
            "prior": [None] * 3,
            "state_scores": [0, 50, 100],
            "checkpoint_models": point_models,
        }
    catalog["configuration_template"] = {
        **identity, "parameters": parameters, "skill_models": models,
    }
    catalog["input_template"] = {**identity, "items": inputs}
    return catalog


SCENE_CATALOG_LOADERS_V3: dict[str, Callable[[], dict[str, Any]]] = {
    "SCN-001": lambda: _load_frame_catalog("scn001_v3.json"),
    "SCN-002": lambda: _load_frame_catalog("scn002_v3.json"),
}


def _loaders(schema_version):
    if schema_version == "1.0":
        return SCENE_CATALOG_LOADERS
    if schema_version == "2.0":
        return SCENE_CATALOG_LOADERS_V2
    if schema_version == "3.0":
        return SCENE_CATALOG_LOADERS_V3
    raise UnsupportedSchemaVersionError(
        f"不支持 schema_version={schema_version!r}；请使用 1.0、2.0 或 3.0 的对应模板。"
    )


def load_catalog(scene_id: str = DEFAULT_SCENE_ID, schema_version: str = "3.0") -> dict[str, Any]:
    """Return the selected detached catalog; unknown IDs never select a default."""
    if not isinstance(scene_id, str) or not scene_id:
        raise UnsupportedSceneError("请提供已注册场景的非空 scene_id。")
    loader = _loaders(schema_version).get(scene_id)
    if loader is None:
        raise UnsupportedSceneError(f"未注册场景：{scene_id}。")
    catalog = loader()
    if catalog.get("scene_id") != scene_id:
        raise ValueError(f"Registered catalog identity does not match {scene_id}.")
    if catalog.get("schema_version") != schema_version:
        raise UnsupportedSchemaVersionError("场景目录版本不匹配，不能静默转换。")
    return copy.deepcopy(catalog)


def catalog_for_configuration(configuration: Any) -> dict[str, Any]:
    """Resolve explicit configuration identity, without implicit scene fallback."""
    scene_id = configuration.get("scene_id") if isinstance(configuration, dict) else None
    schema_version = (
        configuration.get("schema_version") if isinstance(configuration, dict) else None
    )
    return load_catalog(scene_id, schema_version)


def list_scenes(schema_version: str = "3.0") -> dict[str, Any]:
    """List current registry identities for the shared Studio and scene navigation."""
    scenes = []
    for scene_id in _loaders(schema_version):
        catalog = load_catalog(scene_id, schema_version)
        scenes.append({key: catalog[key] for key in ("scene_id", "name", "description")})
    return {"schema_version": schema_version, "scenes": scenes}
