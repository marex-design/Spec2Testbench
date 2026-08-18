from pathlib import Path
from PIL import Image
import matplotlib.pyplot as plt

from spec2testbench.infrastructure.schematic.synthesis.schematic_synthesizer import SchematicSynthesizer

NETLIST_DIR = Path("benchmark_netlists")
OUT_DIR = Path("results/schematics_synthesized")
OUT_DIR.mkdir(parents=True, exist_ok=True)

synth = SchematicSynthesizer()

passed = 0
failed = 0

for path in sorted(NETLIST_DIR.glob("*.cir")):
    output = OUT_DIR / f"{path.stem}.png"

    try:
        netlist = path.read_text()
        synth.synthesize(netlist, str(output), source_name=str(path))
        plt.close("all")

        image = Image.open(output)

        if image.getbbox() is None:
            raise ValueError("Empty image")

        print(f"PASS: {path.name}")
        passed += 1

    except Exception as e:
        print(f"FAIL: {path.name} -> {e}")
        failed += 1

print()
print(f"Total: {passed + failed}")
print(f"PASS: {passed}")
print(f"FAIL: {failed}")