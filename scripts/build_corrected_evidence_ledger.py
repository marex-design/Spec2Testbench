from __future__ import annotations

import json

from run_corrected_metric_semantics_campaign import build_evidence_ledger, ensure_workspace


def main() -> None:
    ensure_workspace()
    print(json.dumps(build_evidence_ledger(), indent=2))


if __name__ == "__main__":
    main()
