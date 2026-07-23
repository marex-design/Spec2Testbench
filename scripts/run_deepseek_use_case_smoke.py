from __future__ import annotations

from deepseek_live_lib import run_use_case_smoke


def main() -> None:
    result = run_use_case_smoke()
    print("results/deepseek_live_v1/live_use_case_smoke_summary.json")
    if result.get("GO_LIVE_USE_CASE_SMOKE") != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
