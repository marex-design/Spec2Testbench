from __future__ import annotations

from deepseek_live_lib import run_frozen_trial_one


def main() -> None:
    result = run_frozen_trial_one()
    print("results/deepseek_live_v1/frozen_trial_1_summary.json")
    if result.get("GO_LIVE_FROZEN_TRIAL_1") != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
