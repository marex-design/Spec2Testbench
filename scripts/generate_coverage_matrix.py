import csv
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from spec2testbench.domain.registry.supported_circuits import SUPPORTED_CIRCUITS
from spec2testbench.domain.registry.supported_tests import get_all_tests


def main():
    output_dir = Path("results")
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / "coverage_matrix.csv"

    tests = get_all_tests()

    with output_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        writer.writerow([
            "circuit",
            "test_category",
            "test_name",
            "pyspice_generated",
            "simulation_runs",
            "markdown_report",
            "png_schematic",
            "verdict",
        ])

        for circuit in SUPPORTED_CIRCUITS:
            for test in tests:
                writer.writerow([
                    circuit,
                    test["category"],
                    test["name"],
                    "not_tested",
                    "not_tested",
                    "not_tested",
                    "not_tested",
                    "PENDING",
                ])

    print(f"Coverage matrix generated: {output_file}")
    print(f"Circuits: {len(SUPPORTED_CIRCUITS)}")
    print(f"Tests: {len(tests)}")
    print(f"Total combinations: {len(SUPPORTED_CIRCUITS) * len(tests)}")


if __name__ == "__main__":
    main()