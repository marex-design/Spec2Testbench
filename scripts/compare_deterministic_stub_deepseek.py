from __future__ import annotations

from deepseek_live_lib import compare_deterministic_stub_deepseek


def main() -> None:
    compare_deterministic_stub_deepseek()
    print("results/deepseek_live_v1/deterministic_vs_stub_vs_deepseek.csv")


if __name__ == "__main__":
    main()
