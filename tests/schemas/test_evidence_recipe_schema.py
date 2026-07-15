from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from pilot_assessment.schemas.export import export_schemas, render_schemas

RECIPE_SCHEMA = "evidence-recipe-0.1.0.schema.json"
OPERATOR_SCHEMA = "operator-definition-0.1.0.schema.json"


def _incomplete_recipe_payload() -> dict[str, object]:
    return {
        "contract_id": "evidence-recipe",
        "contract_version": "0.1.0",
        "recipe_id": "draft.example",
        "recipe_version": 1,
        "anchor": {
            "anchor_id": "EXAMPLE",
            "name": "Incomplete draft",
            "description": "",
            "lifecycle": "active",
            "scientific_status": "starter_template",
        },
        "inputs": [],
        "graph": {
            "nodes": [],
            "edges": [
                {
                    "edge_id": "unfinished",
                    "source": {"node_id": "missing-a", "port_id": "value"},
                    "target": {"node_id": "missing-b", "port_id": "input"},
                }
            ],
        },
        "outputs": [],
        "scoring": None,
        "documentation": {
            "summary": "",
            "assumptions": [],
            "parameter_notes": {},
            "references": [],
        },
        "ui": {"groups": [], "preferred_layout": {}},
    }


def test_rendered_evidence_schemas_have_stable_identity_and_accept_drafts() -> None:
    rendered = render_schemas()

    recipe_schema = json.loads(rendered[RECIPE_SCHEMA])
    operator_schema = json.loads(rendered[OPERATOR_SCHEMA])

    assert recipe_schema["$id"] == ("urn:cranfield:pilot-assessment:schema:evidence-recipe:0.1.0")
    assert operator_schema["$id"] == (
        "urn:cranfield:pilot-assessment:schema:operator-definition:0.1.0"
    )
    assert recipe_schema["x-contract-version"] == "0.1.0"
    assert operator_schema["x-contract-version"] == "0.1.0"
    assert recipe_schema["properties"]["contract_id"]["const"] == "evidence-recipe"
    assert operator_schema["properties"]["contract_id"]["const"] == "operator-definition"

    Draft202012Validator(recipe_schema).validate(_incomplete_recipe_payload())


def test_evidence_recipe_schema_rejects_structurally_invalid_ids() -> None:
    schema = json.loads(render_schemas()[RECIPE_SCHEMA])
    candidate = _incomplete_recipe_payload()
    candidate["recipe_id"] = "bad id"

    assert list(Draft202012Validator(schema).iter_errors(candidate))


def test_exported_evidence_schemas_are_byte_identical_across_targets(
    tmp_path: Path,
) -> None:
    first = tmp_path / "schemas"
    second = tmp_path / "package"

    export_schemas(first, second)

    for name in (RECIPE_SCHEMA, OPERATOR_SCHEMA):
        assert (first / name).read_bytes() == (second / name).read_bytes()
