from pathlib import Path

NETLIST_DIR = Path("benchmark_netlists")

for netlist in NETLIST_DIR.glob("*.cir"):
    text = netlist.read_text()

    if ".control" not in text:
        text = text.replace(
            ".end",
            """
.control
run
.endc

.end
"""
        )

        netlist.write_text(text)

        print(f"Patched: {netlist.name}")

print("Done.")