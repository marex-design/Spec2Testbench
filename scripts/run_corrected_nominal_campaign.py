from __future__ import annotations

import json

from run_corrected_metric_semantics_campaign import ensure_workspace, precondition_check, run_nominal_campaign


def main() -> None:
    ensure_workspace()
    precondition_check()
    print(json.dumps(run_nominal_campaign(), indent=2))


if __name__ == "__main__":
    main()
