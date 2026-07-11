from __future__ import annotations

import math

import pytest

from pilot_assessment.synthetic.prng import float32, triangular_noise, uniform53


def test_sha256_counter_prng_has_frozen_golden_values() -> None:
    assert uniform53(20260711, "EEG", "Fp1", 0, 0).hex() == "0x1.6af3eebf91787p-2"
    assert triangular_noise(20260711, "EEG", "Fp1", 0).hex() == ("-0x1.4d47ba0000000p-2")


def test_prng_is_deterministic_bounded_and_lane_specific() -> None:
    first = uniform53(7, "ECG", "lead_ii", 4, 0)
    assert first == uniform53(7, "ECG", "lead_ii", 4, 0)
    assert first != uniform53(7, "ECG", "lead_ii", 4, 1)
    assert 0.0 < first < 1.0
    assert -1.0 < triangular_noise(7, "ECG", "lead_ii", 4) < 1.0


def test_prng_rejects_out_of_contract_coordinates() -> None:
    invalid_calls = [
        (-1, "EEG", "Fp1", 0, 0),
        (2**63, "EEG", "Fp1", 0, 0),
        (1, "EEG", "Fp1", -1, 0),
        (1, "EEG", "Fp1", 0, -1),
    ]
    for arguments in invalid_calls:
        with pytest.raises(ValueError):
            uniform53(*arguments)


def test_prng_requires_ascii_nonempty_identifiers() -> None:
    with pytest.raises(ValueError):
        uniform53(1, "", "Fp1", 0, 0)
    with pytest.raises(ValueError):
        uniform53(1, "EEG", "额叶", 0, 0)


def test_float32_quantization_is_finite_and_exact() -> None:
    value = float32(math.pi)
    assert value.hex() == "0x1.921fb60000000p+1"
    with pytest.raises(ValueError):
        float32(math.inf)
