from __future__ import annotations

from deepseek_live_lib import build_clean_commit_plan, build_deepseek_live_summary, build_pre_commit_inventory


def main() -> None:
    build_pre_commit_inventory()
    build_clean_commit_plan()
    build_deepseek_live_summary()
    print("results/deepseek_live_v1/deepseek_live_campaign_summary.json")
    print("reports/deepseek_live_v1/final_status.md")


if __name__ == "__main__":
    main()
