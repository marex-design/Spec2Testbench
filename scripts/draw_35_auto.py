from pathlib import Path

from spec2testbench.infrastructure.schematic.schematic_router import draw_schematic_auto

NETLIST_DIR = Path("benchmark_netlists")
OUT_DIR = Path("results/schematics_auto")
OUT_DIR.mkdir(parents=True, exist_ok=True)

passed = 0
failed = 0

for netlist in sorted(NETLIST_DIR.glob("*.cir")):
    output = OUT_DIR / f"{netlist.stem}.png"

    try:
        draw_schematic_auto(str(netlist), str(output))
        print(f"PASS: {netlist.name} -> {output}")
        passed += 1
    except Exception as e:
        print(f"FAIL: {netlist.name} -> {e}")
        failed += 1

print()
print(f"Total: {passed + failed}")
print(f"PASS: {passed}")
print(f"FAIL: {failed}")