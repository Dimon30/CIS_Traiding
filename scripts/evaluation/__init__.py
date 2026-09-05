"""Reusable evaluation protocol components for CIS Trading experiments."""

from .contracts import (
    ARTIFACT_SCHEMA_VERSION,
    ELIGIBILITY_VERSION,
    EVALUATION_PROTOCOL_VERSION,
    TARGET_CONTRACT_VERSION,
    EligibilitySpec,
    TemporalFoldSpec,
    TemporalRole,
)

__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "ELIGIBILITY_VERSION",
    "EVALUATION_PROTOCOL_VERSION",
    "TARGET_CONTRACT_VERSION",
    "EligibilitySpec",
    "TemporalFoldSpec",
    "TemporalRole",
]
