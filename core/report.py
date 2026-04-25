from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


class MarkdownReport:
    def __init__(self, result: Dict[str, Any]):
        self.result = result

    def build(self) -> str:
        case_id = self.result.get("case_id", "unknown")
        final_verdict = self.result.get("final_verdict", "UNKNOWN")
        passed = self.result.get("passed", False)

        simulation = self.result.get("simulation", {})
        extraction = self.result.get("extraction", {})
        checker = self.result.get("checker", {})

        lines = []

        lines.append("# Spec2Testbench Report")
        lines.append("")
        lines.append(f"## Case")
        lines.append("")
        lines.append(f"- Case ID: `{case_id}`")
        lines.append(f"- Final verdict: **{final_verdict}**")
        lines.append(f"- Passed: `{passed}`")
        lines.append("")

        lines.append("## Simulation")
        lines.append("")
        lines.append(f"- Success: `{simulation.get('success')}`")
        lines.append(f"- Command: `{simulation.get('command')}`")
        lines.append(f"- Circuit: `{simulation.get('circuit_path')}`")
        lines.append(f"- Log: `{simulation.get('log_path')}`")
        lines.append("")

        lines.append("## Extracted Measurements")
        lines.append("")
        measurements = extraction.get("measurements", {})

        if measurements:
            lines.append("| Measurement | Value |")
            lines.append("|---|---:|")
            for name, value in measurements.items():
                lines.append(f"| `{name}` | {value} |")
        else:
            lines.append("No measurement extracted.")
        lines.append("")

        lines.append("## Specification Checking")
        lines.append("")

        checker_results = checker.get("results", []) if checker else []

        if checker_results:
            lines.append("| Measurement | Measured | Requirement | Verdict |")
            lines.append("|---|---:|---:|---|")

            for item in checker_results:
                name = item.get("name")
                measured = item.get("measured_value")
                op = item.get("operator")
                expected = item.get("expected_value")
                verdict = item.get("verdict")

                lines.append(
                    f"| `{name}` | {measured} | {op} {expected} | **{verdict}** |"
                )
        else:
            lines.append("No checker result available.")
        lines.append("")

        errors = extraction.get("errors", [])

        lines.append("## Errors")
        lines.append("")

        if errors:
            for error in errors:
                lines.append(f"- `{error}`")
        else:
            lines.append("No error detected.")
        lines.append("")

        lines.append("## Conclusion")
        lines.append("")

        if final_verdict == "PASS":
            lines.append("The circuit is simulable and satisfies all declared specifications.")
        else:
            lines.append("The circuit is simulable or partially simulable, but it does not satisfy all declared specifications.")

        lines.append("")

        return "\n".join(lines)


def generate_report(result: Dict[str, Any], report_path: str | Path) -> str:
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    report = MarkdownReport(result).build()
    report_path.write_text(report, encoding="utf-8")

    return report