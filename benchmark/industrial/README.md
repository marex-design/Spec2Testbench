# Industrial-Style Benchmark Extension

This folder is reserved for a harder benchmark tier intended to complement the
pedagogical 28-case AnalogCoder-Pro benchmark with more industry-representative
analog and mixed-signal building blocks.

Recommended first PDK:
- `sky130`

Why `sky130` first:
- Most mature open-source PDK ecosystem
- Widely documented in academic and open-hardware projects
- Practical for both SPICE-level simulation and future layout-aware extension
- Easier to justify in a reproducible research paper than a proprietary PDK

Suggested second-stage PDKs after `sky130`:
- `gf180mcu`
- `ihp-sg13g2`

Benchmark design goals:
- Multi-stage analog blocks
- Real biasing and feedback structures
- More realistic transistor counts than the current pedagogical benchmark
- Native support for nominal and PVT evaluation

Current first executable subset:
- `ind01_two_stage_ota`
- `ind06_strongarm_comparator`
- `ind08_charge_pump`
- `ind09_ring_vco`

Additional files used by this subset:
- `models/sky130_tt.spice`: local bridge file pointing to a user-installed SKY130 model library

Current structure:
- `manifest.csv`: benchmark inventory and metadata
- `models/`: local PDK bridge files
- `netlists/`: SKY130-oriented benchmark netlists
- `specs/`: benchmark-aligned YAML specifications
- `notes/`: provenance, assumptions, and benchmark notes

How to activate real SKY130 simulation:
1. Edit `models/sky130_tt.spice` to point to your local SKY130 `.lib` file.
2. Run `python scripts/run_industrial_sky130_campaign.py`.
