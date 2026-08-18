# LLM Evaluation Protocol

## Goal

Measure the incremental value of the LLM over the deterministic baseline without changing the simulator, parser, or checker.

## Comparison Modes

- `Baseline`: `use_llm=False`
- `LLM-assisted`: `use_llm=True`

The two modes must share:

- the same benchmark netlist
- the same benchmark-aligned specification
- the same `ngspice` execution path
- the same metric extractor
- the same verdict logic

## Selected First Cases

The first paper-ready comparison subset should cover all major families while staying small enough for repeated runs.

1. `voltage_reference`
2. `current_mirror`
3. `lowpass_filter`
4. `bandpass_filter`
5. `two_stage_opamp`
6. `comparator`
7. `ring_oscillator`
8. `relaxation_oscillator`

## What the LLM Is Allowed To Change

The LLM is evaluated only on testbench generation decisions:

- test category selection
- stimulus choice
- analysis choice
- measurement definitions
- node targeting inside the generated testbench

The LLM is not allowed to change:

- the benchmark netlist
- the post-processing parser
- the spec checker thresholds

## Primary Metrics

For each case and mode, report:

- `testbench_generation_success`
- `simulation_success`
- `overall_verdict`
- `success_rate`
- `measurement_count`
- `failed_metric_count`
- `plausibility_score` when available from campaign data

## Secondary Diagnostic Metrics

- generated measurement names
- generated analysis types
- generated stimulus types
- execution time
- error message if generation or simulation fails

## Fairness Rules

- run baseline and LLM modes on the same machine
- keep the same netlist and spec file
- keep the same warning margin
- keep the same provider/model during one comparison batch
- if the LLM run fails because of API/network/configuration, mark it as `SKIPPED`, not `FAIL`

## Paper Narrative

The baseline demonstrates that the framework is already executable and measurable without any model assistance.

The LLM evaluation should then answer one narrow question:

`Does the LLM improve testbench adequacy and metric coverage over the deterministic baseline on representative analog topologies?`

This keeps the contribution falsifiable and easy to defend.
