from pathlib import Path

NETLIST_DIR = Path("benchmark_netlists")

for path in NETLIST_DIR.glob("*.cir"):
    text = path.read_text()

    text = text.replace(
        ".model NMOS NMOS LEVEL=1 VTO=1 KP=1m",
        ".model NMOS NMOS LEVEL=1 VTO=1 KP=1m LAMBDA=0.02 KF=0 AF=1"
    )

    text = text.replace(
        ".model NMOS NMOS LEVEL=1 VTO=0.7 KP=5m",
        ".model NMOS NMOS LEVEL=1 VTO=0.7 KP=5m LAMBDA=0.02 KF=0 AF=1"
    )

    text = text.replace(
        ".model PMOS PMOS LEVEL=1 VTO=-1 KP=0.5m",
        ".model PMOS PMOS LEVEL=1 VTO=-1 KP=0.5m LAMBDA=0.02 KF=0 AF=1"
    )

    path.write_text(text)

print("MOS models patched.")