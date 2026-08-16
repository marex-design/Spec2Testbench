# ACP-28 conformity protocol

## Scientific question

Among the preserved circuit netlists produced for AnalogCoder-Pro tasks p01-p28, what proportion can Spec2Testbench evaluate and what proportion has a complete deterministic proof of functional conformity?

## Separation of responsibilities

- AnalogCoder-Pro: source/generator of the circuit DUT and original benchmark criterion.
- Spec2Testbench: independent specification-to-SPICE verification layer.
- ngspice: numerical simulation engine.
- LLM: **not used** for the primary ACP conformity rate. LLM experiments are a separate experiment about planning/recovery capability.

This prevents the quality of a second model from contaminating the first measurement of ACP DUT quality.

## Windows / PowerShell run book

```powershell
# 1. Environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,llm]"

# 2. Bind the ngspice executable used on Windows
$env:NGSPICE_PATH = (Get-Command ngspice_con -ErrorAction Stop).Source
& $env:NGSPICE_PATH --version

# 3. Validate all strict YAMLs before simulation
spec2testbench spec-lint --specs benchmark/analogcoder_pro/specs

# 4. Smoke test one DUT
spec2testbench acp-benchmark `
  --manifest benchmark/analogcoder_pro/acp28_manifest.yaml `
  --limit 1 `
  --output results/acp28_smoke

# 5. Full ACP-28 deterministic conformity campaign
spec2testbench acp-benchmark `
  --manifest benchmark/analogcoder_pro/acp28_manifest.yaml `
  --output results/acp28_compliance
```

`.env` is also supported by v0.5.0; explicitly set shell variables when you want the run configuration to be obvious in the experimental log.

## Read the aggregate results

```powershell
$S = Get-Content results/acp28_compliance/summary.json -Raw | ConvertFrom-Json
$S | Select-Object `
  circuits_total, simulation_success, evaluated, compliant, noncompliant, not_evaluated, `
  simulation_success_rate, evaluation_rate, compliance_rate_evaluated, `
  noncompliance_rate_evaluated, verified_compliance_yield, failure_to_evaluate_rate
```

## Read per-circuit results

```powershell
Import-Csv results/acp28_compliance/runs.csv |
  Select-Object case_id,type,execution_status,contract_status,contract_coverage,
                passed_mandatory_requirements,failed_mandatory_requirements,missing_mandatory_requirements |
  Format-Table -AutoSize
```

## Inspect why a circuit was not evaluated

```powershell
Import-Csv results/acp28_compliance/criteria.csv |
  Where-Object criterion_status -ne 'PASS' |
  Format-Table case_id,requirement_id,metric,implementation_status,criterion_status,measured_value,unit -AutoSize
```

## Interpretation

Do not report `simulation_success_rate` as conformity. A SPICE deck can run successfully while violating the functional contract.

Do not report `compliance_rate_evaluated` alone. Report it together with `evaluation_rate` and `verified_compliance_yield`.

A `NOT_EVALUATED` result is not a PASS and not a FAIL. It indicates insufficient scientific evidence under the strict contract.
