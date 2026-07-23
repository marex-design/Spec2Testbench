from __future__ import annotations

from deepseek_live_lib import run_frozen_three_trials


def main() -> None:
    result = run_frozen_three_trials()
    print("results/deepseek_live_v1/frozen_three_trials_summary.json")
    if result.get("GO_LIVE_FROZEN_THREE_TRIALS") != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
