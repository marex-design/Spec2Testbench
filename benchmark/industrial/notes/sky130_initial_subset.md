# SKY130 Initial Industrial Subset

This initial subset turns the former industrial scaffold into a benchmark tier
that is compatible with the current Spec2Testbench flow.

Included first-wave cases:

- `ind01_two_stage_ota`
- `ind06_strongarm_comparator`
- `ind08_charge_pump`
- `ind09_ring_vco`

Why this subset was chosen:

- all four cases map to circuit types already supported by the framework
- they cover multiple verification families already exercised in the paper
- they increase credibility beyond the purely pedagogical AnalogCoder-Pro set
- they remain manageable before introducing a full industrial benchmark

Current limitation:

- the repository does not ship the SKY130 PDK itself
- users must edit `benchmark/industrial/models/sky130_tt.spice` to point to a
  local SKY130 model library before real ngspice execution can succeed

Expected next step:

- add `ff` and `ss` bridge files
- extend the subset toward a bandgap reference and an LDO benchmark
- produce a dedicated industrial-results table for the paper
