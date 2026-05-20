from pathlib import Path
from PIL import Image
import matplotlib.pyplot as plt

from spec2testbench.infrastructure.schematic.topology_detector import TopologyDetector
from spec2testbench.infrastructure.schematic.renderer_factory import RendererFactory


NETLIST_DIR = Path("benchmark_netlists")
OUT_DIR = Path("results/schematics_factory")
OUT_DIR.mkdir(parents=True, exist_ok=True)

detector = TopologyDetector()
factory = RendererFactory()

passed = 0
failed = 0

for netlist_path in sorted(NETLIST_DIR.glob("*.cir")):
    try:
        info = detector.detect_from_path(str(netlist_path))
        renderer = factory.create(info.renderer)

        netlist = netlist_path.read_text()
        output = OUT_DIR / f"{netlist_path.stem}.png"

        renderer.draw(netlist, str(output))
        plt.close("all")

        img = Image.open(output)
        if img.getbbox() is None:
            raise ValueError("Empty image generated")

        print(f"PASS: {netlist_path.name:35s} -> {info.renderer}")
        passed += 1

    except Exception as e:
        print(f"FAIL: {netlist_path.name:35s} -> {e}")
        failed += 1

print()
print(f"Total: {passed + failed}")
print(f"PASS: {passed}")
print(f"FAIL: {failed}")