from __future__ import annotations
from typing import Any

class DeterministicStubProvider:
    """No-network provider used to test the LLM planning boundary deterministically."""
    mode='STUB'
    def generate(self,payload:dict[str,Any])->dict[str,Any]:
        return dict(payload['deterministic_plan'])
