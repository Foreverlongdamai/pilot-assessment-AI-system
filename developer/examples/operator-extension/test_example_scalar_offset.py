"""Minimal stdlib test that can run with the product's private Python."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from example_scalar_offset import register_example_scalar_offset  # noqa: E402

from pilot_assessment.evidence.operators import OperatorExecutionContext  # noqa: E402
from pilot_assessment.evidence.registry import OperatorRegistry  # noqa: E402


class ExampleScalarOffsetTests(unittest.TestCase):
    def test_registration_schema_and_execution(self) -> None:
        registry = OperatorRegistry()
        register_example_scalar_offset(registry)
        definition = registry.definition("extension.example.scalar-offset", "0.1.0")
        implementation = registry.implementation("extension.example.scalar-offset", "0.1.0")

        result = implementation.execute(
            {"value": 2.0},
            {"offset": 0.75},
            OperatorExecutionContext(
                recipe_id="recipe.example",
                recipe_version=1,
                node_id="offset",
                binding_values={},
            ),
        )

        self.assertEqual(definition.parameter_schema["required"], ["offset"])
        self.assertEqual(result, {"value": 2.75})


if __name__ == "__main__":
    unittest.main()
