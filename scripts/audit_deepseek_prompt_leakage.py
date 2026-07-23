from __future__ import annotations

from deepseek_live_lib import audit_deepseek_prompt_leakage


def main() -> None:
    audit_deepseek_prompt_leakage()
    print("results/deepseek_live_v1/prompt_leakage_audit.csv")


if __name__ == "__main__":
    main()
