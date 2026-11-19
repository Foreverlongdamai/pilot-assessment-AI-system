from __future__ import annotations

import copy
import io
import json

import pytest

from pilot_assessment.scene_assessment import catalog, server
from pilot_assessment.scene_assessment.calculator import evaluate, validate_configuration


def rpc(*requests):
    messages = [("runtime.hello", {"supported_protocols": ["1.0"]}), *requests]
    payload = "".join(
        json.dumps({"jsonrpc": "2.0", "id": index, "method": name, "params": params}) + "\n"
        for index, (name, params) in enumerate(messages)
    )
    output = io.BytesIO()
    assert server.serve(io.BytesIO(payload.encode("utf-8")), output) == 0
    return [json.loads(line) for line in output.getvalue().splitlines()][1:]


def test_registered_scenes_list_matches_catalog_identity_and_is_detached():
    result = catalog.list_scenes("1.0")
    definition = catalog.load_catalog("SCN-001", schema_version="1.0")
    assert result == {
        "schema_version": "1.0",
        "scenes": [
            {key: definition[key] for key in ("scene_id", "name", "description")},
        ],
    }
    assert definition == catalog.load_catalog(schema_version="1.0")
    result["scenes"][0]["name"] = "edited"
    definition["name"] = "edited"
    assert catalog.list_scenes("1.0")["scenes"][0]["name"] != "edited"


@pytest.mark.parametrize("scene_id", ["SCN-999", "", None, False, [], {}])
def test_catalog_rejects_unknown_or_invalid_scene_without_fallback(scene_id):
    with pytest.raises(catalog.UnsupportedSceneError):
        catalog.load_catalog(scene_id, schema_version="1.0")


def test_added_registry_entry_is_listed_loaded_and_evaluated_without_scn001_fallback(monkeypatch):
    # A deliberately tiny test catalog with its own IDs and rule proves routing,
    # rather than changing the production catalog or pretending another scene exists.
    identity = {"schema_version": "1.0", "scene_id": "TEST-SECOND"}
    definition = {
        **identity,
        "name": "test second scene",
        "description": "registry routing fixture",
        "metrics": [
            {"metric_id": "completed", "rule": "must_be_true", "value_type": "boolean"},
        ],
        "items": [
            {
                "item_id": "test-item",
                "name": "test item",
                "checkpoints": [
                    {"checkpoint_id": "test-cp", "name": "test cp", "metric_ids": ["completed"]},
                ],
            },
        ],
        "configuration_template": {**identity, "parameters": {}},
        "input_template": {**identity, "results": {"completed": None}},
    }
    monkeypatch.setitem(catalog.SCENE_CATALOG_LOADERS, "TEST-SECOND", lambda: definition)
    assert [scene["scene_id"] for scene in catalog.list_scenes("1.0")["scenes"]] == [
        "SCN-001",
        "TEST-SECOND",
    ]
    selected = catalog.load_catalog("TEST-SECOND", schema_version="1.0")
    selected["name"] = "local editing does not mutate registered loader data"
    assert definition["name"] == "test second scene"
    configuration = copy.deepcopy(definition["configuration_template"])
    input_data = copy.deepcopy(definition["input_template"])
    input_data["results"]["completed"] = False
    assert validate_configuration(configuration) == {"valid": True, "issues": []}
    report = evaluate(configuration, input_data)
    assert report["scene_id"] == "TEST-SECOND"
    assert report["grade"] == "U"
    assert [item["item_id"] for item in report["items"]] == ["test-item"]
    responses = rpc(
        ("scene.list", {}),
        ("scene.catalog", {"scene_id": "TEST-SECOND", "schema_version": "1.0"}),
        ("scene.validate_configuration", {"configuration": configuration}),
        ("scene.evaluate", {"configuration": configuration, "input": input_data}),
    )
    assert all("error" not in response for response in responses)
    assert responses[0]["result"]["schema_version"] == "3.0"
    assert len(responses[0]["result"]["scenes"]) == 2
    assert responses[1]["result"]["scene_id"] == "TEST-SECOND"
    assert responses[2]["result"]["valid"]
    assert responses[3]["result"]["scene_id"] == "TEST-SECOND"
    assert responses[3]["result"]["grade"] == "U"


@pytest.mark.parametrize("scene_id", ["SCN-999", "", None, False, [], {}])
def test_unknown_configuration_scene_is_validation_error_and_cannot_be_evaluated(scene_id):
    configuration = {"schema_version": "1.0", "scene_id": scene_id, "parameters": {}}
    result = validate_configuration(configuration)
    assert result["valid"] is False
    assert result["issues"] and result["issues"][0]["path"] == "/scene_id"
    with pytest.raises(catalog.UnsupportedSceneError):
        evaluate(configuration, catalog.load_catalog(schema_version="1.0")["input_template"])


def test_scene_list_and_optional_catalog_rpc_are_strict_and_recover_from_unknown_scene():
    configuration = {"schema_version": "1.0", "scene_id": "SCN-999", "parameters": {}}
    responses = rpc(
        ("capabilities.list", {}),
        ("scene.list", {}),
        ("scene.catalog", {}),
        ("scene.catalog", {"scene_id": "SCN-001"}),
        ("scene.list", {"scene_id": "SCN-001"}),
        ("scene.catalog", {"extra": True}),
        ("scene.catalog", {"scene_id": None}),
        ("scene.catalog", {"scene_id": "SCN-999"}),
        ("scene.evaluate", {"configuration": configuration, "input": {}}),
        ("scene.validate_configuration", {"configuration": configuration}),
        ("scene.list", {}),
    )
    assert "scene.list" in responses[0]["result"]["methods"]
    assert responses[1]["result"]["schema_version"] == "3.0"
    assert responses[1]["result"]["scenes"][0]["scene_id"] == "SCN-001"
    assert responses[2]["result"]["scene_id"] == responses[3]["result"]["scene_id"]
    assert [response["error"]["code"] for response in responses[4:9]] == [-32602] * 5
    assert responses[9]["result"]["valid"] is False
    assert responses[9]["result"]["issues"][0]["path"] == "/scene_id"
    assert responses[10]["result"]["scenes"][0]["scene_id"] == "SCN-001"


def test_registry_rejects_loader_with_wrong_scene_identity(monkeypatch):
    monkeypatch.setitem(
        catalog.SCENE_CATALOG_LOADERS,
        "TEST-WRONG",
        lambda: catalog.load_catalog(schema_version="1.0"),
    )
    with pytest.raises(ValueError, match="TEST-WRONG"):
        catalog.load_catalog("TEST-WRONG", schema_version="1.0")
