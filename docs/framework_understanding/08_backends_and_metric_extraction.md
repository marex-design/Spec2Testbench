# Phase 8 - Backends and Metric Extraction

## Backends observed

### `NGSPICE_MEASURE`

- Definition: `NgspiceMeasureBackend` in `infrastructure/simulator/result_backends.py`
- Input files:
  - `measures_file`
- Output format:
  - parsed lines matching `name = value`
- Parser:
  - `parse_measure_file()`
- Error handling:
  - missing file -> empty parse
  - `failed` / `not found` -> `NOT_EVALUATED`
  - NaN/Inf -> `NON_FINITE_MEASURE`
  - unparsable -> `UNPARSABLE_MEASURE`
- Compatible metrics:
  - generic named measure metrics, depending on simulator-produced measure names

### `NGSPICE_WRDATA`

- Definition: `NgspiceWrdataBackend`
- Input files:
  - `vectors_file`
- Output format:
  - whitespace-separated numeric matrix
- Parser:
  - `parse_wrdata_file()`
- Error handling:
  - missing, empty, unparsable, non-finite, or ragged-column files become backend errors
- Known extractor functions:
  - `compute_amplitude_pp`
  - `compute_startup_amplitude`
  - `compute_frequency_hz`
  - switching thresholds and hysteresis
  - `compute_dc_gain_db`
  - `compute_cutoff_frequency`

## How waveform becomes metric

Observed chain:

1. ngspice writes either named measures or numeric vector data
2. backend parses file into structured arrays or scalar map
3. backend extractor computes domain value
4. `MetricExtractor` performs higher-level lookup/fallback across result containers
5. `SpecChecker` normalizes units and compares against thresholds

## NaN/infinite handling

Observed safeguards:

- measure parser rejects NaN and Inf
- WRDATA parser rejects NaN and Inf
- checker refuses incompatible unit conversion

## Oscillator handling

Two paths are visible:

- WRDATA/backend path:
  - `compute_frequency_hz()` uses mean crossing analysis over waveform samples
- higher-level metric path:
  - `MetricExtractor._extract_frequency()` also uses mean-crossing periods
  - but only if `oscillation_validation.status` is `None` or `VALID_OSCILLATION`

Observed implications:

- amplitude-too-low or invalid oscillation states block frequency reporting
- tests explicitly confirm non-oscillating variants become `NOT_EVALUATED`

## Limits observed

- Metric extraction is implemented in multiple places:
  - backend scalar/vector extraction
  - higher-level `MetricExtractor`
- This improves flexibility but creates duplication risk.
