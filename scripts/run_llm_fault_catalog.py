from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spec2testbench.application.services.llm_testbench_plan_validator import LLMTestbenchPlanValidator
from spec2testbench.domain.entities.specification import Specification


DEFAULT_SPEC = ROOT / "benchmark/analogcoder_pro/specs/p10_lowpass.yaml"
DEFAULT_NETLIST = ROOT / "benchmark/analogcoder_pro/p10_lowpass.cir"


def base_plan(case_id: str) -> dict:
    return {
        "case_id": case_id,
        "analysis_type": "AC",
        "provider_mode": "FAULT_INJECTION",
        "scientific_llm_evidence": False,
        "stimuli": [
            {"source_name": "vin", "target_node": "Vin", "stimulus_type": "AC", "parameters": {"magnitude": 1.0, "dc_value": 2.5}}
        ],
        "observed_nodes": ["Vout"],
        "measurements": [
            {
                "metric_name": "cutoff_frequency_hz",
                "analysis_type": "AC",
                "input_node": "Vin",
                "output_node": "Vout",
                "expected_unit": "Hz",
                "backend_preference": "NGSPICE_WRDATA",
                "measurement_parameters": {},
            }
        ],
        "simulation_parameters": {"frequency_start_hz": 1.0, "frequency_stop_hz": 1e9, "points_per_decade": 20},
        "concise_rationale": "Measure the AC cutoff from simulator vectors.",
    }


def fault_cases(plan: dict) -> list[tuple[str, dict, set[str]]]:
    cases = []

    p = deepcopy(plan); p["measurements"][0]["output_node"] = "Vghost"
    cases.append(("invented_node", p, {"UNKNOWN_NODE"}))

    p = deepcopy(plan); p["measurements"][0]["output_node"] = "Vin"
    cases.append(("wrong_output_role", p, {"ROLE_MISMATCH"}))

    p = deepcopy(plan); p["stimuli"][0]["target_node"] = "Vout"
    cases.append(("wrong_stimulus_role", p, {"ROLE_MISMATCH"}))

    p = deepcopy(plan); p["measurements"][0]["analysis_type"] = "TRAN"
    cases.append(("wrong_analysis", p, {"ANALYSIS_MISMATCH"}))

    p = deepcopy(plan); p["measurements"][0]["expected_unit"] = "V"
    cases.append(("wrong_unit", p, {"UNIT_MISMATCH"}))

    p = deepcopy(plan); p["measurements"][0]["backend_preference"] = "NGSPICE_MEASURE"
    cases.append(("invalid_measure_backend", p, {"UNSUPPORTED_BACKEND"}))

    p = deepcopy(plan); p["concise_rationale"] = "This circuit will PASS."
    cases.append(("verdict_leakage", p, {"VERDICT_LEAKAGE"}))

    p = deepcopy(plan); p["measurements"] = []
    cases.append(("missing_measurement", p, {"SCHEMA_ERROR"}))

    p = deepcopy(plan); p["threshold_override"] = {"cutoff_frequency_hz": {"min": 0.0}}
    cases.append(("threshold_override_attempt", p, {"SCHEMA_ERROR"}))

    p = deepcopy(plan); p["analysis_type"] = "DC"; p["measurements"][0]["analysis_type"] = "DC"; p["simulation_parameters"] = {"dc_source": "VDOESNOTEXIST", "dc_start": 0, "dc_stop": 5, "dc_step": 0.1}
    cases.append(("nonexistent_source", p, {"INVALID_STIMULUS", "ANALYSIS_MISMATCH"}))

    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject controlled LLM-like plan faults and verify deterministic rejection")
    parser.add_argument("--spec", default=str(DEFAULT_SPEC))
    parser.add_argument("--netlist", default=str(DEFAULT_NETLIST))
    parser.add_argument("--output", default=str(ROOT / "results/hybrid_fault_catalog.json"))
    args = parser.parse_args()

    spec_path = Path(args.spec)
    netlist_path = Path(args.netlist)
    specification = Specification.from_yaml(spec_path)
    specification.case_id = specification.case_id or spec_path.stem
    plan = base_plan(specification.case_id)
    validator = LLMTestbenchPlanValidator()

    rows = []
    for fault_name, payload, expected_statuses in fault_cases(plan):
        validation = validator.parse_and_validate(
            json.dumps(payload),
            specification=specification,
            netlist_path=netlist_path,
            expected_case_id=specification.case_id,
        )
        observed = {validation.status.value, *[issue.status.value for issue in validation.issues]}
        rows.append(
            {
                "fault": fault_name,
                "expected_any_status": sorted(expected_statuses),
                "primary_status": validation.status.value,
                "all_statuses": sorted(observed),
                "detected": bool(observed & expected_statuses),
                "issues": validation.to_dict()["issues"],
            }
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "campaign_type": "CONTROLLED_LLM_LIKE_FAULT_INJECTION",
        "scientific_llm_evidence": False,
        "note": "This validates guard coverage; it is not a measurement of spontaneous live-model hallucination rate.",
        "case_count": len(rows),
        "detected_count": sum(row["detected"] for row in rows),
        "detection_rate": sum(row["detected"] for row in rows) / len(rows),
        "rows": rows,
    }
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
