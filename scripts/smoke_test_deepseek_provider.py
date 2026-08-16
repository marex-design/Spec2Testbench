from __future__ import annotations

import argparse
import json
from pathlib import Path

from spec2testbench.application.ports.llm_provider import LLMRequest
from spec2testbench.infrastructure.llm.deepseek_provider import DeepSeekProvider, DeepSeekProviderConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one minimal JSON-only DeepSeek provider smoke request")
    parser.add_argument("--output", default="scientific_evidence/live/provider_smoke.json")
    parser.add_argument("--top-p", type=float, default=None)
    args = parser.parse_args()
    config = DeepSeekProviderConfig.from_env()
    config.validate_model_selection()
    provider = DeepSeekProvider(config)
    response = provider.generate(LLMRequest(
        system_prompt="Return only a valid JSON object. Do not include markdown.",
        user_payload={"task": "provider_smoke", "expected": {"status": "OK"}},
        response_format={"type": "json_object"},
        model=config.model,
        temperature=config.temperature,
        max_tokens=min(config.max_tokens, 128),
        timeout_seconds=config.timeout_seconds,
        top_p=config.top_p if args.top_p is None else args.top_p,
        metadata={"scientific_evidence": False},
    ))
    parsed = json.loads(response.content)
    payload = {
        "provider": response.provider,
        "model": response.model,
        "temperature": config.temperature,
        "top_p": config.top_p if args.top_p is None else args.top_p,
        "json_valid": isinstance(parsed, dict),
        "finish_reason": response.finish_reason,
        "prompt_tokens": response.prompt_tokens,
        "completion_tokens": response.completion_tokens,
        "total_tokens": response.total_tokens,
        "latency_seconds": response.latency_seconds,
        "transport_metadata": response.raw_metadata,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
