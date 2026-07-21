"""Software-copy-scoped system model store contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, StringConstraints

from pilot_assessment.contracts.common import Sha256Digest, StableId, StrictContractModel

ProductVersion = Annotated[str, StringConstraints(min_length=1, max_length=64)]


class SystemDescriptor(StrictContractModel):
    """Portable identity of one software copy's mutable system model library."""

    contract_id: Literal["system-descriptor"] = "system-descriptor"
    contract_version: Literal["0.1.0"] = "0.1.0"
    model_library_id: StableId
    format_version: Literal["0.1.0"]
    created_from_product_version: ProductVersion
    starter_seed_id: StableId
    starter_seed_hash: Sha256Digest
    created_at: AwareDatetime


__all__ = ["ProductVersion", "SystemDescriptor"]
