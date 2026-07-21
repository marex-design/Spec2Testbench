# Phase 6 - Specification to Test Mapping

## Mapping mechanism

Observed mapping chain:

1. YAML metric names enter `Specification.performance_targets`
2. `TestBenchGenerator._infer_categories_from_metrics()` chooses analysis categories
3. category-specific template builders create `Measurement` objects
4. simulator/native backend produces structured result containers
5. `MetricExtractor.extract()` maps metric names to extraction logic
6. `SpecChecker.verify_single_metric()` applies thresholds and units

## Supported metric families observed

| Metric | Analysis | Stimulus | Source signal | Extraction path | Canonical unit |
| --- | --- | --- | --- | --- | --- |
| `operating_point` / `vout_dc` | `dc`/`.OP` | DC bias | output | `MetricExtractor._extract_operating_point` | `V` |
| `quiescent_current` / `idd` | `dc` | DC bias | supply current | `_extract_current` | `A` |
| `power` | `dc` | DC bias | supply current and `vdd` | `_extract_power` | `W` |
| `dc_gain_db` / `dc_gain` | `ac` | AC source | `vout/vin` | `_extract_dc_gain` or native backend | `dB` |
| `bandwidth` / `cutoff_frequency_hz` | `ac` | AC source | AC transfer | `_extract_bandwidth` or WRDATA backend | `Hz` |
| `unity_gain_frequency` / `ugbw` | `ac` | AC source | AC transfer | `_extract_gbw` | `Hz` |
| `phase_margin` | `ac` | AC source | AC phase | `_extract_phase_margin` | `deg` |
| `slew_rate` | `tran` | pulse | `vout(t)` | `_extract_slew_rate` | `V/s` |
| `settling_time` | `tran` | pulse | `vout(t)` | `_extract_settling_time` | `s` |
| `propagation_delay` | `tran` | pulse | input/output transition | `_extract_propagation_delay` | `s` |
| `v_t_plus` | `tran` | pulse/ramp-like | schmitt threshold | `_extract_v_t_plus` | `V` |
| `v_t_minus` | `tran` | pulse/ramp-like | schmitt threshold | `_extract_v_t_minus` | `V` |
| `hysteresis_width` | `tran` | pulse/ramp-like | threshold difference | `_extract_hysteresis_width` | `V` |
| `frequency_hz` / `oscillator_frequency` | `tran` or `fourier` | none or sinusoid | oscillation output | `_extract_frequency` or WRDATA backend | `Hz` |
| `startup_amplitude` | `tran` | none for oscillator | output envelope | `_extract_startup_amplitude` | `V` |
| `thd_percent` / `thd` | `fourier` | sinusoid or self-oscillation | harmonic magnitudes | `_extract_thd` | `%` |
| `pvt_*_variation` | `pvt` | category-specific | PVT summary | `_extract_pvt_metric` or direct lookup | varies |

## Operators observed

- supported threshold patterns:
  - `min`
  - `max`
  - `min` + `max`
- effective operators:
  - `>=`
  - `<=`
  - range

## Missing-measure behavior

Observed behavior:

- missing metric becomes `Verdict.ERROR`
- run-level compliance becomes `NOT_EVALUATED` if a required nominal metric is missing
- this is reinforced by tests such as `test_missing_measure_does_not_fall_back_to_synthetic_zero`

## Metrics explicitly observed in code

Present in generator, extractor, or backend logic:

- `dc_gain_db`
- `bandwidth`
- `unity_gain_frequency`
- `phase_margin`
- `quiescent_current`
- `power`
- `propagation_delay`
- `slew_rate`
- `settling_time`
- `frequency_hz`
- `startup_amplitude`
- `hysteresis_width`
- `thd_percent`

## Metrics mentioned in prompt but only partially evidenced

- supply current: yes, via `quiescent_current` and `idd`
- quiescent power: yes, via `power`
- rise time: not directly observed as a supported named metric
- oscillation frequency: yes
- hysteresis: yes
- THD: yes

## Architectural reading

Fact observed:
- The mapping logic is implemented, but spread across generator aliases, metric aliases, and backend-specific extractor tables.

Interpretation:
- adding a new metric currently requires coordinated edits in multiple layers rather than one declarative registry.
