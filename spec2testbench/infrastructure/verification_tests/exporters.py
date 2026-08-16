import csv
from pathlib import Path

from ...application.verification_tests import ApplicabilityEvaluation
from ...domain.verification_tests import VerificationTestDefinition, get_verification_test_registry


def write_verification_registry_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "test_id",
        "name",
        "category",
        "analysis_types",
        "applicable_circuit_types",
        "required_port_roles",
        "required_spec_fields",
        "metric_definitions",
        "checker_definitions",
        "version",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for definition in get_verification_test_registry():
            writer.writerow(_definition_to_row(definition))
    return path


def write_applicability_matrix_csv(path: Path, circuit_id: str, evaluations: tuple[ApplicabilityEvaluation, ...]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "circuit_id",
        "test_id",
        "status",
        "reasons",
        "missing_port_roles",
        "missing_spec_fields",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for evaluation in evaluations:
            writer.writerow(
                {
                    "circuit_id": circuit_id,
                    "test_id": evaluation.test_id.name,
                    "status": evaluation.status.value,
                    "reasons": ";".join(evaluation.reasons),
                    "missing_port_roles": ";".join(evaluation.missing_port_roles),
                    "missing_spec_fields": ";".join(evaluation.missing_spec_fields),
                }
            )
    return path


def _definition_to_row(definition: VerificationTestDefinition) -> dict[str, str]:
    return {
        "test_id": definition.test_id.name,
        "name": definition.name,
        "category": definition.category,
        "analysis_types": ";".join(definition.analysis_types),
        "applicable_circuit_types": ";".join(definition.applicable_circuit_types),
        "required_port_roles": ";".join(definition.required_port_roles),
        "required_spec_fields": ";".join(definition.required_spec_fields),
        "metric_definitions": ";".join(definition.metric_definitions),
        "checker_definitions": ";".join(definition.checker_definitions),
        "version": definition.version,
    }
