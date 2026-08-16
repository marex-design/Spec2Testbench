# Spec2Testbench Specification YAML v2.0

The v2 schema is the canonical format for reproducible benchmark specifications. It is intentionally stricter than the legacy YAML format.

## Design rules

1. `schema_version` is always `"2.0"`.
2. Every benchmark case has a stable `case_id`.
3. `provenance` records the upstream benchmark, task, checker summary, DUT path, and DUT SHA-256.
4. `ports` separates signal inputs, outputs, differential roles, supplies, bias and references.
5. `stimuli` describes only test excitation; it does not silently rewrite the DUT.
6. `analyses` declares every OP/DC/AC/TRAN/FFT protocol needed by the requirements.
7. `functional_requirements` is the scientific contract. Each mandatory criterion states its source, operator, threshold, unit, equivalence level, and implementation status.
8. `performance_targets` contains only metrics that Spec2Testbench can ask the runtime to measure. Diagnostic metrics must set `diagnostic_only: true` and must not create a conformity proof.
9. `verification.immutable_dut: true` is mandatory for ACP-28.
10. A mandatory criterion that cannot yet be measured is written as `implementation_status: metadata_only`; it is never deleted and never silently counted as PASS.
11. `require_full_contract_for_compliance: true` means COMPLIANT is possible only when all mandatory requirements have valid evidence and pass.
12. Any unknown field is rejected by the strict Pydantic/JSON schema.

## Canonical structure

```yaml
schema_version: '2.0'
case_id: acp28-p10
name: analogcoder_pro_p10_lowpass
circuit_type: low_pass_filter
technology: AnalogCoder-Pro generic Level-1 benchmark models
description: a passive low-pass filter

provenance:
  benchmark: AnalogCoder-Pro
  benchmark_subset: ACP-28
  upstream_repository: https://github.com/laiyao1/AnalogCoderPro
  upstream_task_id: 10
  upstream_level: Hard
  upstream_type: LowPass
  upstream_submodule_name: LowPass
  upstream_task_description: a passive low-pass filter
  upstream_testbench_description: NA
  official_checker:
    path: problem_check/LowPass.py
    criterion_summary: []
    upstream_mutates_dut: false
  dut:
    path: benchmark/analogcoder_pro/p10_lowpass.cir
    sha256: '<64 hex characters>'
    canonicalization: Embedded analyses/output directives externalized; topology and values preserved.
    topology_and_values_preserved: true

ports:
  input: [Vin]
  output: [Vout]
  differential_positive: []
  differential_negative: []
  common_mode: []
  supply_positive: [Vdd]
  supply_negative: ['0']
  bias: []
  reference: []
  loop_break: []
  loop_injection: []
  current_probe: []

operating_conditions:
  nominal_temperature: 25.0
  nominal_supply: 5.0
  process_corner: tt

stimuli: []
analyses: []
functional_requirements: []
performance_targets: {}
input_conditions: {}
measurement:
  backend: AUTO
  allow_fallback: true
verification:
  auto_select: true
  include_tests: []
  exclude_tests: []
  required_policy: all
  immutable_dut: true
  not_evaluated_on_missing_mandatory_metric: true
  require_full_contract_for_compliance: true
test_requirements: {}
test_categories: []
pvt_config:
  corners: [tt]
  temperature_range: commercial
  supply_variation: 0.0
```

Use the real validated example in `examples/specification_v2_example.yaml` rather than copying placeholder hashes from this documentation.

## Validation

```powershell
spec2testbench spec-lint --specs benchmark/analogcoder_pro/specs
```

Machine-readable JSON Schema:

`schemas/specification-v2.schema.json`

## PASS / FAIL / NOT_EVALUATED

For the strict benchmark policy:

- **PASS / COMPLIANT**: every mandatory contract criterion is evaluated and passes.
- **FAIL / NONCOMPLIANT**: at least one mandatory criterion has valid evidence and fails.
- **NOT_EVALUATED**: no mandatory failure is demonstrated, but at least one mandatory criterion lacks valid evidence, or simulation did not complete.

This rule deliberately prevents missing evidence from inflating the compliance rate.
