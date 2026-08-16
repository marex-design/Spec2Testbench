# Controlled Violation Protocol

Each violation mutates exactly one component or directive in a copied netlist. The copied specification remains unchanged so violations are measured against the original requirement. Runs use `SimulationMode=REAL`, `allow_mock=false`, and paper eligibility is recorded for every case.

Classification maps pre-execution ground truth to framework statuses: TRUE_FAIL, FALSE_PASS, TRUE_NON_SIMULABLE, and related diagnostic classes.
