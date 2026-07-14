"""Trusted packaged anchor/preprocessing registry and closure verifier.

This module resolves executable :class:`AnchorPlugin` / :class:`PreprocessingProvider`
factories from the packaged ``registry-v1.json`` resource.  It is deliberately a
*trusted* loader:

* it imports only the explicitly declared ``pilot_assessment.anchors.plugins.*``
  anchor factories and ``pilot_assessment.anchors.primitives.*`` preprocessing
  factories -- it never scans a directory, never consults entry points, and never
  ``eval``s a string into a callable;
* before a factory is trusted it is bound to an immutable identity: definition,
  parameter/measurement, artifact/output schema hashes, the static local import
  closure of the factory source, declared resource bytes, and the locked
  Python/numeric runtime must all match the registry entry, and the recomputed
  ``implementation_digest`` must equal the declared one.

Fake factories used by tests never enter the trusted namespaces; they are reachable
only through :meth:`PluginRegistry.from_factories_for_testing`.
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from importlib import import_module
from importlib.resources import files
from importlib.util import find_spec
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Literal, NoReturn, cast

from pydantic import JsonValue

from pilot_assessment.anchors.catalog import CatalogResourceError, parameter_schema_sha256
from pilot_assessment.anchors.fingerprint import (
    distribution_content_identity,
    plugin_definition_fingerprint,
    plugin_implementation_digest_payload,
    preprocessing_definition_fingerprint,
    preprocessing_implementation_digest_payload,
    python_runtime_identity,
    runtime_registry_fingerprint,
    schema_descriptor_sha256,
    typed_json_sha256,
)
from pilot_assessment.anchors.protocols import AnchorPlugin, PreprocessingProvider
from pilot_assessment.contracts.anchor_execution import (
    AnchorCapabilityStatus,
    AnchorPluginDefinition,
    AnchorRuntimeRegistry,
    ContentMemberIdentity,
    NumericRuntimeIdentity,
    PluginRegistryEntry,
    PreprocessingProviderDefinition,
    PreprocessingRegistryEntry,
)
from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity

PluginKey = tuple[str, str]
PreprocessorKey = tuple[str, str]

PreprocessingCapabilityStatus = Literal[
    "available", "provider_unavailable", "not_implemented", "incompatible"
]

_ROOT_PACKAGE = "pilot_assessment"
_PLUGIN_NAMESPACE = "pilot_assessment.anchors.plugins"
_PREPROCESSING_NAMESPACE = "pilot_assessment.anchors.primitives"
_SCHEMA_RESOURCE_PACKAGE = "pilot_assessment.schema_resources"
_REGISTRY_RESOURCE_PACKAGE = "pilot_assessment.anchors"
_REGISTRY_RESOURCE_NAME = "registry-v1.json"

# Trusted local modules a plugin/provider may import without them counting as part
# of its behaviour closure.  Everything else under ``pilot_assessment`` that is not
# a closure member is a namespace violation.  Later M4 tasks that introduce shared
# temporal/scoring helpers add those modules to ``_CLOSURE_MEMBER_PREFIXES``.
_FRAMEWORK_MODULE_PREFIXES = (
    "pilot_assessment.contracts",
    "pilot_assessment.anchors.protocols",
    "pilot_assessment.anchors.models",
    "pilot_assessment.anchors.fingerprint",
    "pilot_assessment.anchors.catalog",
    "pilot_assessment.anchors.registry",
    "pilot_assessment.anchors.reference_resolution",
    "pilot_assessment.synchronization",
)
_CLOSURE_MEMBER_PREFIXES = (_PLUGIN_NAMESPACE, _PREPROCESSING_NAMESPACE)

# Numeric distributions whose installed wheel identity a plugin closure may lock.
# The map is import-top-level-name -> installed distribution name.
_PERMITTED_NUMERIC_DISTRIBUTIONS: Mapping[str, str] = {
    "numpy": "numpy",
    "scipy": "scipy",
    "polars": "polars",
    "pyarrow": "pyarrow",
}

# Exported contract schemas that may back a plugin measurement schema id.  They
# resolve only through ``schema_resources/<schema-id>.schema.json``.
_MEASUREMENT_SCHEMA_IDS = frozenset({"anchor-measurement-0.1.0"})

_PLUGIN_DIGEST_TYPE = "anchor-plugin-implementation-digest"
_PREPROCESSING_DIGEST_TYPE = "preprocessing-provider-implementation-digest"
_DIGEST_VERSION = "0.1.0"

_DYNAMIC_IMPORT_NAMES = frozenset({"__import__"})
_DYNAMIC_IMPORT_MODULES = frozenset({"importlib"})


class RegistryError(ValueError):
    """Raised when a registry entry violates its trusted-closure contract."""


class RegistryResolutionError(RegistryError):
    """Raised when a requested plugin/provider cannot be resolved to a factory."""


@dataclass(frozen=True, slots=True)
class PluginCapability:
    status: AnchorCapabilityStatus
    entry: PluginRegistryEntry | None
    diagnostics: tuple[DomainErrorData, ...]


@dataclass(frozen=True, slots=True)
class PreprocessingCapability:
    status: PreprocessingCapabilityStatus
    entry: PreprocessingRegistryEntry | None
    diagnostics: tuple[DomainErrorData, ...]


def _diagnostic(error_code: str, message: str) -> DomainErrorData:
    return DomainErrorData(
        error_code=error_code,
        severity=ErrorSeverity.ERROR,
        recoverable=False,
        message=message,
        remediation="Rebuild the registry entry with `refresh` from the exact factory.",
    )


# --------------------------------------------------------------------------- #
# Trusted module resolution
# --------------------------------------------------------------------------- #


def _require_trusted_namespace(module_name: str, allowed_namespace: str) -> None:
    if module_name != allowed_namespace and not module_name.startswith(f"{allowed_namespace}."):
        raise RegistryError(
            f"factory module {module_name!r} lies outside {allowed_namespace!r}"
        )


def _import_trusted_module(module_name: str, allowed_namespace: str) -> ModuleType:
    _require_trusted_namespace(module_name, allowed_namespace)
    try:
        return import_module(module_name)
    except ImportError as error:
        raise RegistryError(f"cannot import trusted factory module {module_name!r}") from error


def _resolve_factory(
    module: ModuleType, symbol: str
) -> Callable[[], object]:
    if type(symbol) is not str or not symbol:
        raise RegistryError("factory symbol must be a non-empty string")
    factory = getattr(module, symbol, None)
    if factory is None:
        raise RegistryError(f"factory symbol {symbol!r} is not defined in {module.__name__!r}")
    if not callable(factory):
        raise RegistryError(f"factory symbol {symbol!r} in {module.__name__!r} is not callable")
    return factory


# --------------------------------------------------------------------------- #
# Static local import closure
# --------------------------------------------------------------------------- #


def _member_relative_path(module_name: str, *, is_package: bool) -> str:
    suffix = "/__init__.py" if is_package else ".py"
    return module_name.replace(".", "/") + suffix


def _module_source(module_name: str) -> tuple[str, bytes, bool]:
    """Return ``(package_relative_path, source_bytes, is_package)`` for a local module."""

    try:
        spec = find_spec(module_name)
    except (ImportError, ValueError, AttributeError) as error:
        raise RegistryError(f"closure member {module_name!r} cannot be resolved") from error
    if spec is None or spec.origin is None or spec.origin in {"built-in", "frozen", "namespace"}:
        raise RegistryError(f"closure member {module_name!r} has no importable source")
    origin = Path(spec.origin)
    if origin.suffix != ".py" or not origin.is_file():
        raise RegistryError(f"closure member {module_name!r} is not a Python source file")
    is_package = spec.submodule_search_locations is not None
    relative_path = _member_relative_path(module_name, is_package=is_package)
    return relative_path, origin.read_bytes(), is_package


def _absolute_import_targets(
    tree: ast.AST, *, module_name: str, is_package: bool
) -> set[str]:
    """Return the absolute module names statically imported by ``module_name``."""

    package = module_name if is_package else module_name.rpartition(".")[0]
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base_parts = package.split(".")
                if node.level > len(base_parts):
                    raise RegistryError(f"relative import in {module_name!r} escapes its package")
                base = ".".join(base_parts[: len(base_parts) - node.level + 1])
                root = f"{base}.{node.module}" if node.module else base
            elif node.module:
                root = node.module
            else:  # pragma: no cover - guarded by ast for level 0
                continue
            targets.add(root)
            for alias in node.names:
                if alias.name != "*":
                    targets.add(f"{root}.{alias.name}")
    return targets


def _reject_dynamic_imports(tree: ast.AST, module_name: str) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _DYNAMIC_IMPORT_NAMES:
            raise RegistryError(f"closure member {module_name!r} performs a dynamic import")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _DYNAMIC_IMPORT_MODULES:
                    raise RegistryError(
                        f"closure member {module_name!r} imports a dynamic import module"
                    )
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] in _DYNAMIC_IMPORT_MODULES
        ):
            raise RegistryError(
                f"closure member {module_name!r} imports a dynamic import module"
            )


def _is_local(name: str) -> bool:
    return name == _ROOT_PACKAGE or name.startswith(f"{_ROOT_PACKAGE}.")


def _has_prefix(name: str, prefixes: Iterable[str]) -> bool:
    return any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes)


def _module_exists(name: str) -> bool:
    try:
        return find_spec(name) is not None
    except (ImportError, ValueError, AttributeError):
        return False


@dataclass(frozen=True, slots=True)
class _ClosureResult:
    members: tuple[ContentMemberIdentity, ...]
    numeric_distribution_names: tuple[str, ...]


def _static_import_closure(factory_module: str) -> _ClosureResult:
    """Walk the transitive local-import closure rooted at ``factory_module``."""

    members: dict[str, ContentMemberIdentity] = {}
    numeric_names: set[str] = set()
    pending = [factory_module]
    seen: set[str] = set()

    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        relative_path, source, is_package = _module_source(current)
        try:
            tree = ast.parse(source, filename=relative_path)
        except SyntaxError as error:
            raise RegistryError(f"closure member {current!r} is not parseable") from error
        _reject_dynamic_imports(tree, current)
        members[current] = ContentMemberIdentity(
            package_relative_path=relative_path,
            content_sha256=hashlib.sha256(source).hexdigest(),
        )
        for target in _absolute_import_targets(tree, module_name=current, is_package=is_package):
            top_level = target.split(".")[0]
            if not _is_local(target):
                if top_level in _PERMITTED_NUMERIC_DISTRIBUTIONS:
                    numeric_names.add(_PERMITTED_NUMERIC_DISTRIBUTIONS[top_level])
                continue
            if _has_prefix(target, _FRAMEWORK_MODULE_PREFIXES):
                continue
            if _has_prefix(target, _CLOSURE_MEMBER_PREFIXES):
                # ``from pkg import name`` targets both the module and a symbol; only
                # keep the deepest name that actually resolves to a module.
                resolved = target if _module_exists(target) else target.rpartition(".")[0]
                if resolved and resolved not in seen and _module_exists(resolved):
                    pending.append(resolved)
                continue
            raise RegistryError(
                f"closure member {current!r} imports out-of-closure module {target!r}"
            )

    ordered_members = tuple(
        sorted(members.values(), key=lambda item: item.package_relative_path)
    )
    return _ClosureResult(ordered_members, tuple(sorted(numeric_names)))


# --------------------------------------------------------------------------- #
# Schema / content / runtime verification
# --------------------------------------------------------------------------- #


def _measurement_schema_sha256(measurement_schema_id: str) -> str:
    if measurement_schema_id not in _MEASUREMENT_SCHEMA_IDS:
        raise RegistryError(f"unknown measurement schema id {measurement_schema_id!r}")
    resource = files(_SCHEMA_RESOURCE_PACKAGE).joinpath(f"{measurement_schema_id}.schema.json")
    try:
        raw = resource.read_bytes()
    except (FileNotFoundError, ModuleNotFoundError, OSError) as error:
        raise RegistryError(
            f"measurement schema resource for {measurement_schema_id!r} is missing"
        ) from error
    return hashlib.sha256(raw).hexdigest()


def _content_member_bytes(member: ContentMemberIdentity) -> bytes:
    parts = PurePosixPath(member.package_relative_path).parts
    if not parts or parts[0] != _ROOT_PACKAGE:
        raise RegistryError(
            f"registry member {member.package_relative_path!r} is outside the package"
        )
    resource = files(_ROOT_PACKAGE)
    for part in parts[1:]:
        resource = resource.joinpath(part)
    try:
        return resource.read_bytes()
    except (FileNotFoundError, ModuleNotFoundError, OSError) as error:
        raise RegistryError(
            f"registry member {member.package_relative_path!r} is missing"
        ) from error


def _verify_declared_members(
    declared: tuple[ContentMemberIdentity, ...], *, label: str
) -> None:
    for member in declared:
        actual = hashlib.sha256(_content_member_bytes(member)).hexdigest()
        if actual != member.content_sha256:
            raise RegistryError(
                f"{label} {member.package_relative_path!r} bytes differ from the declared digest"
            )


def _verify_runtime_lock(
    python_runtime: object,
    numeric_runtimes: tuple[NumericRuntimeIdentity, ...],
    *,
    expected_distribution_names: tuple[str, ...],
) -> None:
    if python_runtime != python_runtime_identity():
        raise RegistryError("declared Python runtime does not match the active interpreter")
    declared_names = tuple(item.normalized_name for item in numeric_runtimes)
    if declared_names != tuple(sorted(expected_distribution_names)):
        raise RegistryError(
            "declared numeric runtimes do not match the plugin closure import allowlist"
        )
    for identity in numeric_runtimes:
        if identity != distribution_content_identity(identity.normalized_name):
            raise RegistryError(
                f"locked numeric runtime {identity.normalized_name!r} differs from the install"
            )


def _verify_artifact_schema_hashes(
    declared: Mapping[str, str],
    schemas: Iterable[tuple[str, Mapping[str, JsonValue]]],
) -> None:
    computed: dict[str, str] = {}
    for schema_id, descriptor in schemas:
        digest = schema_descriptor_sha256(schema_id, descriptor)
        existing = computed.setdefault(schema_id, digest)
        if existing != digest:
            raise RegistryError(f"schema id {schema_id!r} identifies two descriptors")
    if dict(declared) != computed:
        raise RegistryError("declared artifact/output schema hashes do not match the definition")


def _recompute_plugin_digest(entry: PluginRegistryEntry) -> str:
    return typed_json_sha256(
        _PLUGIN_DIGEST_TYPE, _DIGEST_VERSION, plugin_implementation_digest_payload(entry)
    )


def _recompute_preprocessing_digest(entry: PreprocessingRegistryEntry) -> str:
    return typed_json_sha256(
        _PREPROCESSING_DIGEST_TYPE,
        _DIGEST_VERSION,
        preprocessing_implementation_digest_payload(entry),
    )


# --------------------------------------------------------------------------- #
# Factory verification
# --------------------------------------------------------------------------- #


def _load_plugin_definition(
    entry: PluginRegistryEntry,
) -> tuple[AnchorPlugin, AnchorPluginDefinition]:
    module = _import_trusted_module(entry.factory_module, entry.allowed_package_namespace)
    if not entry.allowed_package_namespace.startswith(_PLUGIN_NAMESPACE):
        raise RegistryError("anchor plugin namespace must be under the plugins package")
    factory = _resolve_factory(module, entry.factory_symbol)
    candidate = factory()
    if not hasattr(candidate, "definition") or not hasattr(candidate, "compute"):
        raise RegistryError(f"factory {entry.factory_symbol!r} did not return an AnchorPlugin")
    plugin = cast(AnchorPlugin, candidate)
    definition = plugin.definition()
    if not isinstance(definition, AnchorPluginDefinition):
        raise RegistryError("plugin definition() must return an AnchorPluginDefinition")
    _require_plugin_definition_identity(definition, entry)
    return plugin, definition


def _require_plugin_definition_identity(
    definition: AnchorPluginDefinition, entry: PluginRegistryEntry
) -> None:
    if (
        definition.anchor_id != entry.anchor_id
        or definition.definition_version != entry.definition_version
        or definition.plugin_id != entry.plugin_id
        or definition.plugin_version != entry.plugin_version
        or definition.api_version != entry.api_version
        or definition.parameter_schema_id != entry.parameter_schema_id
        or definition.measurement_schema_id != entry.measurement_schema_id
    ):
        raise RegistryError("plugin definition identity does not match the registry entry")
    if plugin_definition_fingerprint(definition) != entry.definition_fingerprint:
        raise RegistryError("plugin definition fingerprint does not match the registry entry")


def _load_provider_definition(
    entry: PreprocessingRegistryEntry,
) -> tuple[PreprocessingProvider, PreprocessingProviderDefinition]:
    module = _import_trusted_module(entry.factory_module, entry.allowed_package_namespace)
    if not entry.allowed_package_namespace.startswith(_PREPROCESSING_NAMESPACE):
        raise RegistryError("preprocessing provider namespace must be under the primitives package")
    factory = _resolve_factory(module, entry.factory_symbol)
    candidate = factory()
    if not hasattr(candidate, "definition") or not hasattr(candidate, "compute"):
        raise RegistryError(
            f"factory {entry.factory_symbol!r} did not return a PreprocessingProvider"
        )
    provider = cast(PreprocessingProvider, candidate)
    definition = provider.definition()
    if not isinstance(definition, PreprocessingProviderDefinition):
        raise RegistryError("provider definition() must return a PreprocessingProviderDefinition")
    _require_provider_definition_identity(definition, entry)
    return provider, definition


def _require_provider_definition_identity(
    definition: PreprocessingProviderDefinition, entry: PreprocessingRegistryEntry
) -> None:
    if (
        definition.provider_id != entry.provider_id
        or definition.provider_version != entry.provider_version
        or definition.api_version != entry.api_version
        or definition.parameter_schema_id != entry.parameter_schema_id
        or definition.output_schema_id != entry.output_schema_id
        or definition.artifact_kind != entry.artifact_kind
        or definition.output_payload_kind != entry.output_payload_kind
    ):
        raise RegistryError("provider definition identity does not match the registry entry")
    if preprocessing_definition_fingerprint(definition) != entry.definition_fingerprint:
        raise RegistryError("provider definition fingerprint does not match the registry entry")


def _verify_parameter_schema(parameter_schema_id: str, declared: str) -> None:
    try:
        actual = parameter_schema_sha256(parameter_schema_id)
    except CatalogResourceError as error:
        raise RegistryError(f"parameter schema {parameter_schema_id!r} is not packaged") from error
    if actual != declared:
        raise RegistryError("declared parameter schema hash does not match the packaged bytes")


def verify_implementation_closure(entry: PluginRegistryEntry) -> None:
    """Prove one anchor plugin entry is bound to its exact immutable implementation."""

    if not isinstance(entry, PluginRegistryEntry):
        raise RegistryError("verify_implementation_closure requires a PluginRegistryEntry")
    _verify_parameter_schema(entry.parameter_schema_id, entry.parameter_schema_sha256)
    if _measurement_schema_sha256(entry.measurement_schema_id) != entry.measurement_schema_sha256:
        raise RegistryError("declared measurement schema hash does not match the packaged bytes")
    _plugin, definition = _load_plugin_definition(entry)
    _verify_artifact_schema_hashes(
        entry.artifact_schema_hashes,
        ((recipe.schema_id, recipe.schema_descriptor) for recipe in definition.artifact_recipes),
    )
    closure = _static_import_closure(entry.factory_module)
    if closure.members != entry.implementation_members:
        raise RegistryError("declared implementation members do not match the factory closure")
    _verify_declared_members(entry.resource_members, label="resource member")
    _verify_runtime_lock(
        entry.python_runtime,
        entry.numeric_runtimes,
        expected_distribution_names=closure.numeric_distribution_names,
    )
    if _recompute_plugin_digest(entry) != entry.implementation_digest:
        raise RegistryError("recomputed implementation digest does not match the registry entry")


def verify_preprocessing_closure(entry: PreprocessingRegistryEntry) -> None:
    """Prove one preprocessing provider entry is bound to its exact implementation."""

    if not isinstance(entry, PreprocessingRegistryEntry):
        raise RegistryError("verify_preprocessing_closure requires a PreprocessingRegistryEntry")
    _verify_parameter_schema(entry.parameter_schema_id, entry.parameter_schema_sha256)
    _provider, definition = _load_provider_definition(entry)
    _verify_artifact_schema_hashes(
        {entry.output_schema_id: entry.output_schema_sha256},
        ((definition.output_schema_id, definition.output_schema_descriptor),),
    )
    closure = _static_import_closure(entry.factory_module)
    if closure.members != entry.implementation_members:
        raise RegistryError("declared implementation members do not match the factory closure")
    _verify_declared_members(entry.resource_members, label="resource member")
    _verify_runtime_lock(
        entry.python_runtime,
        entry.numeric_runtimes,
        expected_distribution_names=closure.numeric_distribution_names,
    )
    if _recompute_preprocessing_digest(entry) != entry.implementation_digest:
        raise RegistryError("recomputed implementation digest does not match the registry entry")


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


class PluginRegistry:
    """Immutable trusted view over the packaged anchor/preprocessing registry."""

    __slots__ = ("_entries", "_preprocessors", "_plugin_factories", "_preprocessing_factories")

    def __init__(
        self,
        *,
        entries: Mapping[PluginKey, PluginRegistryEntry],
        preprocessors: Mapping[PreprocessorKey, PreprocessingRegistryEntry],
        plugin_factories: Mapping[PluginKey, Callable[[], AnchorPlugin]] | None,
        preprocessing_factories: Mapping[PreprocessorKey, Callable[[], PreprocessingProvider]]
        | None,
    ) -> None:
        self._entries = dict(entries)
        self._preprocessors = dict(preprocessors)
        self._plugin_factories = (
            None if plugin_factories is None else dict(plugin_factories)
        )
        self._preprocessing_factories = (
            None if preprocessing_factories is None else dict(preprocessing_factories)
        )

    @property
    def _trusted(self) -> bool:
        return self._plugin_factories is None

    # -- plugins ----------------------------------------------------------- #

    def capability(self, plugin_id: str, plugin_version: str) -> PluginCapability:
        key = (plugin_id, plugin_version)
        if not self._trusted:
            assert self._plugin_factories is not None
            status = (
                AnchorCapabilityStatus.AVAILABLE
                if key in self._plugin_factories
                else AnchorCapabilityStatus.NOT_IMPLEMENTED
            )
            return PluginCapability(status, None, ())
        entry = self._entries.get(key)
        if entry is None:
            status = (
                AnchorCapabilityStatus.PLUGIN_UNAVAILABLE
                if any(existing[0] == plugin_id for existing in self._entries)
                else AnchorCapabilityStatus.NOT_IMPLEMENTED
            )
            return PluginCapability(status, None, ())
        try:
            verify_implementation_closure(entry)
        except RegistryError as error:
            return PluginCapability(
                AnchorCapabilityStatus.INCOMPATIBLE,
                entry,
                (_diagnostic("anchor.plugin.incompatible", str(error)),),
            )
        return PluginCapability(AnchorCapabilityStatus.AVAILABLE, entry, ())

    def resolve(
        self, plugin_id: str, plugin_version: str, implementation_digest: str
    ) -> AnchorPlugin:
        key = (plugin_id, plugin_version)
        if not self._trusted:
            assert self._plugin_factories is not None
            factory = self._plugin_factories.get(key)
            if factory is None:
                raise RegistryResolutionError(
                    f"test plugin {key!r} is not registered for testing"
                )
            return factory()
        entry = self._entries.get(key)
        if entry is None:
            raise RegistryResolutionError(f"plugin {key!r} is not registered")
        if implementation_digest != entry.implementation_digest:
            raise RegistryResolutionError(
                "requested implementation digest does not match the registered plugin build"
            )
        plugin, _definition = _load_plugin_definition(entry)
        verify_implementation_closure(entry)
        return plugin

    # -- preprocessing providers ------------------------------------------ #

    def preprocessing_capability(
        self, provider_id: str, provider_version: str
    ) -> PreprocessingCapability:
        key = (provider_id, provider_version)
        if not self._trusted:
            assert self._preprocessing_factories is not None
            status: PreprocessingCapabilityStatus = (
                "available" if key in self._preprocessing_factories else "not_implemented"
            )
            return PreprocessingCapability(status, None, ())
        entry = self._preprocessors.get(key)
        if entry is None:
            status = (
                "provider_unavailable"
                if any(existing[0] == provider_id for existing in self._preprocessors)
                else "not_implemented"
            )
            return PreprocessingCapability(status, None, ())
        try:
            verify_preprocessing_closure(entry)
        except RegistryError as error:
            return PreprocessingCapability(
                "incompatible",
                entry,
                (_diagnostic("anchor.provider.incompatible", str(error)),),
            )
        return PreprocessingCapability("available", entry, ())

    def resolve_preprocessor(
        self, provider_id: str, provider_version: str, implementation_digest: str
    ) -> PreprocessingProvider:
        key = (provider_id, provider_version)
        if not self._trusted:
            assert self._preprocessing_factories is not None
            factory = self._preprocessing_factories.get(key)
            if factory is None:
                raise RegistryResolutionError(
                    f"test provider {key!r} is not registered for testing"
                )
            return factory()
        entry = self._preprocessors.get(key)
        if entry is None:
            raise RegistryResolutionError(f"provider {key!r} is not registered")
        if implementation_digest != entry.implementation_digest:
            raise RegistryResolutionError(
                "requested implementation digest does not match the registered provider build"
            )
        provider, _definition = _load_provider_definition(entry)
        verify_preprocessing_closure(entry)
        return provider

    # -- constructors ------------------------------------------------------ #

    @classmethod
    def from_factories_for_testing(
        cls,
        factories: Mapping[PluginKey, Callable[[], AnchorPlugin]],
        preprocessors: Mapping[PreprocessorKey, Callable[[], PreprocessingProvider]],
    ) -> PluginRegistry:
        return cls(
            entries={},
            preprocessors={},
            plugin_factories=dict(factories),
            preprocessing_factories=dict(preprocessors),
        )

    @classmethod
    def _from_model(cls, model: AnchorRuntimeRegistry) -> PluginRegistry:
        return cls(
            entries={(item.plugin_id, item.plugin_version): item for item in model.entries},
            preprocessors={
                (item.provider_id, item.provider_version): item for item in model.preprocessors
            },
            plugin_factories=None,
            preprocessing_factories=None,
        )


def _load_registry_model() -> AnchorRuntimeRegistry:
    resource = files(_REGISTRY_RESOURCE_PACKAGE).joinpath(_REGISTRY_RESOURCE_NAME)
    try:
        raw = resource.read_bytes()
    except (FileNotFoundError, ModuleNotFoundError, OSError) as error:
        raise RegistryError("packaged registry resource is missing") from error
    return AnchorRuntimeRegistry.model_validate_json(raw)


def load_packaged_registry() -> PluginRegistry:
    """Return the trusted registry backed by the packaged ``registry-v1.json``."""

    return PluginRegistry._from_model(_load_registry_model())


def packaged_registry_fingerprint() -> str:
    """Return the canonical fingerprint of the packaged registry model."""

    return runtime_registry_fingerprint(_load_registry_model())


# --------------------------------------------------------------------------- #
# Module CLI
# --------------------------------------------------------------------------- #


def _cli_error(message: str) -> NoReturn:
    raise RegistryError(message)


def _registry_resource_path() -> Path:
    return Path(str(files(_REGISTRY_RESOURCE_PACKAGE).joinpath(_REGISTRY_RESOURCE_NAME)))


def _read_registry_model(path: Path) -> AnchorRuntimeRegistry:
    try:
        raw = path.read_bytes()
    except (FileNotFoundError, OSError) as error:
        raise RegistryError("registry resource is missing") from error
    return AnchorRuntimeRegistry.model_validate_json(raw)


def _write_registry_model(path: Path, model: AnchorRuntimeRegistry) -> None:
    payload = json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    path.write_text(payload, encoding="utf-8", newline="\n")


def _with_computed_plugin_digest(entry: PluginRegistryEntry) -> PluginRegistryEntry:
    digest = _recompute_plugin_digest(entry)
    return entry.model_copy(update={"implementation_digest": digest})


def _with_computed_preprocessing_digest(
    entry: PreprocessingRegistryEntry,
) -> PreprocessingRegistryEntry:
    digest = _recompute_preprocessing_digest(entry)
    return entry.model_copy(update={"implementation_digest": digest})


def _build_plugin_entry(
    anchor_id: str, factory_module: str, factory_symbol: str
) -> PluginRegistryEntry:
    _require_trusted_namespace(factory_module, _PLUGIN_NAMESPACE)
    module = _import_trusted_module(factory_module, _PLUGIN_NAMESPACE)
    factory = _resolve_factory(module, factory_symbol)
    candidate = factory()
    if not hasattr(candidate, "definition") or not hasattr(candidate, "compute"):
        raise RegistryError(f"factory {factory_symbol!r} did not return an AnchorPlugin")
    definition = cast(AnchorPlugin, candidate).definition()
    if not isinstance(definition, AnchorPluginDefinition):
        raise RegistryError("plugin definition() must return an AnchorPluginDefinition")
    if definition.anchor_id != anchor_id:
        raise RegistryError(
            f"factory anchor id {definition.anchor_id!r} does not match {anchor_id!r}"
        )
    closure = _static_import_closure(factory_module)
    artifact_schema_hashes = {
        recipe.schema_id: schema_descriptor_sha256(recipe.schema_id, recipe.schema_descriptor)
        for recipe in definition.artifact_recipes
    }
    entry = PluginRegistryEntry(
        anchor_id=definition.anchor_id,
        definition_version=definition.definition_version,
        plugin_id=definition.plugin_id,
        plugin_version=definition.plugin_version,
        api_version=definition.api_version,
        factory_module=factory_module,
        factory_symbol=factory_symbol,
        allowed_package_namespace=_PLUGIN_NAMESPACE,
        definition_fingerprint=plugin_definition_fingerprint(definition),
        parameter_schema_id=definition.parameter_schema_id,
        parameter_schema_sha256=parameter_schema_sha256(definition.parameter_schema_id),
        measurement_schema_id=definition.measurement_schema_id,
        measurement_schema_sha256=_measurement_schema_sha256(definition.measurement_schema_id),
        artifact_schema_hashes=dict(sorted(artifact_schema_hashes.items())),
        implementation_members=closure.members,
        resource_members=(),
        python_runtime=python_runtime_identity(),
        numeric_runtimes=tuple(
            distribution_content_identity(name) for name in closure.numeric_distribution_names
        ),
        implementation_digest="0" * 64,
    )
    return _with_computed_plugin_digest(entry)


def _build_preprocessing_entry(
    provider_id: str, factory_module: str, factory_symbol: str
) -> PreprocessingRegistryEntry:
    _require_trusted_namespace(factory_module, _PREPROCESSING_NAMESPACE)
    module = _import_trusted_module(factory_module, _PREPROCESSING_NAMESPACE)
    factory = _resolve_factory(module, factory_symbol)
    candidate = factory()
    if not hasattr(candidate, "definition") or not hasattr(candidate, "compute"):
        raise RegistryError(f"factory {factory_symbol!r} did not return a PreprocessingProvider")
    definition = cast(PreprocessingProvider, candidate).definition()
    if not isinstance(definition, PreprocessingProviderDefinition):
        raise RegistryError("provider definition() must return a PreprocessingProviderDefinition")
    if definition.provider_id != provider_id:
        raise RegistryError(
            f"factory provider id {definition.provider_id!r} does not match {provider_id!r}"
        )
    closure = _static_import_closure(factory_module)
    entry = PreprocessingRegistryEntry(
        provider_id=definition.provider_id,
        provider_version=definition.provider_version,
        api_version=definition.api_version,
        factory_module=factory_module,
        factory_symbol=factory_symbol,
        allowed_package_namespace=_PREPROCESSING_NAMESPACE,
        definition_fingerprint=preprocessing_definition_fingerprint(definition),
        parameter_schema_id=definition.parameter_schema_id,
        parameter_schema_sha256=parameter_schema_sha256(definition.parameter_schema_id),
        output_schema_id=definition.output_schema_id,
        output_schema_sha256=schema_descriptor_sha256(
            definition.output_schema_id, definition.output_schema_descriptor
        ),
        artifact_kind=definition.artifact_kind,
        output_payload_kind=definition.output_payload_kind,
        implementation_members=closure.members,
        resource_members=(),
        python_runtime=python_runtime_identity(),
        numeric_runtimes=tuple(
            distribution_content_identity(name) for name in closure.numeric_distribution_names
        ),
        implementation_digest="0" * 64,
    )
    return _with_computed_preprocessing_digest(entry)


def _parse_options(arguments: list[str], allowed: frozenset[str]) -> dict[str, str]:
    options: dict[str, str] = {}
    index = 0
    while index < len(arguments):
        flag = arguments[index]
        if flag not in allowed:
            _cli_error(f"unsupported option: {flag}")
        if index + 1 >= len(arguments):
            _cli_error(f"option {flag} requires a value")
        if flag in options:
            _cli_error(f"duplicate option: {flag}")
        options[flag] = arguments[index + 1]
        index += 2
    return options


def _resolved_binding(
    options: Mapping[str, str],
    existing_module: str | None,
    existing_symbol: str | None,
) -> tuple[str, str]:
    module = options.get("--factory-module")
    symbol = options.get("--factory-symbol")
    if existing_module is None or existing_symbol is None:
        if module is None or symbol is None:
            _cli_error("an absent entry requires --factory-module and --factory-symbol")
        return module, symbol
    return module or existing_module, symbol or existing_symbol


def _verify_command() -> str:
    model = _load_registry_model()
    for entry in model.entries:
        verify_implementation_closure(entry)
    for provider_entry in model.preprocessors:
        verify_preprocessing_closure(provider_entry)
    return runtime_registry_fingerprint(model)


def _refresh_plugin_command(arguments: list[str]) -> str:
    options = _parse_options(
        arguments, frozenset({"--anchor", "--factory-module", "--factory-symbol"})
    )
    anchor_id = options.get("--anchor")
    if anchor_id is None:
        _cli_error("refresh requires --anchor")
    path = _registry_resource_path()
    model = _read_registry_model(path)
    existing = next((item for item in model.entries if item.anchor_id == anchor_id), None)
    module, symbol = _resolved_binding(
        options,
        existing.factory_module if existing else None,
        existing.factory_symbol if existing else None,
    )
    new_entry = _build_plugin_entry(anchor_id, module, symbol)
    verify_implementation_closure(new_entry)
    retained = tuple(item for item in model.entries if item.anchor_id != anchor_id)
    updated = AnchorRuntimeRegistry(
        entries=tuple(
            sorted(
                (*retained, new_entry),
                key=lambda item: (item.anchor_id, item.definition_version),
            )
        ),
        preprocessors=model.preprocessors,
    )
    _write_registry_model(path, updated)
    old_digest = existing.implementation_digest if existing else "absent"
    return (
        f"anchor={anchor_id} old_digest={old_digest} "
        f"new_digest={new_entry.implementation_digest}"
    )


def _refresh_preprocessor_command(arguments: list[str]) -> str:
    options = _parse_options(
        arguments, frozenset({"--provider", "--factory-module", "--factory-symbol"})
    )
    provider_id = options.get("--provider")
    if provider_id is None:
        _cli_error("refresh-preprocessor requires --provider")
    path = _registry_resource_path()
    model = _read_registry_model(path)
    existing = next(
        (item for item in model.preprocessors if item.provider_id == provider_id), None
    )
    module, symbol = _resolved_binding(
        options,
        existing.factory_module if existing else None,
        existing.factory_symbol if existing else None,
    )
    new_entry = _build_preprocessing_entry(provider_id, module, symbol)
    verify_preprocessing_closure(new_entry)
    retained = tuple(item for item in model.preprocessors if item.provider_id != provider_id)
    updated = AnchorRuntimeRegistry(
        entries=model.entries,
        preprocessors=tuple(
            sorted(
                (*retained, new_entry),
                key=lambda item: (item.provider_id, item.provider_version),
            )
        ),
    )
    _write_registry_model(path, updated)
    old_digest = existing.implementation_digest if existing else "absent"
    return (
        f"provider={provider_id} old_digest={old_digest} "
        f"new_digest={new_entry.implementation_digest}"
    )


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        if not arguments:
            _cli_error("usage: registry {verify|refresh|refresh-preprocessor} ...")
        command, rest = arguments[0], arguments[1:]
        if command == "verify":
            sys.stdout.write(f"registry_fingerprint={_verify_command()}\n")
            return 0
        if command == "refresh":
            sys.stdout.write(f"{_refresh_plugin_command(rest)}\n")
            return 0
        if command == "refresh-preprocessor":
            sys.stdout.write(f"{_refresh_preprocessor_command(rest)}\n")
            return 0
        _cli_error(f"unsupported registry command: {command}")
    except (RegistryError, CatalogResourceError, ValueError) as error:
        sys.stderr.write(f"registry error: {error}\n")
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised through the module CLI
    raise SystemExit(main())


__all__ = [
    "PluginCapability",
    "PluginKey",
    "PluginRegistry",
    "PreprocessingCapability",
    "PreprocessorKey",
    "RegistryError",
    "RegistryResolutionError",
    "load_packaged_registry",
    "main",
    "packaged_registry_fingerprint",
    "verify_implementation_closure",
    "verify_preprocessing_closure",
]
