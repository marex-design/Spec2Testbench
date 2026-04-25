from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any

import yaml

from core.simulator import run_ngspice
from core.extractor import extract_log_results
from core.report import generate_report
from modules.specchecker.checker import check_specs


class Spec2TestbenchPipeline:
    def __init__(self, config_path: str | Path = "config.yaml"):
        self.config_path = Path(config_path)
        self.config = self.load_yaml(self.config_path)

    def load_yaml(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"YAML file not found: {path}")

        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file)

    def save_json(self, path: str | Path, data: Dict[str, Any]) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)

    def run_case(self, case_dir: str | Path) -> Dict[str, Any]:
        case_dir = Path(case_dir)

        spec_path = case_dir / "spec.yaml"
        circuit_path = case_dir / "circuit.cir"

        case_id = case_dir.name
        logs_dir = Path(self.config["paths"]["logs_dir"])
        log_path = logs_dir / f"{case_id}.log"

        simulator_cfg = self.config.get("simulator", {})

        simulation_result = run_ngspice(
            circuit_path=circuit_path,
            log_path=log_path,
            ngspice_command=simulator_cfg.get("command", "ngspice"),
            timeout_seconds=simulator_cfg.get("timeout_seconds", 30),
        )

        extraction_result = extract_log_results(log_path)

        if not simulation_result["success"] or not extraction_result["success"]:
            final_result = {
                "case_id": case_id,
                "final_verdict": "FAIL",
                "passed": False,
                "simulation": simulation_result,
                "extraction": extraction_result,
                "checker": None,
            }
        else:
            checker_result = check_specs(
                spec_path=spec_path,
                measurements=extraction_result["measurements"],
            )

            final_result = {
                "case_id": case_id,
                "final_verdict": checker_result["final_verdict"],
                "passed": checker_result["passed"],
                "simulation": simulation_result,
                "extraction": extraction_result,
                "checker": checker_result,
            }

        summary_path = self.config.get("outputs", {}).get(
            "summary_json",
            "results/summary.json",
        )

        verdicts_path = self.config.get("outputs", {}).get(
            "verdicts_json",
            "results/verdicts.json",
        )

        report_path = self.config.get("outputs", {}).get(
            "report_md",
            "results/report.md",
        )

        self.save_json(summary_path, final_result)

        self.save_json(
            verdicts_path,
            {
                "case_id": case_id,
                "final_verdict": final_result["final_verdict"],
                "passed": final_result["passed"],
                "measurements": extraction_result.get("measurements", {}),
                "errors": extraction_result.get("errors", []),
            },
        )

        generate_report(final_result, report_path)

        return final_result


def run_pipeline(
    case_dir: str | Path,
    config_path: str | Path = "config.yaml",
) -> Dict[str, Any]:
    pipeline = Spec2TestbenchPipeline(config_path=config_path)
    return pipeline.run_case(case_dir)