from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "results" / "final_implementation"
REPORTS_DIR = ROOT / "reports" / "final_implementation"
BASELINE_VERSION_JSON = RESULTS_DIR / "baseline_version.json"
BASELINE_HASHES_CSV = RESULTS_DIR / "baseline_file_hashes.csv"
BASELINE_STATUS_MD = REPORTS_DIR / "baseline_status.md"


def git_output(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return (completed.stdout or completed.stderr or "").strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_paths() -> list[tuple[str, str, Path]]:
    groups: list[tuple[str, str, Path]] = []
    pattern_groups = {
        "ACP28_ORIGINAL_CIRCUITS": [
            "benchmark/analogcoder_pro/*.cir",
        ],
        "ACP28_NORMALIZED_CORPUS": [
            "benchmarks_normalized/analogcoder_pro/*/canonical_dut.ckt",
            "benchmarks_normalized/analogcoder_pro/*/original_deck.ckt",
            "benchmarks_normalized/analogcoder_pro/*/circuit_metadata.yaml",
            "benchmarks_normalized/analogcoder_pro/*/harness_metadata.yaml",
        ],
        "FROZEN_PILOT_V3": [
            "scripts/build_frozen_pilot_v3.py",
            "scripts/generate_frozen_pilot_v2.py",
        ],
        "KNOWLEDGE_BASE": [
            "knowledge/**/*",
            "spec2testbench/application/services/spice_knowledge.py",
        ],
        "LLM_PROMPTS": [
            "spec2testbench/infrastructure/llm/prompts/*",
        ],
        "PYDANTIC_MODELS": [
            "spec2testbench/domain/entities/testbench_plan.py",
            "scripts/deepseek_live_lib.py",
        ],
        "CHECKER": [
            "spec2testbench/infrastructure/spec_checker/*.py",
            "spec2testbench/infrastructure/waveform_checker/*.py",
            "spec2testbench/application/usecases/run_verification.py",
        ],
        "HARNESSES": [
            "spec2testbench/domain/entities/analysis_harness.py",
            "benchmarks_normalized/analogcoder_pro/*/harness_metadata.yaml",
        ],
        "MANUSCRIPT_CURRENT": [
            "paper_final/main.tex",
            "paper_final/sections/*.tex",
            "paper_final/tables/*.tex",
        ],
    }
    for group_name, patterns in pattern_groups.items():
        for pattern in patterns:
            for path in sorted(ROOT.glob(pattern)):
                if path.is_file():
                    groups.append((group_name, pattern, path))
    return groups


def write_baseline_version() -> dict[str, object]:
    version_payload = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "branch": git_output("branch", "--show-current"),
        "head": git_output("rev-parse", "HEAD"),
        "status_short": git_output("status", "--short"),
        "status_branch": git_output("status", "--short", "--branch").splitlines()[:1],
        "last_commit": git_output("log", "-1", "--oneline"),
        "worktree_dirty": bool(git_output("status", "--short")),
        "expected_starting_commit": "ae3b359918b64b1c42dec20fe5670ba18b4859a4",
    }
    BASELINE_VERSION_JSON.write_text(json.dumps(version_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return version_payload


def write_hash_inventory(paths: list[tuple[str, str, Path]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    with BASELINE_HASHES_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "group",
                "pattern",
                "relative_path",
                "sha256",
                "size_bytes",
            ],
        )
        writer.writeheader()
        for group_name, pattern, path in paths:
            writer.writerow(
                {
                    "group": group_name,
                    "pattern": pattern,
                    "relative_path": path.relative_to(ROOT).as_posix(),
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
            )
            counts[group_name] = counts.get(group_name, 0) + 1
    return counts


def write_status_report(version_payload: dict[str, object], counts: dict[str, int]) -> None:
    tracked_groups = [
        "ACP28_ORIGINAL_CIRCUITS",
        "ACP28_NORMALIZED_CORPUS",
        "FROZEN_PILOT_V3",
        "KNOWLEDGE_BASE",
        "LLM_PROMPTS",
        "PYDANTIC_MODELS",
        "CHECKER",
        "HARNESSES",
        "MANUSCRIPT_CURRENT",
    ]
    missing_groups = [group_name for group_name in tracked_groups if counts.get(group_name, 0) == 0]
    lines = [
        "# Final Implementation Baseline Status",
        "",
        f"- Captured at: `{version_payload['captured_at_utc']}`",
        f"- Branch: `{version_payload['branch']}`",
        f"- HEAD: `{version_payload['head']}`",
        f"- Last commit: `{version_payload['last_commit']}`",
        f"- Expected starting commit matched: `{str(version_payload['head'] == version_payload['expected_starting_commit']).lower()}`",
        f"- Worktree dirty at capture: `{str(version_payload['worktree_dirty']).lower()}`",
        "",
        "## Hash coverage",
        "",
    ]
    for group_name in tracked_groups:
        lines.append(f"- {group_name}: `{counts.get(group_name, 0)}` files hashed")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This baseline was captured from the current scientific worktree state before any new final-implementation outputs were generated.",
            "- A dirty worktree means the freeze reflects the exact current state, not a clean checkout.",
        ]
    )
    if missing_groups:
        lines.extend(
            [
                "- The following required populations were not present in the current worktree and could not be hashed:",
                *[f"  - {group_name}" for group_name in missing_groups],
            ]
        )
    BASELINE_STATUS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    version_payload = write_baseline_version()
    paths = collect_paths()
    counts = write_hash_inventory(paths)
    write_status_report(version_payload, counts)


if __name__ == "__main__":
    main()
