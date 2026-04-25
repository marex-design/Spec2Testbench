from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Spec2Testbench - Automated SPICE testbench verification pipeline"
    )

    parser.add_argument(
        "--case",
        required=True,
        help="Path to the case directory, e.g. cases/example_case",
    )

    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config.yaml",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON result",
    )

    args = parser.parse_args()

    result = run_pipeline(
        case_dir=Path(args.case),
        config_path=Path(args.config),
    )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    print("\n=== Spec2Testbench Result ===")
    print(f"Case ID       : {result['case_id']}")
    print(f"Final Verdict : {result['final_verdict']}")
    print(f"Passed        : {result['passed']}")

    checker = result.get("checker")

    if checker:
        print("\nMeasurements:")
        for item in checker["results"]:
            name = item["name"]
            measured = item["measured_value"]
            op = item["operator"]
            expected = item["expected_value"]
            verdict = item["verdict"]

            print(f"- {name}: {measured} {op} {expected} => {verdict}")

    extraction = result.get("extraction", {})
    errors = extraction.get("errors", [])

    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"- {error}")

    print("\nOutputs:")
    print("- results/summary.json")
    print("- results/verdicts.json")
    print("- results/logs/")


if __name__ == "__main__":
    main()