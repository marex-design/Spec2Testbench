from __future__ import annotations

from deepseek_live_lib import run_single_cases


def main() -> None:
    result = run_single_cases()
    print("results/deepseek_live_v1/single_cases_summary.json")
    if result.get("GO_LIVE_SINGLE_CASES") != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
