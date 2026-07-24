from dataclasses import dataclass, field

from ...domain.entities.specification import Specification
from ...domain.verification_tests import (
    VerificationApplicabilityStatus,
    VerificationTestDefinition,
    VerificationTestId,
    get_verification_test_definition,
    get_verification_test_registry,
)


@dataclass(frozen=True)
class ApplicabilityEvaluation:
    test_id: VerificationTestId
    status: VerificationApplicabilityStatus
    reasons: tuple[str, ...] = ()
    missing_port_roles: tuple[str, ...] = ()
    missing_spec_fields: tuple[str, ...] = ()


class VerificationApplicabilityEngine:
    def evaluate_all(self, specification: Specification) -> tuple[ApplicabilityEvaluation, ...]:
        return tuple(self.evaluate(specification, definition.test_id) for definition in get_verification_test_registry())

    def evaluate(self, specification: Specification, test_id: VerificationTestId) -> ApplicabilityEvaluation:
        definition = get_verification_test_definition(test_id)
        normalized_includes = self._normalize_requested_tests(specification.verification.include_tests)
        normalized_excludes = self._normalize_requested_tests(specification.verification.exclude_tests)

        if test_id in normalized_excludes:
            return ApplicabilityEvaluation(
                test_id=test_id,
                status=VerificationApplicabilityStatus.NOT_APPLICABLE,
                reasons=("explicitly_excluded",),
            )

        if not self._circuit_type_is_applicable(specification, definition):
            return ApplicabilityEvaluation(
                test_id=test_id,
                status=VerificationApplicabilityStatus.NOT_APPLICABLE,
                reasons=("circuit_type_not_applicable",),
            )

        missing_port_roles = tuple(
            role for role in definition.required_port_roles if not specification.port_nodes(role)
        )
        if missing_port_roles:
            return ApplicabilityEvaluation(
                test_id=test_id,
                status=VerificationApplicabilityStatus.MISSING_REQUIRED_METADATA,
                reasons=("missing_required_ports",),
                missing_port_roles=missing_port_roles,
            )

        missing_spec_fields = tuple(
            field_name for field_name in definition.required_spec_fields if not self._spec_field_present(specification, field_name)
        )
        if missing_spec_fields:
            return ApplicabilityEvaluation(
                test_id=test_id,
                status=VerificationApplicabilityStatus.MISSING_REQUIRED_METADATA,
                reasons=("missing_required_spec_fields",),
                missing_spec_fields=missing_spec_fields,
            )

        unsupported_reasons = self._unsupported_configuration_reasons(specification, definition)
        if unsupported_reasons:
            return ApplicabilityEvaluation(
                test_id=test_id,
                status=VerificationApplicabilityStatus.UNSUPPORTED_CONFIGURATION,
                reasons=tuple(unsupported_reasons),
            )

        if test_id in normalized_includes or self._has_explicit_test_requirement(specification, test_id):
            status = VerificationApplicabilityStatus.REQUIRED
            reasons = ("explicit_requirement",)
        elif specification.verification.auto_select:
            status = VerificationApplicabilityStatus.OPTIONAL
            reasons = ("auto_select_candidate",)
        else:
            status = VerificationApplicabilityStatus.NOT_APPLICABLE
            reasons = ("auto_select_disabled",)

        return ApplicabilityEvaluation(
            test_id=test_id,
            status=status,
            reasons=reasons,
        )

    @staticmethod
    def _normalize_requested_tests(requested_tests: list[str]) -> set[VerificationTestId]:
        normalized: set[VerificationTestId] = set()
        for raw_value in requested_tests:
            token = str(raw_value).strip().upper()
            if not token:
                continue
            for candidate in VerificationTestId:
                if token in {candidate.name, candidate.value, candidate.name.split("_", 1)[0]}:
                    normalized.add(candidate)
                    break
        return normalized

    @staticmethod
    def _circuit_type_is_applicable(specification: Specification, definition: VerificationTestDefinition) -> bool:
        return specification.circuit_type.value in definition.applicable_circuit_types

    @staticmethod
    def _has_explicit_test_requirement(specification: Specification, test_id: VerificationTestId) -> bool:
        return test_id.value in specification.test_requirements or test_id.name in specification.test_requirements

    @staticmethod
    def _spec_field_present(specification: Specification, field_name: str) -> bool:
        if field_name == "process_corners":
            return len(specification.process_corners) > 0
        if field_name == "temperature_range":
            return specification.temperature_range is not None
        if field_name == "supply_variation":
            return specification.supply_variation is not None
        if field_name.startswith("test_requirements."):
            _, _, suffix = field_name.partition(".")
            return suffix in specification.test_requirements
        if field_name == "operating_conditions.process_corner":
            return bool(specification.operating_conditions.process_corner)
        if field_name == "operating_conditions.nominal_temperature":
            return specification.operating_conditions.nominal_temperature is not None
        if field_name == "operating_conditions.nominal_supply":
            return specification.operating_conditions.nominal_supply is not None
        return False

    @staticmethod
    def _unsupported_configuration_reasons(
        specification: Specification,
        definition: VerificationTestDefinition,
    ) -> list[str]:
        reasons: list[str] = []
        if definition.test_id == VerificationTestId.T06_PHASE_GAIN_MARGIN:
            loop_break = specification.port_nodes("loop_break")
            loop_injection = specification.port_nodes("loop_injection")
            if not loop_break and not loop_injection:
                reasons.append("loop_break_or_injection_not_declared")
        if definition.test_id == VerificationTestId.T21_MIXER_CONVERSION_SPURS:
            if len(specification.port_nodes("reference")) < 1:
                reasons.append("lo_reference_not_declared")
        if definition.test_id == VerificationTestId.T26_PROCESS_CORNERS and len(specification.process_corners) < 2:
            reasons.append("multiple_process_corners_required")
        if definition.test_id == VerificationTestId.T28_SUPPLY_VARIATION and float(specification.supply_variation or 0.0) <= 0.0:
            reasons.append("positive_supply_variation_required")
        return reasons
