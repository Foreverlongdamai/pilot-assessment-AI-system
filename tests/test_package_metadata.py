from importlib.metadata import requires, version
from importlib.resources import as_file, files
from inspect import signature
from pathlib import Path

import pilot_assessment
from pilot_assessment.anchors.registry import load_packaged_registry, packaged_registry_fingerprint
from pilot_assessment.contracts.anchor_execution import AnchorRuntimeRegistry

M4_SCHEMA_RESOURCE_NAMES = {
    "anchor-catalog-0.1.0.schema.json",
    "anchor-evaluation-report-0.1.0.schema.json",
    "anchor-execution-plan-0.1.0.schema.json",
    "anchor-measurement-0.1.0.schema.json",
    "anchor-plugin-definition-0.1.0.schema.json",
    "anchor-result-0.2.0.schema.json",
    "anchor-runtime-registry-0.1.0.schema.json",
    "preprocessing-provider-definition-0.1.0.schema.json",
    "resolved-reference-set-0.1.0.schema.json",
    "session-semantic-snapshot-0.1.0.schema.json",
}

M4_PARAMETER_RESOURCE_NAMES = {
    *(f"o{index}-parameters-0.1.json" for index in range(1, 14)),
    *(f"h{index}-parameters-0.1.json" for index in range(1, 6)),
    "movement-events-v1-parameters-0.1.json",
    "gaze-aoi-intervals-v1-parameters-0.1.json",
    "fixation-intervals-v1-parameters-0.1.json",
    "control-physio-windows-v2-parameters-0.1.json",
    "ecg-hr-trace-v1-parameters-0.1.json",
    "eeg-engagement-windows-v1-parameters-0.1.json",
}


def test_package_version_is_single_sourced() -> None:
    assert pilot_assessment.__version__ == "0.1.0"
    assert version("pilot-assessment-system") == pilot_assessment.__version__


def test_m2_runtime_dependencies_are_importable() -> None:
    import PIL
    import polars

    assert polars.__version__
    assert PIL.__version__


def test_m4_runtime_constraints_are_published_in_package_metadata() -> None:
    declared = set(requires("pilot-assessment-system") or ())

    assert {
        "jsonschema>=4.23,<5",
        "numpy>=2.3.4,<2.4",
        "rfc8785>=0.1.4,<0.2",
        "scipy>=1.17,<1.18",
    } <= declared

    import jsonschema

    assert jsonschema.validators.validator_for


def test_m4_public_evaluate_boundary_has_no_registry_policy_or_fault_injection() -> None:
    from pilot_assessment.anchors import evaluate

    assert tuple(signature(evaluate).parameters) == ("request", "sink")


def test_m3_temporal_binding_catalog_is_a_packaged_resource() -> None:
    resource = files("pilot_assessment.synchronization.profile_data").joinpath(
        "m3-temporal-bindings-0.1.json"
    )
    with as_file(resource) as path:
        assert Path(path).is_file()


def test_m4_contract_schemas_are_packaged_resources() -> None:
    package = files("pilot_assessment.schema_resources")
    resource_names = {item.name for item in package.iterdir() if item.name.endswith(".schema.json")}

    assert resource_names >= M4_SCHEMA_RESOURCE_NAMES
    for name in M4_SCHEMA_RESOURCE_NAMES:
        resource = package.joinpath(name)
        with as_file(resource) as path:
            assert Path(path).is_file()
            assert Path(path).read_bytes()


def test_m4_reference_catalog_parameter_schemas_and_empty_registry_are_packaged() -> None:
    profile_package = files("pilot_assessment.anchors.profile_data")
    parameter_package = files("pilot_assessment.anchors.profile_data.parameters")
    anchors_package = files("pilot_assessment.anchors")

    assert profile_package.joinpath("__init__.py").is_file()
    assert parameter_package.joinpath("__init__.py").is_file()
    catalog = profile_package.joinpath("reference-model-v0.1-anchor-catalog.json")
    registry = anchors_package.joinpath("registry-v1.json")
    assert catalog.is_file() and catalog.read_bytes()
    assert registry.is_file() and registry.read_bytes()

    catalog_names = {item.name for item in profile_package.iterdir() if item.name.endswith(".json")}
    registry_names = {
        item.name for item in anchors_package.iterdir() if item.name.endswith(".json")
    }
    assert catalog_names == {"reference-model-v0.1-anchor-catalog.json"}
    assert registry_names == {"registry-v1.json"}

    parameter_names = {
        item.name for item in parameter_package.iterdir() if item.name.endswith(".json")
    }
    assert parameter_names == M4_PARAMETER_RESOURCE_NAMES
    assert len(parameter_names) == 24
    for name in parameter_names:
        assert parameter_package.joinpath(name).read_bytes()


def test_m4_packaged_registry_is_loadable_with_o1_o2_implemented() -> None:
    raw = files("pilot_assessment.anchors").joinpath("registry-v1.json").read_bytes()
    model = AnchorRuntimeRegistry.model_validate_json(raw)

    assert model.contract_id == "anchor-runtime-registry"
    assert model.contract_version == "0.1.0"
    assert tuple(entry.anchor_id for entry in model.entries) == ("O1", "O2")
    assert model.preprocessors == ()

    # The trusted loader accepts the packaged resource and produces a stable fingerprint.
    load_packaged_registry()
    assert packaged_registry_fingerprint() == packaged_registry_fingerprint()
