from __future__ import annotations

import json

from run_corrected_metric_semantics_campaign import (
    ensure_workspace,
    precondition_check,
    revalidate_gain_mutations,
    run_baseline_replay,
    run_frozen_replay,
    run_nominal_campaign,
)


def main() -> None:
    ensure_workspace()
    precondition_check()
    nominal = run_nominal_campaign()
    run_frozen_replay()
    revalidate_gain_mutations(nominal)
    print(json.dumps(run_baseline_replay(), indent=2))


if __name__ == "__main__":
    main()
