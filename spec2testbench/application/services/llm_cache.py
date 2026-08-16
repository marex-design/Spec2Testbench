from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LLMCacheKey:
    case_id: str
    mode: str
    trial_id: str
    provider: str
    model: str
    prompt_sha256: str
    specification_sha256: str
    netlist_sha256: str
    capability_registry_sha256: str
    temperature: float
    max_tokens: int
    knowledge_version: str = ""
    knowledge_bundle_sha256: str = ""
    canonical_dut_sha256: str = ""
    harness_metadata_sha256: str = ""
    requested_metrics_sha256: str = ""
    compiler_version: str = ""

    def digest(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class FileLLMCache:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def load(self, key: LLMCacheKey) -> dict[str, Any] | None:
        path = self._cache_path(key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, key: LLMCacheKey, payload: dict[str, Any]) -> Path:
        path = self._cache_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def _cache_path(self, key: LLMCacheKey) -> Path:
        return self._root / key.case_id / key.mode / key.trial_id / f"{key.digest()}.json"
