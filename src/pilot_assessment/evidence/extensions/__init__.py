"""Ordinary-source registration point for expert-developed evidence operators.

This module is intentionally explicit.  A developer adds a normal Python module next to this
file, imports its registration function below, and calls that function from
``register_extension_operators``.  Restarting the desktop application rebuilds the same trusted
operator registry from the edited source tree.  There is no plugin package, dynamic download, or
project-specific override layer.
"""

from pilot_assessment.evidence.registry import OperatorRegistry


def register_extension_operators(registry: OperatorRegistry) -> None:
    """Register locally developed operators after packaged built-ins.

    Example after copying the template from ``developer/examples/operator-extension``::

        from .example_scalar_offset import register_example_scalar_offset
        register_example_scalar_offset(registry)

    Keep each operator ID and implementation version unique.  Duplicate identities fail at
    startup with an explicit ``OperatorRegistryError`` instead of silently replacing code.
    """

    del registry  # The clean distribution intentionally starts with no local extensions.


__all__ = ["register_extension_operators"]
