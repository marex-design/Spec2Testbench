from pathlib import Path

from spec2testbench.infrastructure.schematic.topology_detector import TopologyDetector


detector = TopologyDetector()

print("Supported circuits:", detector.supported_circuit_count())
print("Supported families:", detector.supported_families())
print("Coverage valid:", detector.validate_coverage())
print()

for family, circuits in detector.circuits_by_family().items():
    print(f"{family}: {len(circuits)}")
    for circuit in circuits:
        print(f"  - {circuit}")

print("\nDetection from benchmark filenames:")
for path in sorted(Path("benchmark_netlists").glob("*.cir")):
    info = detector.detect_from_path(str(path))
    print(f"{path.name:35s} -> {info.family:15s} -> {info.renderer}")