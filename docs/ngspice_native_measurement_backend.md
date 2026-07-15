# Ngspice Native Measurement Backend

Spec2Testbench can now extract real simulation results without requiring PySpice raw parsing.

## Backends

- `NGSPICE_MEASURE`: parses native ngspice `.measure` outputs from `measures.txt`.
- `NGSPICE_WRDATA`: parses ASCII numeric vectors exported by `wrdata`.
- `PYSPICE`: optional fallback when PySpice raw parsing is available.

## Current Supported Metrics

- `.measure`: `operating_point`, `vout_dc`, `quiescent_current`, `idd`, `power`, `dc_gain_db`, `cutoff_frequency_hz`, `bandwidth`, `startup_amplitude`, `propagation_delay`, `propagation_delay_s`
- `wrdata`: `dc_gain_db`, `cutoff_frequency_hz`, `bandwidth`, `amplitude_pp`, `frequency_hz`, `oscillator_frequency`, `switching_threshold_rising_v`, `switching_threshold_falling_v`, `hysteresis_width_v`

## Output Artifacts

Each native extraction pass emits:

- `ngspice_stdout.txt`
- `ngspice_stderr.txt`
- `measures.txt`
- `vectors.dat`
- `vectors.csv`
- `vector_metadata.json`

## Failure Semantics

- missing or failed native measures become `NOT_EVALUATED`
- missing vector files become `NOT_EVALUATED`
- no artificial zero values are injected
- PySpice absence no longer blocks real campaigns
