from __future__ import annotations

from enum import Enum


class ACQuantityType(str, Enum):
    TRANSFER_GAIN_DB = "TRANSFER_GAIN_DB"
    ABSOLUTE_OUTPUT_DBV = "ABSOLUTE_OUTPUT_DBV"
    ABSOLUTE_INPUT_DBV = "ABSOLUTE_INPUT_DBV"
    TRANSFER_MAGNITUDE_LINEAR = "TRANSFER_MAGNITUDE_LINEAR"
    TRANSFER_PHASE_DEG = "TRANSFER_PHASE_DEG"


TRANSFER_GAIN_V2 = "transfer_gain_v2"
LEGACY_ABSOLUTE_OUTPUT_V1 = "legacy_absolute_output_v1"


def scientific_eligibility_under_current_semantics(
    metric_name: str,
    metric_definition_version: str | None,
) -> bool:
    metric_lower = metric_name.strip().lower()
    if metric_lower in {"dc_gain", "dc_gain_db", "gain_db"} and metric_definition_version == LEGACY_ABSOLUTE_OUTPUT_V1:
        return False
    return True


def legacy_metric_interpretation(
    metric_name: str,
    metric_definition_version: str | None,
) -> str | None:
    metric_lower = metric_name.strip().lower()
    if metric_lower in {"dc_gain", "dc_gain_db", "gain_db"} and metric_definition_version == LEGACY_ABSOLUTE_OUTPUT_V1:
        return ACQuantityType.ABSOLUTE_OUTPUT_DBV.value
    return None
