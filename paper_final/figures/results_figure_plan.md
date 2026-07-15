# Results Figure Plan

## Goal

Design one main results figure for the manuscript that visually answers RQ1--RQ3 without overstating RQ4. The figure must highlight that real execution, simulability/compliance separation, and controlled-violation sensitivity are different evidentiary layers.

## Recommended Structure

Use a three-panel horizontal layout:

1. `Panel A - Real Execution Coverage`
2. `Panel B - Simulability vs Compliance`
3. `Panel C - Controlled-Violation Datasets`

Do not include an LLM quantitative panel, because the canonical ablation results are pending.

## Panel A - Real Execution Coverage

Show a compact bar or annotated summary block for the canonical nominal campaign:

- 28 circuits
- 28 REAL runs
- 0 mock
- 28 successful executions
- 28 scientifically eligible results

Add a small annotation that extracted evidence spans DC, AC, transient, and spectral families. The panel should visually communicate execution breadth only, not compliance.

## Panel B - Simulability vs Compliance

Use a two-class stacked bar or a simple confusion-style block:

- `SIMULABLE_COMPLIANT = 27`
- `SIMULABLE_NONCOMPLIANT = 1`

Add a highlighted callout for `p04_amplifier` with exactly these fields:

- execution: `SUCCESS`
- mode: `REAL`
- metric: `dc_gain_db`
- value: `-160.0000000868589 dB`
- threshold: `>= 0.0 dB`
- verdict: `SIMULABLE_NONCOMPLIANT`

Place the equation `SIMULABLE != COMPLIANT` inside or immediately below this panel.

## Panel C - Controlled-Violation Datasets

This panel must show that there are two distinct retained datasets and that they cannot be silently merged.

Use side-by-side summary cards or bars:

Card 1: `Frozen pilot V3`
- 16 cases
- TRUE_ACCEPT = 8
- TRUE_DETECTION = 8
- FALSE_ACCEPT = 0
- FALSE_REJECT = 0
- UNEVALUATED = 0

Card 2: `Expanded controlled campaign`
- run id `20260712_195226`
- 30 generated variants
- 2 effective controlled violations
- 1 detected effective violation
- 1 false accept
- 0 unevaluated effective violations

Add a visible note: `Do not merge these counts into one confusion matrix.`

## RQ4 Handling

Do not create a quantitative LLM results panel.

Instead, add a narrow footer note or unobtrusive side label:

- `RQ4 quantitative ablation pending`
- `results/final_ablation_summary.json: PARTIAL`

This note must not look like a missing plot due to an error; it should look like an intentional pending-results placeholder.

## Caption Intent

The caption should explain that the canonical evidence supports three distinct conclusions: full real execution coverage on the nominal benchmark-aligned campaign, one demonstrative separation between simulability and compliance in `p04_amplifier`, and a controlled-violation story that differs between the frozen pilot V3 and the later expanded campaign.

## Forbidden Visual Implications

The figure must not imply:

- that successful execution means compliance
- that the expanded controlled campaign achieved zero false accepts
- that an LLM ablation was completed
- that software test counts are analog-verdict counts
- that the pilot V3 and expanded campaign are one homogeneous experiment
