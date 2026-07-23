from __future__ import annotations

from deepseek_live_lib import audit_deepseek_live_cache


def main() -> None:
    audit_deepseek_live_cache()
    print("results/deepseek_live_v1/frozen_cache_audit.csv")


if __name__ == "__main__":
    main()
