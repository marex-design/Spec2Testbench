from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Optional


from spec2testbench.domain.entities.testbench_plan import TestbenchPlan


class DeepSeekPlanProvider:
    """Live DeepSeek provider restricted to TestbenchPlan generation.

    The provider proposes a structured plan only. It is not allowed to modify the
    DUT, specification thresholds, or compliance verdicts. Those remain under the
    deterministic framework boundary.
    """

    mode = "DEEPSEEK_LIVE"
    scientific_llm_evidence = True
    provider_name = "deepseek"
    prompt_version = "h1-plan-v1"
    default_base_url = "https://api.deepseek.com"
    default_model = "deepseek-v4-pro"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        max_tokens: int = 4096,
        thinking: bool = False,
        client: Any = None,
    ) -> None:
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        if not self.api_key and client is None:
            raise RuntimeError(
                "DEEPSEEK_API_KEY is not configured. Export it in the shell; "
                "do not store the key in the repository."
            )
        self.model = model or os.getenv("DEEPSEEK_MODEL", self.default_model)
        if self.model not in {"deepseek-v4-flash", "deepseek-v4-pro"}:
            raise ValueError(
                "Unsupported DeepSeek model for H1: "
                f"{self.model!r}. Use deepseek-v4-flash or deepseek-v4-pro."
            )
        self.base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", self.default_base_url)
        self.max_tokens = int(max_tokens)
        self.thinking = bool(thinking)
        if client is not None:
            self.client = client
        else:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.last_call_metadata: dict[str, Any] = {}

    @staticmethod
    def _sha256_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _system_prompt(self) -> str:
        return (
            "You are the planning component inside Spec2Testbench, a hybrid "
            "LLM-SPICE analog verification framework. Return JSON only. Your only "
            "task is to propose a TestbenchPlan. You MUST NOT modify the DUT netlist, "
            "MUST NOT modify specification thresholds or requirement operators, and "
            "MUST NOT decide PASS/FAIL/COMPLIANT/NONCOMPLIANT. Use only metrics present "
            "in the frozen specification and only circuit nodes supplied by the input. "
            "The deterministic validator will reject unsafe or inconsistent plans. "
            "When a repair object is present, correct only the cited planning issue. "
            "Do not set provider_mode or scientific_llm_evidence; these provenance "
            "fields are owned and stamped by the deterministic framework."
        )

    def _request_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        schema = json.loads(json.dumps(TestbenchPlan.model_json_schema()))
        properties = schema.get("properties", {})
        for framework_owned in ("provider_mode", "scientific_llm_evidence"):
            properties.pop(framework_owned, None)
            if framework_owned in schema.get("required", []):
                schema["required"].remove(framework_owned)
        return {
            "task": "propose_testbench_plan",
            "prompt_version": self.prompt_version,
            "testbench_plan_json_schema": schema,
            "case_id": payload.get("case_id"),
            "specification": payload.get("specification"),
            "deterministic_seed_plan": payload.get("deterministic_plan"),
            "repair": payload.get("repair"),
            "constraints": {
                "dut_immutable": True,
                "thresholds_immutable": True,
                "verdict_is_deterministic_only": True,
                "json_only": True,
            },
        }

    def generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        user_obj = self._request_payload(payload)
        user_text = json.dumps(user_obj, sort_keys=True, separators=(",", ":"))
        system_text = self._system_prompt()
        request_fingerprint = self._sha256_text(system_text + "\n" + user_text)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": self.max_tokens,
            # Explicitly disable thinking for the first H1 planning baseline.
            # This reduces variance and makes the planning boundary easier to audit.
            "extra_body": {"thinking": {"type": "enabled" if self.thinking else "disabled"}},
        }

        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)

        usage = getattr(response, "usage", None)
        self.last_call_metadata = {
            "provider": self.provider_name,
            "provider_mode": self.mode,
            "prompt_version": self.prompt_version,
            "requested_model": self.model,
            "response_model": getattr(response, "model", None),
            "base_url": self.base_url,
            "thinking": self.thinking,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "request_sha256": request_fingerprint,
            "response_sha256": self._sha256_text(content),
            "usage": {
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            },
        }
        return parsed
