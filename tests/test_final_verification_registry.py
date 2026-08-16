from pathlib import Path

from spec2testbench.application.verification_tests import VerificationApplicabilityEngine
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.value_objects.circuit_type import CircuitType
from spec2testbench.domain.verification_tests import (
    VerificationApplicabilityStatus,
    VerificationTestId,
    get_verification_test_definition,
    get_verification_test_registry,
)


def test_final_verification_registry_has_exact_28_ids():
    registry = get_verification_test_registry()

    assert len(registry) == 28
    assert [definition.test_id for definition in registry] == list(VerificationTestId)


def test_phase_margin_definition_requires_loop_metadata():
    definition = get_verification_test_definition(VerificationTestId.T06_PHASE_GAIN_MARGIN)

    assert definition.required_port_roles == ("loop_break",)
    assert definition.analysis_types == ("ac",)


def test_specification_from_yaml_supports_final_schema_sections(tmp_path: Path):
    specification_path = tmp_path / "final_spec.yaml"
    specification_path.write_text(
        "\n".join(
            [
                "name: final_case",
                "circuit_type: opamp",
                "verification:",
                "  include_tests: [T05, T06]",
                "  exclude_tests: [T28]",
                "  auto_select: false",
                "ports:",
                "  input: [vin]",
                "  output: [vout]",
                "  loop_break: [loop_break_node]",
                "  supply_positive: [vdd]",
                "operating_conditions:",
                "  nominal_temperature: 27",
                "  nominal_supply: 1.8",
                "  process_corner: tt",
                "performance_targets:",
                "  dc_gain_db:",
                "    min: 60",
                "    unit: dB",
                "test_requirements:",
                "  T06:",
                "    min_phase_margin_deg: 60",
                "pvt_config:",
                "  corners: [tt, ff]",
                "  temperature_range: extended",
                "  supply_variation: 0.1",
            ]
        ),
        encoding="utf-8",
    )

    specification = Specification.from_yaml(specification_path)

    assert specification.verification.include_tests == ["T05", "T06"]
    assert specification.verification.exclude_tests == ["T28"]
    assert specification.verification.auto_select is False
    assert specification.port_nodes("loop_break") == ["loop_break_node"]
    assert specification.input_nodes == ["vin"]
    assert specification.output_nodes == ["vout"]
    assert specification.operating_conditions.nominal_supply == 1.8
    assert specification.operating_conditions.process_corner == "tt"
    assert "T06" in specification.test_requirements


def test_applicability_engine_marks_explicit_phase_margin_as_required():
    specification = Specification.from_dict(
        {
            "name": "pm_case",
            "circuit_type": CircuitType.OPERATIONAL_AMPLIFIER.value,
            "verification": {"include_tests": ["T06"], "auto_select": False},
            "ports": {
                "input": ["vin"],
                "output": ["vout"],
                "loop_break": ["lb"],
                "supply_positive": ["vdd"],
            },
            "performance_targets": {"phase_margin": {"min": 60, "unit": "deg"}},
        }
    )

    evaluation = VerificationApplicabilityEngine().evaluate(specification, VerificationTestId.T06_PHASE_GAIN_MARGIN)

    assert evaluation.status == VerificationApplicabilityStatus.REQUIRED


def test_applicability_engine_requires_multiple_process_corners_for_t26():
    specification = Specification.from_dict(
        {
            "name": "pvt_case",
            "circuit_type": CircuitType.AMPLIFIER.value,
            "ports": {"input": ["vin"], "output": ["vout"], "supply_positive": ["vdd"]},
            "process_corners": ["tt"],
            "verification": {"include_tests": ["T26"]},
        }
    )

    evaluation = VerificationApplicabilityEngine().evaluate(specification, VerificationTestId.T26_PROCESS_CORNERS)

    assert evaluation.status == VerificationApplicabilityStatus.UNSUPPORTED_CONFIGURATION
    assert evaluation.reasons == ("multiple_process_corners_required",)
