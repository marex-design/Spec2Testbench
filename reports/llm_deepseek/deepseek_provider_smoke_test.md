# DeepSeek Provider Smoke Test

- Date: 2026-07-21
- Provider: stub
- Model: deepseek-stub-v1
- Case: smoke_p10_lowpass
- Plan validation: VALID
- Repairs attempted: 0
- Compiled testbench: yes
- Real ngspice execution: yes
- Execution status: SUCCESS
- Measurement backend: NGSPICE_WRDATA
- Compliance status: PASS

## Parsed Plan
```json
{
  "case_id": "smoke_p10_lowpass",
  "analysis_type": "AC",
  "stimuli": [
    {
      "source_name": "vin",
      "target_node": "Vin",
      "stimulus_type": "AC",
      "parameters": {
        "magnitude": 1.0,
        "dc_value": 2.5
      }
    }
  ],
  "observed_nodes": [
    "Vout"
  ],
  "measurements": [
    {
      "metric_name": "cutoff_frequency_hz",
      "analysis_type": "AC",
      "input_node": "Vin",
      "output_node": "Vout",
      "expected_unit": "Hz",
      "backend_preference": "NGSPICE_WRDATA",
      "measurement_parameters": {}
    }
  ],
  "simulation_parameters": {
    "start_time_s": null,
    "stop_time_s": null,
    "time_step_s": null,
    "dc_source": null,
    "dc_start": null,
    "dc_stop": null,
    "dc_step": null,
    "frequency_start_hz": 1.0,
    "frequency_stop_hz": 1000000000.0,
    "points_per_decade": 20
  },
  "concise_rationale": "Deterministic stub provider generated a netlist-aware JSON TestbenchPlan."
}
```