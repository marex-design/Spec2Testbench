from __future__ import annotations

from deepseek_live_lib import build_pre_live_manifest, freeze_frozen_protocol, run_secret_audit


def main() -> None:
    build_pre_live_manifest()
    run_secret_audit()
    freeze_frozen_protocol()
    print("results/deepseek_live_v1/pre_live_manifest.json")
    print("results/deepseek_live_v1/frozen_protocol_manifest.json")


if __name__ == "__main__":
    main()
