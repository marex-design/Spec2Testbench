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

Expected future structure:
- `manifest.csv`: benchmark inventory and metadata
- `netlists/`: SPICE netlists or extracted subcircuits
- `specs/`: benchmark-aligned YAML specifications
- `notes/`: source provenance, assumptions, and references
