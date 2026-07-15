# Framework Architecture Figure Specification

## Purpose

Generate one architecture figure for the manuscript section `Framework and Methods`. The figure must explain the end-to-end verification chain of Spec2Testbench without implying unsupported industrial scope, completed robustness, or LLM control over the final decision.

## Required Message

The figure must show that Spec2Testbench transforms a frozen YAML specification into an executable verification plan, runs a real ngspice simulation, extracts finite evidence through native backends, applies deterministic checking, and emits a traceable report with separated statuses. It must visually emphasize that simulability and compliance are distinct outcomes.

## Layout

Use a left-to-right pipeline with three horizontal layers:

1. `Specification and Planning`
2. `Execution and Extraction`
3. `Decision and Reporting`

Place the main pipeline in the center and use short side callouts only where needed for constraints or boundaries. Avoid dense paragraphs inside the figure.

## Main Blocks in Order

The central pipeline must contain exactly these ten blocks in this order:

1. `YAML Specification Parser`
2. `Specification Normalizer`
3. `Verification Planner`
4. `Deterministic or LLM-Assisted Testbench Generator`
5. `ngspice Execution Backend`
6. `Result Backend`
7. `Metric Extractor`
8. `Specification Checker`
9. `Status Classifier`
10. `Report and Provenance Layer`

## Inputs and Outputs

Show the following inputs entering the first half of the pipeline:

- `Benchmark circuit netlist`
- `Frozen YAML specification`

Show the following outputs leaving the final block:

- `Metric traces`
- `Separated statuses`
- `Machine-readable report`
- `Provenance record`

## Internal Annotations

Annotate the `Result Backend` block with two sublabels:

- `NGSPICE_MEASURE`
- `NGSPICE_WRDATA`

Annotate the `Status Classifier` block with the separated status taxonomy:

- `Execution status`
- `Simulation mode`
- `Compliance status`
- `Robustness status`
- `Scientific category`

## LLM Boundary Callout

Add one clearly separated callout near the `Deterministic or LLM-Assisted Testbench Generator` block.

The callout must say that the LLM may propose:

- analysis form
- stimulus formulation
- measurement directives
- testbench wording

The callout must also say that the LLM does not modify:

- benchmark circuit
- specification
- thresholds
- backend routing
- checker
- final decision

Visually separate this callout from the deterministic decision path so the figure cannot be read as if the LLM decides compliance.

## Anti-False-PASS Callouts

Add a compact boxed annotation below the extraction and decision part of the pipeline labeled `Anti-false-PASS controls`.

It must list these mechanisms exactly:

- `Missing measure != zero`
- `NOT_EVALUATED instead of injected value`
- `Oscillation validated before frequency acceptance`
- `Controlled override tracking`
- `Mock simulation not scientifically eligible`
- `Provenance preserved for every evaluated case`

## Evidence and Scope Notes

Add a small note at the bottom of the figure:

- `Canonical manuscript evidence uses real ngspice execution.`
- `Native extraction is validated for NGSPICE_MEASURE and NGSPICE_WRDATA.`
- `Robustness and full industrial PVT validation are not claimed in this figure.`

## Visual Style

Use a clean scientific style suitable for `IEEEtran`.

- White background.
- Dark text.
- One restrained accent color for the planning layer, one for the execution layer, and one for the decision layer.
- Thin arrows.
- No decorative icons that suggest fabrication, certification, or industrial sign-off.

## Forbidden Implications

The figure must not imply:

- post-layout validation
- industrial PVT closure
- regulatory certification
- LLM control over the compliance verdict
- circuit mutation during nominal benchmark evaluation

## Caption Intent

The final caption should communicate that the figure shows a traceable specification-to-evidence pipeline in which real ngspice execution, native extraction, deterministic checking, and separated statuses prevent simulability from being mistaken for compliance.
