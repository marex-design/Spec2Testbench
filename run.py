from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Any

from core.pipeline import run_pipeline, run_all_cases


def print_result(result: Dict[str, Any]) -> None:
    """Print a single test case result."""
    print("\n=== Spec2Testbench Result ===")
    print(f"Case ID         : {result.get('case_id', 'N/A')}")
    print(f"Final verdict   : {result.get('final_verdict', 'N/A')}")
    print(f"Passed          : {result.get('passed', False)}")
    
    if 'num_candidates' in result:
        print(f"Num candidates  : {result.get('num_candidates', 0)}")
        print(f"Passed candidates: {result.get('passed_candidates', 0)}")
        print(f"Failed candidates: {result.get('failed_candidates', 0)}")
        print(f"Pass@k          : {result.get('pass_at_k', False)}")
    
    print("\nOutputs:")
    print("- results/summary.json")
    print("- results/report.md")


def print_global_result(result: Dict[str, Any]) -> None:
    """Print global results for all test cases."""
    print("\n=== Spec2Testbench Global Result ===")
    print(f"Total cases      : {result['total_cases']}")
    print(f"Pass@k cases     : {result['pass_at_k_count']}")
    print(f"Fail@k cases     : {result['fail_at_k_count']}")
    print(f"Pass@k rate      : {result['pass_at_k_rate']:.2%}")

    print("\nCases:")
    for case in result["cases"]:
        # Handle both formats: with pass_at_k or with error
        if "error" in case:
            print(f"- {case['case_id']}: ERROR - {case['error']}")
        else:
            print(
                f"- {case['case_id']}: "
                f"Pass@k={case['pass_at_k']} "
                f"({case['passed_candidates']}/{case['num_candidates']} candidates passed)"
            )

            for candidate in case.get("candidates", []):
                print(
                    f"  - {candidate['candidate_id']}: "
                    f"{candidate['final_verdict']} "
                    f"(passed={candidate['passed']})"
                )

    print("\nOutputs:")
    print("- results/global_summary.json")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Spec2Testbench - Automatic testbench generation and verification"
    )
    
    parser.add_argument(
        "--case",
        type=str,
        help="Run a single test case (path to case directory)",
    )
    
    parser.add_argument(
        "--cases-root",
        type=str,
        default="cases",
        help="Root directory containing test cases (default: cases)",
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)",
    )
    
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all test cases",
    )
    
    args = parser.parse_args()
    
    # Create results directory if it doesn't exist
    Path("results").mkdir(parents=True, exist_ok=True)
    
    if args.all:
        print("Running all test cases...")
        global_result = run_all_cases(
            cases_root=args.cases_root,
            config_path=args.config,
        )
        print_global_result(global_result)
    
    elif args.case:
        print(f"Running single test case: {args.case}")
        result = run_pipeline(
            case_dir=args.case,
            config_path=args.config,
        )
        print_result(result)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()