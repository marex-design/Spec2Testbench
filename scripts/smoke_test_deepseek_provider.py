from __future__ import annotations

from deepseek_live_lib import run_provider_smoke


def main() -> None:
    result = run_provider_smoke()
    print("results/deepseek_live_v1/provider_smoke.json")
    if result.get("GO_PROVIDER_SMOKE") != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
