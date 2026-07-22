# SPICE Knowledge Architecture

This knowledge repository was generated for `knowledge_stub_v1`.

It separates four layers:

- `knowledge/spice_core/`: portable SPICE and compiler-owned structural rules.
- `knowledge/ngspice/`: rules confirmed on the installed ngspice executable.
- `knowledge/spec2testbench/`: local scientific invariants, recipes, and policies.
- `knowledge/validated_examples/`: safe generic examples with leakage checks.

Only rules with validation status `CONFIRMED_PORTABLE`, `CONFIRMED_NGSPICE_INSTALLED`, or `CONFIRMED_SPEC2TESTBENCH` are exposed to retrieval.