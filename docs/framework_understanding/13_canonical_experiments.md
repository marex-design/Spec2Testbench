# Phase 13 - Canonical Experiments

## Confirmed canonical paper campaign

- Runner: `scripts/run_paper_campaign.py`
- Summary artifact: `results/paper_campaign_summary.json`
- Artifact root: `artifacts/paper_campaign/20260711_094959/`

## Confirmed counts from inspected artifact

From `results/paper_campaign_summary.json`:

- 28 circuits total
- 28/28 `simulation_mode = REAL`
- 28/28 `execution_status = SUCCESS`
- 27 `SIMULABLE_COMPLIANT`
- 1 `SIMULABLE_NONCOMPLIANT`
- the noncompliant case is `p04_amplifier`

These counts are directly confirmed by the file and should be preferred over any prose claim.

## Other experiment families observed

- Frozen pilot:
  - `experiments/frozen_pilot_v2/`
  - `experiments/frozen_pilot_v3/`
- Controlled violations:
  - `experiments/controlled_violations/`
- Ground truth:
  - `experiments/ground_truth/`
- Native backend validation:
  - `artifacts/full_ngspice_native_validation/`
  - `scripts/generate_full_ngspice_native_validation.py`
  - `scripts/validate_ngspice_native_extraction.py`

## Claims not confirmed in this pass

The following numbers were requested, but I did not find a single inspected artifact in this pass that conclusively proves all of them together:

- `8 true accepts`
- `8 true detections`
- `30 mutations`
- `2 effective violations`
- `1 detected`
- `1 missed`
- `66 tests passed`

Interpretation:
- these may well be derivable from `experiments/controlled_violations/`, `ground_truth`, and test execution, but they were not fully reconstructed in this documentation pass without running the full supporting analysis.

## Architectural reading

Fact observed:
- the paper campaign counts for the nominal ACP-28 run are directly supported by repository artifacts.

Interpretation:
- the repository is in relatively good shape for reproducible nominal campaign auditing, but secondary mutation/forensics claims require additional focused reconstruction.
