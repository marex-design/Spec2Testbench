# Paper-Eligible Results Policy

A result is paper eligible only when:

- `simulation_mode` is `REAL` or accepted `RECOVERED`;
- `execution_status` is `SUCCESS`;
- `simulation_mode` is not `MOCK`;
- the result was generated under `configs/paper_experiment.yaml`;
- the circuit artifact directory contains the specification, netlist, generated
  testbench, logs, metric trace, report, and provenance.

Mock results are development artifacts. They must not be counted in scientific
aggregations, paper tables, or claims about circuit behavior.

Archived pre-consolidation artifacts are stored in `archive/pre_consolidation`
and must not be mixed with the current paper campaign.
