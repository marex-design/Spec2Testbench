from __future__ import annotations

import argparse
import os

from deepseek_live_lib import (
    STAGE_ORDER,
    build_clean_commit_plan,
    build_deepseek_live_summary,
    build_pre_commit_inventory,
    build_pre_live_manifest,
    run_secret_audit,
    run_stage,
)


FLAG_TO_STAGE = {
    "discover_models": "model_discovery",
    "provider_smoke": "provider_smoke",
    "single_cases": "single_schmitt",
    "use_case_smoke": "use_case_smoke",
    "freeze_frozen_protocol": "frozen_protocol_freeze",
    "frozen_trial_one": "frozen_trial_1",
    "frozen_three_trials": "frozen_trials_2_3",
    "post_live_deterministic_parity": "post_live_deterministic",
}


def _selected_stages(args: argparse.Namespace) -> list[str]:
    if args.only_stage:
        return [args.only_stage]
    if args.through_stage:
        index = STAGE_ORDER.index(args.through_stage)
        return STAGE_ORDER[: index + 1]
    selected = []
    for flag, stage in FLAG_TO_STAGE.items():
        if getattr(args, flag):
            selected.append(stage)
    return selected or ["model_discovery"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the DeepSeek live campaign stages")
    parser.add_argument("--discover-models", action="store_true")
    parser.add_argument("--provider-smoke", action="store_true")
    parser.add_argument("--single-cases", action="store_true")
    parser.add_argument("--use-case-smoke", action="store_true")
    parser.add_argument("--freeze-frozen-protocol", action="store_true")
    parser.add_argument("--frozen-trial-one", action="store_true")
    parser.add_argument("--frozen-three-trials", action="store_true")
    parser.add_argument("--post-live-deterministic-parity", action="store_true")
    parser.add_argument("--through-stage", choices=STAGE_ORDER)
    parser.add_argument("--only-stage", choices=STAGE_ORDER)
    parser.add_argument("--case-id")
    parser.add_argument("--use-case")
    parser.add_argument("--trial-id")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force-new-provider-call", action="store_true")
    parser.add_argument("--max-live-calls", type=int)
    parser.add_argument("--max-repairs", type=int)
    parser.add_argument("--stop-on-provider-error", action="store_true")
    parser.add_argument("--stop-on-systemic-error", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--disable-pyspice", action="store_true")
    parser.add_argument("--no-mock", action="store_true")
    args = parser.parse_args()

    if args.disable_pyspice:
        os.environ["SPEC2TESTBENCH_DISABLE_PYSPICE"] = "1"

    build_pre_live_manifest()
    run_secret_audit()
    build_pre_commit_inventory()
    build_clean_commit_plan()

    if args.dry_run or args.verify_only:
        build_deepseek_live_summary()
        print("results/deepseek_live_v1/pre_live_manifest.json")
        print("results/deepseek_live_v1/secret_audit.json")
        print("results/deepseek_live_v1/deepseek_live_campaign_summary.json")
        return

    for stage in _selected_stages(args):
        result = run_stage(stage)
        go_values = [value for key, value in result.items() if key.startswith("GO_")]
        if go_values and any(value not in {"PASS", "NOT_EXECUTED"} for value in go_values):
            break

    build_deepseek_live_summary()
    print("results/deepseek_live_v1/deepseek_live_campaign_summary.json")
    print("reports/deepseek_live_v1/final_status.md")


if __name__ == "__main__":
    main()
