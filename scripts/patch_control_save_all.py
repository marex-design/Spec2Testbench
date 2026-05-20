from pathlib import Path
import re

NETLIST_DIR = Path("benchmark_netlists")

for path in NETLIST_DIR.glob("*.cir"):
    text = path.read_text()

    text = re.sub(
        r"\.control.*?\.endc",
        ".control\nset noaskquit\nsave all\nrun\n.endc",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    path.write_text(text)

print("All control blocks patched with save all.")