"""Deterministic finite-discrete factor algebra used by exact inference."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


class FactorError(ValueError):
    """Raised when factor construction or probability algebra is invalid."""


@dataclass(frozen=True, slots=True, init=False)
class Factor:
    """An immutable non-negative tensor with explicit variable/cardinality order."""

    variables: tuple[str, ...]
    cardinalities: tuple[int, ...]
    values: NDArray[np.float64]

    def __init__(
        self,
        variables: tuple[str, ...],
        cardinalities: tuple[int, ...],
        values: object,
    ) -> None:
        if len(variables) != len(cardinalities):
            raise FactorError("variables and cardinalities must have equal length")
        if len(variables) != len(set(variables)):
            raise FactorError("factor variables must be unique")
        if any(type(variable) is not str or not variable for variable in variables):
            raise FactorError("factor variables must be non-empty exact strings")
        if any(type(cardinality) is not int or cardinality < 1 for cardinality in cardinalities):
            raise FactorError("factor cardinalities must be positive strict integers")
        array = np.asarray(values, dtype=np.float64)
        expected_shape = cardinalities if cardinalities else ()
        if array.shape != expected_shape:
            raise FactorError(f"factor values have shape {array.shape}, expected {expected_shape}")
        if not bool(np.all(np.isfinite(array))):
            raise FactorError("factor values must be finite")
        if bool(np.any(array < 0.0)):
            raise FactorError("factor values must be non-negative")
        snapshot = array.copy()
        snapshot.setflags(write=False)
        object.__setattr__(self, "variables", variables)
        object.__setattr__(self, "cardinalities", cardinalities)
        object.__setattr__(self, "values", snapshot)

    def condition(self, variable: str, state_index: int) -> Factor:
        """Select one state and remove the conditioned variable from the scope."""

        try:
            axis = self.variables.index(variable)
        except ValueError as error:
            raise FactorError(f"variable {variable!r} is not in the factor") from error
        if type(state_index) is not int or not 0 <= state_index < self.cardinalities[axis]:
            raise FactorError("condition state index is outside the variable cardinality")
        return Factor(
            self.variables[:axis] + self.variables[axis + 1 :],
            self.cardinalities[:axis] + self.cardinalities[axis + 1 :],
            np.take(self.values, state_index, axis=axis),
        )

    def sum_out(self, variable: str) -> Factor:
        """Marginalize one variable while preserving the remaining scope order."""

        try:
            axis = self.variables.index(variable)
        except ValueError as error:
            raise FactorError(f"variable {variable!r} is not in the factor") from error
        return Factor(
            self.variables[:axis] + self.variables[axis + 1 :],
            self.cardinalities[:axis] + self.cardinalities[axis + 1 :],
            np.sum(self.values, axis=axis, dtype=np.float64),
        )

    def reorder(self, variables: tuple[str, ...]) -> Factor:
        """Return the identical tensor under an explicit permutation."""

        if len(variables) != len(set(variables)) or set(variables) != set(self.variables):
            raise FactorError("reorder variables must be an exact scope permutation")
        axes = tuple(self.variables.index(variable) for variable in variables)
        cardinalities = tuple(self.cardinalities[axis] for axis in axes)
        values = np.transpose(self.values, axes=axes) if axes else self.values
        return Factor(variables, cardinalities, values)

    def marginal(self, variables: tuple[str, ...]) -> Factor:
        """Sum every other variable and return the requested stable order."""

        if len(variables) != len(set(variables)) or not set(variables).issubset(self.variables):
            raise FactorError("marginal variables must be a unique subset of the factor scope")
        result = self
        for variable in tuple(item for item in result.variables if item not in variables):
            result = result.sum_out(variable)
        return result.reorder(variables)

    def normalize(self) -> Factor:
        """Normalize total mass, rejecting impossible evidence instead of inventing a prior."""

        total = float(np.sum(self.values, dtype=np.float64))
        if not math.isfinite(total) or total <= 0.0:
            raise FactorError("factor has zero probability mass and cannot be normalized")
        return Factor(self.variables, self.cardinalities, self.values / total)

    def multiply(self, other: Factor) -> Factor:
        return multiply_factors((self, other))


def multiply_factors(factors: Sequence[Factor]) -> Factor:
    """Multiply factors after deterministic alphabetical scope alignment."""

    if not factors:
        return Factor((), (), 1.0)
    cardinality_by_variable: dict[str, int] = {}
    for factor in factors:
        for variable, cardinality in zip(
            factor.variables,
            factor.cardinalities,
            strict=True,
        ):
            existing = cardinality_by_variable.setdefault(variable, cardinality)
            if existing != cardinality:
                raise FactorError(f"variable {variable!r} has inconsistent cardinalities")
    variables = tuple(sorted(cardinality_by_variable))
    cardinalities = tuple(cardinality_by_variable[variable] for variable in variables)
    result = np.ones(cardinalities if cardinalities else (), dtype=np.float64)
    variable_position = {variable: index for index, variable in enumerate(variables)}
    for factor in factors:
        positions = tuple(variable_position[variable] for variable in factor.variables)
        axis_order = tuple(sorted(range(len(positions)), key=positions.__getitem__))
        ordered_positions = tuple(positions[axis] for axis in axis_order)
        aligned = (
            np.transpose(factor.values, axes=axis_order) if len(axis_order) > 1 else factor.values
        )
        shape = [1] * len(variables)
        for position, axis in zip(ordered_positions, axis_order, strict=True):
            shape[position] = factor.cardinalities[axis]
        result = result * np.reshape(aligned, tuple(shape))
    return Factor(variables, cardinalities, result)


__all__ = ["Factor", "FactorError", "multiply_factors"]
