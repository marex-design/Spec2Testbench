from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spec2testbench.infrastructure.llm.deepseek_provider import DeepSeekProvider, DeepSeekProviderConfig


def main() -> None:
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY is not set. Configure it first, then rerun.")

    config = DeepSeekProviderConfig.from_env()
    provider = DeepSeekProvider(config)
    models = provider.list_models()
    if not models:
        raise SystemExit("DeepSeek returned no models.")

    for model_name in models:
        print(model_name)

    requested_model = os.getenv("DEEPSEEK_MODEL", "").strip()
    if not requested_model:
        raise SystemExit(
            "\nDEEPSEEK_MODEL is not set. Pick one of the models above, export DEEPSEEK_MODEL, then rerun."
        )
    if requested_model not in models:
        raise SystemExit(
            f"\nConfigured model '{requested_model}' is not available from the current DeepSeek account."
        )
    print(f"\nConfigured model OK: {requested_model}")


if __name__ == "__main__":
    main()

