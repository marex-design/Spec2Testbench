from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml


class TestbenchGenerator:
    def __init__(self, library_dir: str | Path = "library"):
        self.library_dir = Path(library_dir)
        self.tests = self.load_all_tests()

    def load_yaml(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"YAML file not found: {path}")

        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file)

    def load_all_tests(self) -> Dict[str, Dict[str, Any]]:
        tests: Dict[str, Dict[str, Any]] = {}

        for yaml_file in self.library_dir.glob("*_tests.yaml"):
            data = self.load_yaml(yaml_file) or {}

            for test in data.get("tests", []):
                test_id = test["id"]
                tests[test_id] = test

        return tests

    def get_test(self, test_id: str) -> Dict[str, Any]:
        if test_id not in self.tests:
            raise ValueError(f"Unknown test id: {test_id}")

        return self.tests[test_id]

    def validate_parameters(
        self,
        test: Dict[str, Any],
        parameters: Dict[str, Any],
    ) -> None:
        required_parameters = test.get("required_parameters", [])

        missing = [
            parameter
            for parameter in required_parameters
            if parameter not in parameters
        ]

        if missing:
            raise ValueError(
                f"Missing parameters for test '{test['id']}': {missing}"
            )

    def render_template(
        self,
        template: str,
        measurement_name: str,
        parameters: Dict[str, Any],
    ) -> str:
        values = dict(parameters)
        values["measurement_name"] = measurement_name

        return template.format(**values)

    def resolve_value(self, value: Any, parameters: Dict[str, Any]) -> Any:
        if isinstance(value, str):
            try:
                return value.format(**parameters)
            except KeyError:
                return value
        return value

    def generate_control_body(self, spec: Dict[str, Any]) -> str:
        enabled_tests = spec.get("enabled_tests", [])

        lines: List[str] = []

        for enabled_test in enabled_tests:
            test_id = enabled_test["id"]
            measurement_name = enabled_test["measurement_name"]
            parameters = enabled_test.get("parameters", {})

            test = self.get_test(test_id)
            self.validate_parameters(test, parameters)

            template = test["ngspice_template"]
            rendered = self.render_template(
                template=template,
                measurement_name=measurement_name,
                parameters=parameters,
            )

            lines.append(f"* Test: {test_id}")
            lines.append(rendered.strip())
            lines.append("")

        return "\n".join(lines).strip()

    def generate_measurement_specs(self, spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        enabled_tests = spec.get("enabled_tests", [])
        measurements: List[Dict[str, Any]] = []

        for enabled_test in enabled_tests:
            test_id = enabled_test["id"]
            measurement_name = enabled_test["measurement_name"]
            parameters = enabled_test.get("parameters", {})

            test = self.get_test(test_id)
            self.validate_parameters(test, parameters)

            checker = test.get("checker", {})
            operator = checker.get("operator")

            if operator == "range":
                measurements.append(
                    {
                        "name": measurement_name,
                        "requirement": {
                            "operator": "range",
                            "minimum": self.resolve_value(
                                checker["minimum"],
                                parameters,
                            ),
                            "maximum": self.resolve_value(
                                checker["maximum"],
                                parameters,
                            ),
                        },
                    }
                )
            else:
                measurements.append(
                    {
                        "name": measurement_name,
                        "requirement": {
                            "operator": operator,
                            "value": self.resolve_value(
                                checker.get("expected", checker.get("value")),
                                parameters,
                            ),
                        },
                    }
                )

        return measurements

    def generate_testbench_file(
        self,
        circuit_path: str | Path,
        spec_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        circuit_path = Path(circuit_path)
        spec_path = Path(spec_path)
        output_path = Path(output_path)

        spec = self.load_yaml(spec_path)

        if not circuit_path.exists():
            raise FileNotFoundError(f"Circuit file not found: {circuit_path}")

        circuit_text = circuit_path.read_text(encoding="utf-8")
        circuit_text = circuit_text.replace(".end", "").strip()

        simulation = spec.get("simulation", {})
        directive = simulation.get("directive")

        if not directive:
            raise ValueError("Missing simulation.directive in spec.yaml")

        control_body = self.generate_control_body(spec)

        testbench = f"""{circuit_text}

{directive}

.control
run
{control_body}
.endc

.end
"""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(testbench, encoding="utf-8")

        return output_path


# Module-level convenience functions
def generate_control_body(
    spec: Dict[str, Any],
    library_dir: str | Path = "library",
) -> str:
    """Generate NGSPICE control body from specification."""
    generator = TestbenchGenerator(library_dir=library_dir)
    return generator.generate_control_body(spec)


def generate_measurement_specs(
    spec: Dict[str, Any],
    library_dir: str | Path = "library",
) -> List[Dict[str, Any]]:
    """Generate measurement specifications from test specification."""
    generator = TestbenchGenerator(library_dir=library_dir)
    return generator.generate_measurement_specs(spec)


def generate_testbench_file(
    circuit_path: str | Path,
    spec_path: str | Path,
    output_path: str | Path,
    library_dir: str | Path = "library",
) -> Path:
    """Generate a complete testbench file from circuit and specification."""
    generator = TestbenchGenerator(library_dir=library_dir)
    return generator.generate_testbench_file(
        circuit_path=circuit_path,
        spec_path=spec_path,
        output_path=output_path,
    )