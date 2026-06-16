"""Generate reference testbenches for the 28 imported AnalogCoder-Pro circuits."""

from __future__ import annotations

import csv
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from spec2testbench.infrastructure.testbench import TestBenchGenerator

SPEC_DIR = ROOT / "examples" / "benchmark_specs"
NETLIST_DIR = ROOT / "benchmark" / "analogcoder_pro"
OUT_DIR = ROOT / "testbenches" / "benchmark"


def source_task_id(specification: Specification) -> int:
    source = specification.input_conditions.get("source", {})
    if isinstance(source, dict) and "task_id" in source:
        return int(source["task_id"])
    prefix = specification.name.split("_p", 1)[-1].split("_", 1)[0]
    return int(prefix)


def matching_netlist(spec_path: Path) -> Path:
    stem = spec_path.stem
    candidate = NETLIST_DIR / f"{stem}.cir"
    if candidate.exists():
        return candidate
    task_prefix = stem.split("_", 1)[0]
    matches = sorted(NETLIST_DIR.glob(f"{task_prefix}_*.cir"))
    if not matches:
        raise FileNotFoundError(f"No netlist found for {spec_path.name}")
    return matches[0]


def main() -> None:
    specs = sorted(SPEC_DIR.glob("p*.yaml"))
    if len(specs) != 28:
        raise RuntimeError(f"Expected 28 YAML specs in {SPEC_DIR}, found {len(specs)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    generator = TestBenchGenerator(use_llm=False)
    simulator = PySpiceSimulator()

    rows = []
    for spec_path in specs:
        netlist_path = matching_netlist(spec_path)
        specification = Specification.from_yaml(spec_path)
        testbench = generator.generate(specification)
        testbench.netlist_path = str(netlist_path.relative_to(ROOT))

        task_name = spec_path.stem
        spice_path = OUT_DIR / f"{task_name}_tb.cir"
        py_path = OUT_DIR / f"{task_name}_tb.py"

        spice_deck = simulator._generate_spice_deck(netlist_path, testbench)
        py_code = testbench.generate_pyspice_code()

        spice_path.write_text(spice_deck, encoding="utf-8")
        py_path.write_text(py_code, encoding="utf-8")

        rows.append(
            {
                "spec": str(spec_path.relative_to(ROOT)),
                "netlist": str(netlist_path.relative_to(ROOT)),
                "spice_testbench": str(spice_path.relative_to(ROOT)),
                "pyspice_testbench": str(py_path.relative_to(ROOT)),
                "analyses": ",".join(analysis.type.value for analysis in testbench.analyses),
                "measurements": ",".join(measurement.name for measurement in testbench.measurements),
                "stimuli": ",".join(stimulus.name for stimulus in testbench.stimuli),
            }
        )

    with (OUT_DIR / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {len(rows)} reference testbenches in {OUT_DIR.relative_to(ROOT)}")
    print(f"Manifest: {(OUT_DIR / 'manifest.csv').relative_to(ROOT)}")


if __name__ == "__main__":
    main()

