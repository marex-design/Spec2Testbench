# LLM TestbenchPlan Schema

The LLM never emits free-form SPICE. It emits a strict JSON object validated by Pydantic.

Top-level fields:

- `case_id`
- `analysis_type`
- `stimuli`
- `observed_nodes`
- `measurements`
- `simulation_parameters`
- `concise_rationale`

Important enums:

- `AnalysisType`: `OP`, `DC`, `AC`, `TRAN`
- `StimulusType`: `DC`, `AC`, `PULSE`, `SIN`, `PWL`, `TRIANGLE`
- `MeasurementBackendPreference`: `NGSPICE_MEASURE`, `NGSPICE_WRDATA`, `AUTO`

Key validation rules:

- No `NaN` or infinite values.
- No unknown nodes.
- No missing requested metrics.
- No unsupported units or incompatible analyses.
- No unsafe simulation ranges.
- No verdict leakage such as `PASS`, `FAIL`, `TRUE_ACCEPT`, or `FALSE_REJECT`.

Compilation remains deterministic after schema validation. The compiler, not the LLM, owns `.control`, `.measure`, `wrdata`, path quoting, and artifact naming.
