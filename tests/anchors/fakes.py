"""Test doubles for the trusted anchor/preprocessing registry.

Two independent kinds of fake live here:

* class-based fakes (:class:`FakeAnchorPlugin` / :class:`FakePreprocessingProvider`)
  reached only through :meth:`PluginRegistry.from_factories_for_testing`; they never
  enter a trusted namespace;
* source-backed fakes installed under an allowlisted ``pilot_assessment.anchors``
  namespace through :class:`TrustedModuleHarness`.  These prove the exact trusted
  bootstrap and closure verification without shipping a production plugin.
"""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pilot_assessment.anchors import registry
from pilot_assessment.contracts.anchor_execution import (
    AnchorArtifactRecipe,
    AnchorPluginDefinition,
    PreprocessingProviderDefinition,
)

FAKE_ANCHOR_MODULE = "pilot_assessment.anchors.plugins.fake_reference_anchor"
FAKE_ANCHOR_HELPER_MODULE = "pilot_assessment.anchors.plugins.fake_reference_helper"
FAKE_PROVIDER_MODULE = "pilot_assessment.anchors.primitives.fake_reference_provider"

_ANCHOR_ARTIFACT_DESCRIPTOR: dict[str, Any] = {
    "type": "table",
    "fields": [
        {"name": "t_ns", "dtype": "i64", "unit": "ns", "nullable": False},
        {"name": "value", "dtype": "f64", "unit": "ratio", "nullable": False},
    ],
    "canonical_order_keys": ["t_ns"],
}
_PROVIDER_OUTPUT_DESCRIPTOR: dict[str, Any] = {
    "type": "table",
    "fields": [
        {"name": "event_id", "dtype": "utf8", "unit": "id", "nullable": False},
        {"name": "t_ns", "dtype": "i64", "unit": "ns", "nullable": False},
    ],
    "canonical_order_keys": ["t_ns", "event_id"],
}


def fake_anchor_definition() -> AnchorPluginDefinition:
    return AnchorPluginDefinition(
        anchor_id="O1",
        definition_version="0.1.0",
        plugin_id="fake-reference-anchor",
        plugin_version="0.1.0",
        api_version="0.1.0",
        required_streams=("X",),
        required_context_paths=(),
        required_semantic_paths=(),
        required_reference_ids=(),
        dependencies=(),
        parameter_schema_id="o1-parameters-0.1",
        measurement_schema_id="anchor-measurement-0.1.0",
        artifact_recipes=(
            AnchorArtifactRecipe(
                artifact_id="fake-trace",
                kind="sample_trace",
                schema_id="fake-trace-v0.1",
                schema_descriptor=_ANCHOR_ARTIFACT_DESCRIPTOR,
                payload_kind="table",
            ),
        ),
    )


def fake_provider_definition() -> PreprocessingProviderDefinition:
    return PreprocessingProviderDefinition(
        provider_id="fake-reference-provider",
        provider_version="1.0.0",
        api_version="0.1.0",
        required_streams=("U",),
        required_context_paths=(),
        required_semantic_paths=(),
        required_reference_ids=(),
        dependencies=(),
        parameter_schema_id="movement-events-v1-parameters-0.1",
        output_schema_id="fake-provider-output-v0.1",
        output_schema_descriptor=_PROVIDER_OUTPUT_DESCRIPTOR,
        artifact_kind="event_trace",
        output_payload_kind="table",
    )


class FakeAnchorPlugin:
    """A minimal in-process anchor plugin double for factory-injection tests."""

    def definition(self) -> AnchorPluginDefinition:
        return fake_anchor_definition()

    def compute(self, *args: object, **kwargs: object) -> Any:  # pragma: no cover - never invoked
        raise NotImplementedError("fake plugin compute is not exercised by registry tests")


class FakePreprocessingProvider:
    def definition(self) -> PreprocessingProviderDefinition:
        return fake_provider_definition()

    def compute(self, *args: object, **kwargs: object) -> Any:  # pragma: no cover - never invoked
        raise NotImplementedError("fake provider compute is not exercised by registry tests")


def create_fake_plugin() -> FakeAnchorPlugin:
    return FakeAnchorPlugin()


def create_fake_provider() -> FakePreprocessingProvider:
    return FakePreprocessingProvider()


# --------------------------------------------------------------------------- #
# Source-backed trusted-namespace fakes
# --------------------------------------------------------------------------- #

ANCHOR_MODULE_SOURCE = '''\
from pilot_assessment.contracts.anchor_execution import (
    AnchorArtifactRecipe,
    AnchorPluginDefinition,
)


class _Plugin:
    def definition(self):
        return AnchorPluginDefinition(
            anchor_id="O1",
            definition_version="0.1.0",
            plugin_id="fake-reference-anchor",
            plugin_version="0.1.0",
            api_version="0.1.0",
            required_streams=("X",),
            required_context_paths=(),
            required_semantic_paths=(),
            required_reference_ids=(),
            dependencies=(),
            parameter_schema_id="o1-parameters-0.1",
            measurement_schema_id="anchor-measurement-0.1.0",
            artifact_recipes=(
                AnchorArtifactRecipe(
                    artifact_id="fake-trace",
                    kind="sample_trace",
                    schema_id="fake-trace-v0.1",
                    schema_descriptor={
                        "type": "table",
                        "fields": [
                            {"name": "t_ns", "dtype": "i64", "unit": "ns", "nullable": False},
                            {"name": "value", "dtype": "f64", "unit": "ratio", "nullable": False},
                        ],
                        "canonical_order_keys": ["t_ns"],
                    },
                    payload_kind="table",
                ),
            ),
        )

    def compute(self, *args, **kwargs):
        raise NotImplementedError


def create_plugin():
    return _Plugin()
'''

PROVIDER_MODULE_SOURCE = '''\
from pilot_assessment.contracts.anchor_execution import PreprocessingProviderDefinition


class _Provider:
    def definition(self):
        return PreprocessingProviderDefinition(
            provider_id="fake-reference-provider",
            provider_version="1.0.0",
            api_version="0.1.0",
            required_streams=("U",),
            required_context_paths=(),
            required_semantic_paths=(),
            required_reference_ids=(),
            dependencies=(),
            parameter_schema_id="movement-events-v1-parameters-0.1",
            output_schema_id="fake-provider-output-v0.1",
            output_schema_descriptor={
                "type": "table",
                "fields": [
                    {"name": "event_id", "dtype": "utf8", "unit": "id", "nullable": False},
                    {"name": "t_ns", "dtype": "i64", "unit": "ns", "nullable": False},
                ],
                "canonical_order_keys": ["t_ns", "event_id"],
            },
            artifact_kind="event_trace",
            output_payload_kind="table",
        )

    def compute(self, *args, **kwargs):
        raise NotImplementedError


def create_provider():
    return _Provider()
'''

# A plugin whose source imports a sibling closure helper module.
ANCHOR_WITH_HELPER_SOURCE = (
    "from pilot_assessment.anchors.plugins.fake_reference_helper import HELPER_CONSTANT\n"
    + ANCHOR_MODULE_SOURCE
)
HELPER_MODULE_SOURCE = "HELPER_CONSTANT = 3\n"

# A plugin source that performs a forbidden dynamic import.
ANCHOR_DYNAMIC_IMPORT_SOURCE = "import importlib\n" + ANCHOR_MODULE_SOURCE

# A plugin source that imports an out-of-closure local module.
ANCHOR_NAMESPACE_CROSSING_SOURCE = (
    "from pilot_assessment.secret_helpers import leak\n" + ANCHOR_MODULE_SOURCE
)

# A plugin source that locks a numeric distribution.
ANCHOR_WITH_NUMPY_SOURCE = "import numpy\n" + ANCHOR_MODULE_SOURCE


class TrustedModuleHarness:
    """Installs source-backed fake modules under allowlisted trusted namespaces.

    ``add_source`` registers a module for the static-closure walk (``find_spec`` +
    source bytes only, never executed).  ``add_module`` additionally executes the
    module so the trusted loader can import it and call its factory.
    """

    def __init__(self, tmp_path: Path) -> None:
        self._tmp_path = tmp_path
        self._paths: dict[str, Path] = {}
        self._modules: dict[str, object] = {}

    def add_source(self, module_name: str, source: str) -> Path:
        path = self._tmp_path / (module_name.replace(".", "__") + ".py")
        path.write_text(source, encoding="utf-8")
        self._paths[module_name] = path
        return path

    def add_module(self, module_name: str, source: str) -> object:
        path = self.add_source(module_name, source)
        spec = importlib.util.spec_from_file_location(module_name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self._modules[module_name] = module
        return module

    def find_spec(self, name: str) -> Any:
        if name in self._paths:
            return SimpleNamespace(origin=str(self._paths[name]), submodule_search_locations=None)
        return importlib.util.find_spec(name)

    def import_module(self, name: str) -> object:
        if name in self._modules:
            return self._modules[name]
        return importlib.import_module(name)

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(registry, "find_spec", self.find_spec)
        monkeypatch.setattr(registry, "import_module", self.import_module)
