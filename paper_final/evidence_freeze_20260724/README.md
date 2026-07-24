# Paper Evidence Freeze 2026-07-24

- Freeze id: `evidence_freeze_20260724`
- Git commit: `0db963312862e747ad2f8fdc039313861e9bf8ba`
- Workflow authority: `public_cli_verify`
- Replay entrypoint: `python reproduce_paper.py`
- Public workflow: `spec2testbench verify --no-llm` with `SPEC2TESTBENCH_DISABLE_PYSPICE=1`
- Cases: 28
- REAL runs: 28
- Successful executions: 28
- Scientifically eligible: 28
- SIMULABLE_COMPLIANT: 16
- SIMULABLE_NONCOMPLIANT: 2
- UNEVALUATED: 10
- Noncompliant cases: p04_amplifier, p23_oscillator
- Not evaluated cases: p02_amplifier, p08_currentmirror, p11_highpass, p13_bandstop, p16_opamp, p17_currentmirror, p18_opamp, p20_opamp, p21_opamp, p22_oscillator
