from pathlib import Path

from spec2testbench.application.services.llm_metric_registry import get_metric_definition
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.value_objects.metric_semantics import (
    ACQuantityType,
    LEGACY_ABSOLUTE_OUTPUT_V1,
    TRANSFER_GAIN_V2,
    legacy_metric_interpretation,
    scientific_eligibility_under_current_semantics,
)
from spec2testbench.infrastructure.testbench import TestBenchGenerator as FrameworkTestBenchGenerator


def test_metric_registry_marks_dc_gain_as_transfer_ratio():
    definition = get_metric_definition("dc_gain_db")

    assert definition is not None
    assert definition.definition_version == TRANSFER_GAIN_V2
    assert definition.quantity_type == ACQuantityType.TRANSFER_GAIN_DB
    assert definition.measurement_expression_id == "AC_TRANSFER_GAIN_DB"


def test_absolute_output_dbv_is_not_transfer_gain():
    transfer = get_metric_definition("dc_gain_db")
    absolute = get_metric_definition("absolute_output_dbv")

    assert transfer is not None
    assert absolute is not None
    assert transfer.quantity_type == ACQuantityType.TRANSFER_GAIN_DB
    assert absolute.quantity_type == ACQuantityType.ABSOLUTE_OUTPUT_DBV
    assert transfer.definition_version != absolute.definition_version


def test_legacy_result_is_not_current_scientific_evidence():
    assert scientific_eligibility_under_current_semantics("dc_gain_db", LEGACY_ABSOLUTE_OUTPUT_V1) is False
    assert legacy_metric_interpretation("dc_gain_db", LEGACY_ABSOLUTE_OUTPUT_V1) == ACQuantityType.ABSOLUTE_OUTPUT_DBV.value


def test_gain_definition_version_is_persisted():
    specification = Specification.from_dict(
        {
            "name": "gain_case",
            "circuit_type": "amplifier",
            "performance_targets": {"dc_gain_db": {"min": 0.0, "unit": "dB"}},
            "input_conditions": {"vdd": 5.0, "vss": 0.0, "vcm": 2.5, "input_nodes": "Vin", "output_nodes": "Vout"},
            "test_categories": ["ac"],
        }
    )

    testbench = FrameworkTestBenchGenerator(use_llm=False).generate(specification)
    request = next(item for item in testbench.metadata["measurement_requests"] if item["name"] == "dc_gain_db")

    assert request["metric_definition_version"] == TRANSFER_GAIN_V2
    assert request["quantity_type"] == ACQuantityType.TRANSFER_GAIN_DB.value
    assert request["measurement_expression_id"] == "AC_TRANSFER_GAIN_DB"


def test_input_ac_magnitude_is_persisted():
    specification = Specification.from_dict(
        {
            "name": "gain_case",
            "circuit_type": "amplifier",
            "performance_targets": {"dc_gain_db": {"min": 0.0, "unit": "dB"}},
            "input_conditions": {"vdd": 5.0, "vss": 0.0, "vcm": 2.5, "input_nodes": "Vin", "output_nodes": "Vout"},
            "test_categories": ["ac"],
        }
    )

    testbench = FrameworkTestBenchGenerator(use_llm=False).generate(specification)
    request = next(item for item in testbench.metadata["measurement_requests"] if item["name"] == "dc_gain_db")

    assert request["input_ac_magnitude"] == 1.0
    assert request["reference_frequency_hz"] == 1.0


def test_multimode_plan_preserves_ac_magnitude_for_transient_and_ac(tmp_path: Path):
    specification = Specification.from_dict(
        {
            "name": "gain_transient_case",
            "circuit_type": "amplifier",
            "performance_targets": {
                "dc_gain_db": {"min": 0.0, "unit": "dB"},
                "slew_rate": {"min": 1.0, "unit": "V/s"},
            },
            "input_conditions": {"vdd": 5.0, "vss": 0.0, "vcm": 2.5, "input_nodes": "Vin", "output_nodes": "Vout"},
            "test_categories": ["ac", "transient"],
        }
    )
    netlist_path = tmp_path / "demo.cir"
    netlist_path.write_text(
        "\n".join(
            [
                "Vdd Vdd 0 5",
                "Vin Vin 0 DC 1.0 AC 1n",
                "Rload Vout Vdd 10k",
                "M1 Vout Vin 0 0 nmos_model W=5e-05 L=1e-06",
                ".MODEL nmos_model NMOS (LEVEL=1 KP=0.0001 VTO=0.5)",
                ".END",
            ]
        ),
        encoding="utf-8",
    )

    testbench = FrameworkTestBenchGenerator(use_llm=False).generate(specification, netlist_path=netlist_path)
    source_action = testbench.metadata["llm_guided_plan"]["source_actions"][0]

    assert source_action["new_source"]["type"] == "pulse"
    assert source_action["new_source"]["ac_magnitude"] == 1.0
