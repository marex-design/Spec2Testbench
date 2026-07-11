# Remaining Scientific Risks

- The campaign produced real ngspice executions, but the wrapper still deletes
  temporary raw files after parsing. Raw-file retention should be completed
  before final submission.
- `ngspice_version` is recorded as `null` because version probing blocked on
  this Windows environment when called from Python.
- PySpice is not available for parsing, so the simulator uses the fallback raw
  parser.
- Robustness status is `NOT_EVALUATED` for the nominal 28-circuit campaign.
- The campaign found one simulable but non-compliant circuit, `p04_amplifier`;
  this is scientifically useful, but it should be manually inspected before
  publication.
- LLM behavior remains exploratory and is not evidence for the main paper.
