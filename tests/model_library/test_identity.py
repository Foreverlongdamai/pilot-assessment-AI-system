from __future__ import annotations

import pytest

from pilot_assessment.model_library.identity import jcs_bytes, typed_content_sha256

SAFE_INTEGER = 9_007_199_254_740_991


def test_jcs_bytes_are_deterministic_for_mapping_order_and_tuple_projection() -> None:
    left = {"b": 1, "a": "é", "values": (True, None, -0.0)}
    right = {"values": [True, None, 0.0], "a": "é", "b": 1}

    assert jcs_bytes(left) == b'{"a":"\xc3\xa9","b":1,"values":[true,null,0]}'
    assert jcs_bytes(right) == jcs_bytes(left)


@pytest.mark.parametrize(
    "value",
    (
        SAFE_INTEGER + 1,
        -SAFE_INTEGER - 1,
        float("nan"),
        float("inf"),
        b"bytes",
        {1: "non-string-key"},
        "\ud800",
    ),
)
def test_jcs_bytes_reject_values_outside_the_canonical_json_domain(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        jcs_bytes(value)


def test_typed_content_hash_uses_stable_type_and_schema_separation() -> None:
    payload = {"b": 1, "a": "é", "negative_zero": -0.0}

    assert typed_content_sha256("example-type", "0.1.0", payload) == (
        "51b15951bdb784bd8fbbda955fcd38930c35f6e6a6dcb37fda8353ef750bd7f9"
    )
    assert typed_content_sha256("other-type", "0.1.0", payload) != typed_content_sha256(
        "example-type", "0.1.0", payload
    )
    assert typed_content_sha256("example-type", "0.2.0", payload) != typed_content_sha256(
        "example-type", "0.1.0", payload
    )


@pytest.mark.parametrize(
    ("type_id", "schema_version"),
    (
        ("", "0.1.0"),
        ("example", ""),
        ("é", "0.1.0"),
        ("example", "版本"),
        ("type\0id", "0.1.0"),
        ("example", "0.1\0.0"),
    ),
)
def test_typed_content_hash_rejects_noncanonical_identity_fields(
    type_id: str, schema_version: str
) -> None:
    with pytest.raises(ValueError):
        typed_content_sha256(type_id, schema_version, {})
