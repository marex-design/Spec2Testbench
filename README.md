# Spec2Testbench v0.5.0

Spec2Testbench is a traceable specification-to-SPICE verification framework for analog circuits. The final research package focuses on one external circuit corpus only: **AnalogCoder-Pro ACP-28**.

## Scientific scope

- Preserve each ACP netlist as an immutable DUT and verify its SHA-256.
- Express ACP requirements in strict, uniform specification YAML v2 files.
- Generate deterministic or LLM-assisted testbench plans.
- Validate every LLM plan deterministically before execution.
- Execute ngspice and derive measured values only from simulator evidence.
- Retry only protocol/testbench failures; electrical non-compliance is terminal.
- Keep user thresholds and the DUT immutable through verification.
- Report coverage, compliance, false accepts/rejects, LLM quality, latency, tokens and inter-run stability.

## Primary CLI

```powershell
spec2testbench version
spec2testbench spec-lint --specs benchmark/analogcoder_pro/specs
spec2testbench verify --specs benchmark/analogcoder_pro/specs/p10_lowpass.yaml --netlist benchmark/analogcoder_pro/p10_lowpass.cir --no-llm --output results/p10
spec2testbench hybrid-verify --specs benchmark/analogcoder_pro/specs/p10_lowpass.yaml --netlist benchmark/analogcoder_pro/p10_lowpass.cir --provider deepseek --model $env:DEEPSEEK_MODEL --temperature 0.1 --top-p 1.0 --max-retries 3 --output results/p10_hybrid
spec2testbench acp-benchmark --manifest benchmark/analogcoder_pro/acp28_manifest.yaml --output results/acp28_compliance
```

## Research campaigns

The campaign drivers remain explicit scripts because they produce research datasets rather than a single user verification:

```powershell
python scripts/run_llm_fault_catalog.py --output results/llm_fault_catalog.json
python scripts/run_hybrid_feedback_campaign.py --manifest experiments/ground_truth/ground_truth_manifest.yaml --provider deepseek --model $env:DEEPSEEK_MODEL --temperature 0.1 --top-p 1.0 --trials 3 --max-retries 3 --output results/hybrid_ground_truth
python scripts/run_hybrid_feedback_campaign.py --manifest experiments/hybrid_feedback/acp28_manifest.yaml --provider deepseek --model $env:DEEPSEEK_MODEL --temperature 0.1 --top-p 1.0 --trials 3 --max-retries 3 --output results/hybrid_acp28
```

## ACP-28 corpus

`benchmark/analogcoder_pro/` contains exactly the retained ACP-28 DUT corpus, its uniform v2 specifications, the ACP manifest, and a snapshot of `problem_set.tsv`. No separate reference benchmark is bundled in v0.5.0.

The strict ACP contract currently contains **64 mandatory criteria**. **36 are directly executable by the current core** and **28 are preserved explicitly as `metadata_only`** rather than being silently converted into PASS. Twelve of the 28 circuits currently have a fully executable mandatory contract. The deterministic ACP runner therefore returns `NOT_EVALUATED` whenever complete mandatory evidence is unavailable.

This limitation is intentional and is recorded in `docs/FINAL_IMPLEMENTATION_AUDIT.md`; it must not be presented as full ACP functional coverage.

## Independent oracle and mutations

- `experiments/manual_oracle_subset/`: independent analytical/manual reference for p10/p11 nominal and non-compliant RC mutations.
- `experiments/ground_truth/ground_truth_manifest.yaml`: primary confusion-matrix oracle.
- `experiments/controlled_violations/`: 26 materialized controlled variants; every variant changes an active DUT line, has original/mutated SHA-256 and an effectiveness check.

The broader controlled-violation set is a stress set. Its detection rate must only be reported after real ngspice execution. The 10-case LLM-like fault catalog is deterministic guard coverage, not a spontaneous hallucination rate.

## Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,pyspice,llm]"
$env:NGSPICE_PATH=(Get-Command ngspice_con -ErrorAction Stop).Source
$env:DEEPSEEK_API_KEY="..."
$env:DEEPSEEK_MODEL="<exact model id>"
$env:DEEPSEEK_TOP_P="1.0"
```

A local `.env` is supported through the settings layer; shell variables are recommended for frozen experimental runs because they make the configuration explicit in the session log.

## Validation

Run local tests first:

```powershell
python -m pytest -q -m "not ngspice and not llm_live"
```

Then, on the machine with ngspice:

```powershell
python -m pytest -q
```

Live LLM evidence is intentionally opt-in and requires real provider credentials. Stub runs are never labelled scientific LLM evidence.

See `docs/FINAL_IMPLEMENTATION_AUDIT.md`, `docs/ACP28_BENCHMARK_PROTOCOL.md`, and `docs/hybrid_feedback_architecture.md` before producing thesis tables.
