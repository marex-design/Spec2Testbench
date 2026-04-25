from __future__ import annotations

import operator
from pathlib import Path
from typing import Any, Dict, List

import yaml


OPERATORS = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}


class SpecChecker:
    def __init__(self, spec_path: str | Path):
        self.spec_path = Path(spec_path)
        self.spec = self.load_spec()

    def load_spec(self) -> Dict[str, Any]:
        if not self.spec_path.exists():
            raise FileNotFoundError(f"Spec file not found: {self.spec_path}")

        with self.spec_path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file)

    def normalize_name(self, name: str) -> str:
        return name.lower()

    def check_measurement(
        self,
        measurement_name: str,
        measured_value: float,
        requirement: Dict[str, Any],
    ) -> Dict[str, Any]:
        op_symbol = requirement["operator"]
        expected_value = float(requirement["value"])

        if op_symbol not in OPERATORS:
            raise ValueError(f"Unsupported operator: {op_symbol}")

        passed = OPERATORS[op_symbol](measured_value, expected_value)

        return {
            "name": measurement_name,
            "measured_value": measured_value,
            "operator": op_symbol,
            "expected_value": expected_value,
            "passed": passed,
            "verdict": "PASS" if passed else "FAIL",
        }

    def check(self, measurements: Dict[str, float]) -> Dict[str, Any]:
        measurement_specs = self.spec.get("measurements", [])
        results: List[Dict[str, Any]] = []

        normalized_measurements = {
            self.normalize_name(name): value for name, value in measurements.items()
        }

        for item in measurement_specs:
            name = self.normalize_name(item["name"])
            requirement = item["requirement"]

            if name not in normalized_measurements:
                results.append(
                    {
                        "name": name,
                        "measured_value": None,
                        "operator": requirement.get("operator"),
                        "expected_value": requirement.get("value"),
                        "passed": False,
                        "verdict": "FAIL",
                        "reason": "Measurement not found",
                    }
                )
                continue

            result = self.check_measurement(
                measurement_name=name,
                measured_value=normalized_measurements[name],
                requirement=requirement,
            )
            results.append(result)

        final_pass = all(result["passed"] for result in results)

        return {
            "case_id": self.spec.get("case", {}).get("id", "unknown"),
            "final_verdict": "PASS" if final_pass else "FAIL",
            "passed": final_pass,
            "results": results,
        }


def check_specs(spec_path: str | Path, measurements: Dict[str, float]) -> Dict[str, Any]:
    checker = SpecChecker(spec_path)
    return checker.check(measurements)