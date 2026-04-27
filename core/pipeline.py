from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List

import yaml
from core.extractor import extract_log_results
from core.report import generate_report
from modules.specchecker.checker import check_specs
from modules.testbenchgen.generator import generate_testbench_file


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

    def run_ngspice(
        self,
        circuit_path: Path,
        log_path: Path,
        ngspice_command: str,
        timeout_seconds: int,
    ) -> Dict[str, Any]:
        """Run NGSPICE simulation."""
        import subprocess
        
        try:
            with open(log_path, "w", encoding="utf-8") as log_file:
                result = subprocess.run(
                    [ngspice_command, "-b", str(circuit_path)],
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    timeout=timeout_seconds,
                    text=True,
                )
            
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "log_path": str(log_path),
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Simulation timed out after {timeout_seconds} seconds",
                "log_path": str(log_path),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "log_path": str(log_path),
            }

    def run_candidate(
        self,
        case_dir: str | Path,
        candidate_dir: str | Path,
    ) -> Dict[str, Any]:
        """Run a single candidate test case."""
        case_dir = Path(case_dir)
        candidate_dir = Path(candidate_dir)

        spec_path = case_dir / "spec.yaml"
        source_circuit_path = candidate_dir / "circuit.cir"
        
        # Create outputs directory if it doesn't exist
        outputs_dir = candidate_dir / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        
        generated_circuit_path = outputs_dir / "generated_testbench.cir"
        
        circuit_path = generate_testbench_file(
            circuit_path=source_circuit_path,
            spec_path=spec_path,
            output_path=generated_circuit_path,
        )

        candidate_id = candidate_dir.name
        
        # Get logs directory from config, with fallback
        logs_dir = Path(self.config.get("paths", {}).get("logs_dir", "results/logs"))
         
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / f"{case_dir.name}_{candidate_id}.log"

        simulator_cfg = self.config.get("simulator", {})

        simulation_result = self.run_ngspice(
            circuit_path=circuit_path,
            log_path=log_path,
            ngspice_command=simulator_cfg.get("command", "ngspice"),
            timeout_seconds=simulator_cfg.get("timeout_seconds", 30),
        )

        extraction_result = extract_log_results(log_path)

        if not simulation_result["success"] or not extraction_result["success"]:
            final_result = {
                "candidate_id": candidate_id,
                "case_id": case_dir.name,
                "final_verdict": "FAIL",
                "passed": False,
                "simulation": simulation_result,
                "extraction": extraction_result,
                "checker": None,
            }
        else:
            checker_result = check_specs(
                spec_path=spec_path,
                measurements=extraction_result.get("measurements", {}),
            )

            final_result = {
                "candidate_id": candidate_id,
                "case_id": case_dir.name,
                "final_verdict": checker_result.get("final_verdict", "FAIL"),
                "passed": checker_result.get("passed", False),
                "simulation": simulation_result,
                "extraction": extraction_result,
                "checker": checker_result,
            }

        # Get output paths from config with defaults
        outputs_cfg = self.config.get("outputs", {})
        summary_path = outputs_cfg.get("summary_json", f"results/{case_dir.name}_{candidate_id}_summary.json")
        report_path = outputs_cfg.get("report_md", f"results/{case_dir.name}_{candidate_id}_report.md")

        self.save_json(summary_path, final_result)
        generate_report(final_result, report_path)

        return final_result

    def run_case(self, case_dir: str | Path) -> Dict[str, Any]:
        """Run a test case (supports single circuit or multiple candidates)."""
        case_dir = Path(case_dir)

        # Case with direct circuit.cir (no candidates folder)
        if (case_dir / "circuit.cir").exists():
            return self.run_candidate(
                case_dir=case_dir,
                candidate_dir=case_dir,
            )

        # Case with candidates folder
        candidate_dirs = find_candidate_dirs(case_dir)

        if not candidate_dirs:
            raise FileNotFoundError(
                f"No circuit.cir or candidates found in: {case_dir}"
            )

        candidate_results = [
            self.run_candidate(case_dir=case_dir, candidate_dir=candidate_dir)
            for candidate_dir in candidate_dirs
        ]

        passed_candidates = [
            result for result in candidate_results if result.get("passed") is True
        ]

        final_result = {
            "case_id": case_dir.name,
            "num_candidates": len(candidate_results),
            "passed_candidates": len(passed_candidates),
            "failed_candidates": len(candidate_results) - len(passed_candidates),
            "pass_at_k": len(passed_candidates) > 0,
            "candidates": candidate_results,
        }

        self.save_json(f"results/{case_dir.name}_summary.json", final_result)

        return final_result


def run_pipeline(
    case_dir: str | Path,
    config_path: str | Path = "config.yaml",
) -> Dict[str, Any]:
    """Run pipeline for a single test case."""
    pipeline = Spec2TestbenchPipeline(config_path=config_path)
    return pipeline.run_case(case_dir)


def find_experiment_cases(cases_root: str | Path = "cases") -> List[Path]:
    """Find all experiment cases containing spec.yaml."""
    cases_root = Path(cases_root)

    if not cases_root.exists():
        raise FileNotFoundError(f"Cases directory not found: {cases_root}")

    case_dirs = []

    for path in cases_root.rglob("spec.yaml"):
        case_dirs.append(path.parent)

    return sorted(case_dirs)


def find_candidate_dirs(case_dir: str | Path) -> List[Path]:
    """Find all candidate directories containing circuit.cir."""
    case_dir = Path(case_dir)
    candidates_dir = case_dir / "candidates"

    if candidates_dir.exists():
        candidate_dirs = [
            path
            for path in candidates_dir.iterdir()
            if path.is_dir() and (path / "circuit.cir").exists()
        ]
        return sorted(candidate_dirs)

    if (case_dir / "circuit.cir").exists():
        return [case_dir]

    return []


def run_all_cases(
    cases_root: str | Path = "cases",
    config_path: str | Path = "config.yaml",
) -> Dict[str, Any]:
    """Run pipeline for all test cases."""
    pipeline = Spec2TestbenchPipeline(config_path=config_path)
    case_dirs = find_experiment_cases(cases_root)

    all_results = []

    for case_dir in case_dirs:
        try:
            candidate_dirs = find_candidate_dirs(case_dir)

            candidate_results = []

            for candidate_dir in candidate_dirs:
                result = pipeline.run_candidate(
                    case_dir=case_dir,
                    candidate_dir=candidate_dir,
                )
                candidate_results.append(result)

            passed_candidates = [
                result for result in candidate_results if result.get("passed") is True
            ]

            case_result = {
                "case_id": case_dir.name,
                "num_candidates": len(candidate_results),
                "passed_candidates": len(passed_candidates),
                "failed_candidates": len(candidate_results) - len(passed_candidates),
                "pass_at_k": len(passed_candidates) > 0,
                "candidates": [
                    {
                        "candidate_id": result.get("candidate_id"),
                        "final_verdict": result.get("final_verdict"),
                        "passed": result.get("passed"),
                    }
                    for result in candidate_results
                ],
            }

            all_results.append(case_result)
        except Exception as e:
            all_results.append({
                "case_id": case_dir.name,
                "error": str(e),
                "pass_at_k": False,
            })

    total_cases = len(all_results)
    pass_at_k_count = sum(1 for result in all_results if result.get("pass_at_k", False))

    global_result = {
        "total_cases": total_cases,
        "pass_at_k_count": pass_at_k_count,
        "fail_at_k_count": total_cases - pass_at_k_count,
        "pass_at_k_rate": pass_at_k_count / total_cases if total_cases > 0 else 0,
        "cases": all_results,
    }

    # Create results directory if it doesn't exist
    Path("results").mkdir(parents=True, exist_ok=True)
    pipeline.save_json("results/global_summary.json", global_result)

    return global_result