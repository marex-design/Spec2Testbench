from __future__ import annotations
from typing import Protocol, Any
class LLMProvider(Protocol):
    def generate(self, payload: dict[str,Any]) -> dict[str,Any] | str: ...
