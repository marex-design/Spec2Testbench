"""Run a strict native-WRDATA extension without changing frozen pilot V2."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml

from spec2testbench.application.usecases.run_verification import VerificationPipeline
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator

OUT = ROOT / "artifacts" / "frozen_pilot_v2_wrdata_extension"
RESULTS = ROOT / "results"
REPORTS = ROOT / "reports"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    os.environ["SPEC2TESTBENCH_DISABLE_PYSPICE"] = "1"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = OUT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    netlist = ROOT / "benchmark" / "analogcoder_pro" / "p22_oscillator.cir"
    base = Specification.from_dict({
        "name": "wrdata_p22_amplitude",
        "circuit_type": "oscillator",
        "performance_targets": {"startup_amplitude": {"min": 1e-12, "unit": "V"}},
        "input_conditions": {"vdd": 5.0, "vcm": 2.5, "output_nodes": "Vout"},
        "test_categories": ["transient"],
        "case_id": "wrdata_nominal",
        "parent_circuit_id": "p22_oscillator",
        "measurement": {"required_backend": "NGSPICE_WRDATA", "allow_backend_fallback": False, "disable_pyspice": True},
    })
    pipeline = VerificationPipeline(use_llm=False, allow_mock=False, timeout_seconds=60)
    pipeline.simulator = PySpiceSimulator(timeout=60, allow_mock=False)
    rows = []
    for case_id, threshold in [("wrdata_nominal", 1e-12), ("wrdata_controlled_violation", 10.0)]:
        data = base.to_dict()
        data["case_id"] = case_id
        data["performance_targets"]["startup_amplitude"]["min"] = threshold
        spec = Specification.from_dict(data)
        tb = pipeline.testbench_gen.generate(spec)
        tb.case_id = case_id
        tb.metadata["required_metrics"] = ["startup_amplitude"]
        tb.metadata["measurement"] = spec.measurement
        sim = pipeline.simulator.run(netlist, tb, output_dir=run_dir / case_id)
        report = pipeline.verify(spec, netlist, simulation_results=sim)
        case_dir = run_dir / case_id
        case_dir.mkdir(exist_ok=True)
        native = sim.get("measurement_source")
        if native:
            source_dir = Path(native).parent
            for name in ("vectors.dat", "vectors.csv", "vector_metadata.json", "ngspice_stdout.txt", "ngspice_stderr.txt", "measures.txt"):
                source = source_dir / name
                if source.exists(): shutil.copy2(source, case_dir / name)
        (case_dir / "generated_testbench.cir").write_text(tb.generate_spice_deck(), encoding="utf-8")
        (case_dir / "simulation_results.json").write_text(json.dumps(sim, default=str, indent=2), encoding="utf-8")
        (case_dir / "verification_report.json").write_text(json.dumps(vars(report), default=str, indent=2), encoding="utf-8")
        trace = next((x for x in report.metric_traces if x.metric_name == "startup_amplitude"), None)
        row = {"case_id": case_id, "backend": report.measurement_backend, "status": trace.status if trace else "NOT_EVALUATED", "value": trace.measured_value if trace else "", "threshold": threshold, "verdict": report.compliance_status.value}
        rows.append(row)
        prov = dict(report.provenance or {})
        vectors = case_dir / "vectors.dat"
        prov.update({"measurement_backend": report.measurement_backend, "pyspice_used": False, "sample_count": sum(1 for _ in vectors.open(encoding="utf-8")) if vectors.exists() else 0, "signals": ["time", "v(vout)"], "wrdata_sha256": sha256(vectors) if vectors.exists() else None})
        (case_dir / "provenance.json").write_text(json.dumps(prov, indent=2), encoding="utf-8")
    with (RESULTS / "wrdata_extension_results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
    (REPORTS / "wrdata_end_to_end_validation.md").write_text("# WRDATA End-to-End Validation\n\n" + "\n".join(f"- `{r['case_id']}`: backend `{r['backend']}`, status `{r['status']}`, verdict `{r['verdict']}`" for r in rows) + "\n", encoding="utf-8")
    print(json.dumps({"run_id": run_id, "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
