from __future__ import annotations

from deepseek_live_lib import run_model_discovery


def main() -> None:
    result = run_model_discovery()
    print("results/deepseek_live_v1/model_discovery.json")
    if result.get("go_model_discovery") != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
