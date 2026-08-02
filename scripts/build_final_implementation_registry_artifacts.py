from __future__ import annotations

import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spec2testbench.application.services.benchmark_deck_normalizer import BenchmarkDeckNormalizer
from spec2testbench.application.verification_tests import VerificationApplicabilityEngine
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.value_objects.circuit_type import CircuitType
from spec2testbench.infrastructure.verification_tests import write_verification_registry_csv

BENCHMARK_DIR = ROOT / "benchmark" / "analogcoder_pro"
MANIFEST_PATH = BENCHMARK_DIR / "manifest.csv"
OUTPUT_DIR = ROOT / "results" / "final_implementation"
REGISTRY_CSV = OUTPUT_DIR / "verification_test_registry.csv"
APPLICABILITY_CSV = OUTPUT_DIR / "circuit_test_applicability_matrix.csv"


TYPE_HINTS = {
    "amplifier": CircuitType.AMPLIFIER,
    "opamp": CircuitType.OPERATIONAL_AMPLIFIER,
    "comparator": CircuitType.COMPARATOR,
    "currentmirror": CircuitType.CURRENT_MIRROR,
    "current mirror": CircuitType.CURRENT_MIRROR,
    "mixer": CircuitType.MIXER,
    "oscillator": CircuitType.OSCILLATOR,
    "integrator": CircuitType.INTEGRATOR,
    "differentiator": CircuitType.DIFFERENTIATOR,
    "schmitt": CircuitType.SCHMITT_TRIGGER,
    "lowpass": CircuitType.LOW_PASS_FILTER,
    "highpass": CircuitType.HIGH_PASS_FILTER,
    "bandpass": CircuitType.BAND_PASS_FILTER,
    "bandstop": CircuitType.NOTCH_FILTER,
    "notch": CircuitType.NOTCH_FILTER,
    "adder": CircuitType.COMPOSITE,
    "subtractor": CircuitType.COMPOSITE,
}


def infer_circuit_type(case_id: str, metadata: dict) -> CircuitType:
    text = " ".join(
        str(metadata.get(key, ""))
        for key in ("declared_type", "declared_topology", "description", "inferred_topology")
    ).lower()
    case_hint = case_id.lower()
    for token, circuit_type in TYPE_HINTS.items():
        if token in text or token in case_hint:
            return circuit_type
    return CircuitType.COMPOSITE


def manifest_rows() -> list[dict[str, str]]:
    with MANIFEST_PATH.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build_specification(case_id: str, metadata: dict, harness: dict) -> Specification:
    circuit_type = infer_circuit_type(case_id, metadata)

    signal_inputs = [str(item) for item in metadata.get("signal_inputs", [])]
    outputs = [str(item) for item in metadata.get("outputs", [])]
    supplies = [str(item) for item in metadata.get("supplies", [])]
    bias_inputs = [str(item) for item in metadata.get("bias_inputs", [])]
    internal_nodes = [str(item) for item in metadata.get("internal_nodes", [])]

    ports = {
        "input": signal_inputs[:1],
        "output": outputs,
        "bias": bias_inputs,
        "supply_positive": supplies,
        "current_probe": outputs or internal_nodes,
    }
    if len(signal_inputs) >= 2:
        ports["differential_positive"] = [signal_inputs[0]]
        ports["differential_negative"] = [signal_inputs[1]]
        ports["common_mode"] = signal_inputs[:2]
    if circuit_type == CircuitType.MIXER and len(signal_inputs) >= 2:
        ports["input"] = [signal_inputs[0]]
        ports["reference"] = [signal_inputs[1]]

    nominal_supply = None
    for source in metadata.get("sources", []):
        if str(source.get("role", "")).upper() == "SUPPLY_SOURCE" and source.get("original_dc_value") is not None:
            nominal_supply = source.get("original_dc_value")
            break

    process_corners = []
    if circuit_type in {
        CircuitType.AMPLIFIER,
        CircuitType.OPERATIONAL_AMPLIFIER,
        CircuitType.DIFFERENTIAL_AMPLIFIER,
        CircuitType.INSTRUMENTATION_AMPLIFIER,
    }:
        process_corners = ["tt"]

    spec_data = {
        "name": case_id,
        "case_id": case_id,
        "circuit_type": circuit_type.value,
        "input_conditions": {
            "input_nodes": signal_inputs,
            "output_nodes": outputs,
            "temperature": 27,
            "vdd": nominal_supply if nominal_supply is not None else 1.8,
        },
        "ports": ports,
        "operating_conditions": {
            "nominal_temperature": 27,
            "nominal_supply": nominal_supply if nominal_supply is not None else 1.8,
            "process_corner": "tt",
        },
        "process_corners": process_corners,
        "temperature_range": "extended",
        "supply_variation": 0.1,
        "verification": {"auto_select": True},
        "test_categories": [],
        "performance_targets": {},
        "test_requirements": {},
        "raw_specs": metadata.get("description", ""),
        "description": metadata.get("description", ""),
        "measurement": {
            "ground_node": harness.get("ground_node"),
        },
    }
    return Specification.from_dict(spec_data)


def write_applicability_matrix() -> None:
    engine = VerificationApplicabilityEngine()
    normalizer = BenchmarkDeckNormalizer()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "case_id",
        "circuit_type",
        "test_id",
        "status",
        "reasons",
        "missing_port_roles",
        "missing_spec_fields",
    ]
    with APPLICABILITY_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in sorted(manifest_rows(), key=lambda item: item["netlist"]):
            case_id = Path(row["netlist"]).stem
            result = normalizer.normalize(
                BENCHMARK_DIR / row["netlist"],
                case_id=case_id,
                declared_type=row["type"],
                declared_topology=row["description"],
                description=row["description"],
            )
            specification = build_specification(case_id, result.circuit_metadata, result.harness_metadata)
            evaluations = engine.evaluate_all(specification)
            for evaluation in evaluations:
                writer.writerow(
                    {
                        "case_id": specification.case_id or specification.name,
                        "circuit_type": specification.circuit_type.value,
                        "test_id": evaluation.test_id.name,
                        "status": evaluation.status.value,
                        "reasons": ";".join(evaluation.reasons),
                        "missing_port_roles": ";".join(evaluation.missing_port_roles),
                        "missing_spec_fields": ";".join(evaluation.missing_spec_fields),
                    }
                )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_verification_registry_csv(REGISTRY_CSV)
    write_applicability_matrix()


if __name__ == "__main__":
    main()
