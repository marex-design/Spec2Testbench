from __future__ import annotations

import json

from run_corrected_metric_semantics_campaign import audit_legacy_gain_references, ensure_workspace, precondition_check


def main() -> None:
    ensure_workspace()
    precondition_check()
    print(json.dumps(audit_legacy_gain_references(), indent=2))


if __name__ == "__main__":
    main()
