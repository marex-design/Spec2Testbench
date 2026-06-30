# SKY130 Model Bridge

This folder is reserved for local SKY130 SPICE model bridge files used by the
industrial benchmark.

Expected workflow:

1. Install or clone a local SKY130 PDK distribution.
2. Edit `sky130_tt.spice` so that its `.lib` line points to your local SKY130
   transistor model library.
3. Reuse the same pattern for additional corners such as `ff` and `ss` if you
   later want fuller PVT support.

Why a bridge file is used:

- The benchmark netlists can keep stable repo-local include paths.
- The actual PDK installation path remains local and is not hard-coded into the
  repository.
- The simulator now rewrites relative `.include` and `.lib` paths to absolute
  paths before launching ngspice, so repo-local bridge files remain usable even
  when the merged deck is emitted into a temporary directory.
