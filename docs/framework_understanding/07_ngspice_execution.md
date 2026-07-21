# Phase 7 - ngspice Execution

## Which simulator path is real?

Observed fact:
- `VerificationPipeline._run_simulation_with_ngspice()` instantiates `PySpiceSimulator`, not `NgspiceSimulator`.

Interpretation:
- `spec2testbench/infrastructure/simulator/ngspice_simulator.py` is a simpler or older adapter, not the main canonical execution path.

## Documented execution behavior from inspected code

1. ngspice executable localization
   - settings expose `ngspice_path`
   - pipeline uses `PySpiceSimulator.is_available`
   - `run_verification.py` also has fallback version detection via `shutil.which(...)`

2. command construction
   - paper-campaign artifacts persist a simplified command template:
   - `ngspice -b -r <raw_file> testbench.cir`
   - exact temp-path-resolved command is not preserved in the artifact examined.

3. Windows path handling
   - repository clearly targets Windows in multiple places
   - artifact provenance for `p04` shows Windows platform
   - included netlist path in persisted `testbench.cir` is an absolute Windows path

4. temporary files
   - temporary/result/raw files are implied by simulator/backend architecture
   - campaign script persists selected evidence afterward

5. stdout/stderr capture
   - `VerificationReport` stores `simulation_logs` and `simulation_errors`
   - campaign script writes them to `stdout.txt` and `stderr.txt`

6. timeouts
   - `VerificationPipeline` accepts `timeout_seconds`
   - statuses include `TIMEOUT`
   - tests explicitly validate timeout classification

7. return codes
   - `VerificationReport` stores `ngspice_returncode`
   - integration tests expect `report.ngspice_returncode == 0`

8. convergence / execution error classification
   - non-successful runs become `ExecutionStatus.ERROR` or `TIMEOUT`
   - tests check examples like `"singular matrix"` and missing structured result file

9. `REAL` vs `MOCK`
   - `SimulationMode` has `REAL`, `MOCK`, `RECOVERED`
   - if no netlist exists, mock execution is allowed only when configured
   - mock results are not paper-eligible

10. PySpice enabled/disabled
   - provenance stores `pyspice_required`
   - integration tests expect `pyspice_required is False` in real pipeline evidence
   - repository contains tests about operation without PySpice-specific dependence

11. continuing without PySpice
   - strong evidence exists that the framework can still reason using structured backends and result parsing rather than requiring PySpice metrics only

12. version information
   - provenance attempts to record:
     - framework version
     - git commit
     - python version
     - ngspice version
     - PySpice version
     - operating system

## Limitations observed

- The exact resolved ngspice command line is not preserved verbatim in the examined campaign artifact.
- `p04` provenance had `ngspice_version: null`, while integration tests expect a populated version string in successful environments.

## Architectural reading

Fact observed:
- execution is treated as a scientific evidence event with explicit provenance and eligibility status.

Interpretation:
- this is one of the stronger parts of the implementation, although command capture could be more exact.
