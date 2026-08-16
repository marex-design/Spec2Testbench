from __future__ import annotations

import argparse
import json
from pathlib import Path

from spec2testbench.infrastructure.llm.deepseek_provider import DeepSeekProvider, DeepSeekProviderConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover DeepSeek model identifiers using the configured account")
    parser.add_argument("--output", default="scientific_evidence/live/model_discovery.json")
    args = parser.parse_args()
    provider = DeepSeekProvider(DeepSeekProviderConfig.from_env())
    payload = provider.discover_models()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
