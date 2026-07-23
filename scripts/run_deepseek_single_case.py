from __future__ import annotations

import argparse

from deepseek_live_lib import run_single_case


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one DeepSeek live single-case stage")
    parser.add_argument(
        "--stage",
        required=True,
        choices=["single_ac", "single_transient", "single_oscillator", "single_schmitt"],
    )
    args = parser.parse_args()
    result = run_single_case(args.stage)
    print(f"results/deepseek_live_v1/{args.stage}.json")
    if next(value for key, value in result.items() if key.startswith("GO_")) != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
