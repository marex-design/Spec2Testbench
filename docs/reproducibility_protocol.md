# Reproducibility Protocol

1. Install the package and dependencies.
2. Ensure `ngspice` is available on the execution path.
3. Run `pytest -q`.
4. Run `python scripts\run_paper_campaign.py`.
5. Inspect `results/paper_campaign_summary.json` for the `run_id` and global metrics.
6. Use only artifacts under the matching `artifacts/paper_campaign/<run_id>/` directory.

Each report includes provenance fields for:

- run id and timestamp;
- framework and Python versions when available;
- git commit;
- operating system;
- spec and netlist file paths;
- SHA-256 hashes for spec, netlist, and generated testbench;
- execution, simulation, compliance, robustness, and scientific statuses.

Unavailable provenance fields are recorded as `null`; they are not fabricated.
