# Fichier : scripts/test_graph.py
import os
import glob
import sys
import importlib.util

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
SCHEMATIC_DIR = os.path.join(PROJECT_ROOT, "spec2testbench", "schematic")
BENCHMARK_DIR = os.path.join(PROJECT_ROOT, "benchmark_netlists")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "benchmarks")

def force_import(module_name, file_name):
    path = os.path.join(SCHEMATIC_DIR, file_name)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

RenderEngine = force_import("render_engine", "render_engine.py").RenderEngine

def main():
    renderer = RenderEngine()
    
    # Trouver tous les fichiers .cir
    netlists = glob.glob(os.path.join(BENCHMARK_DIR, "*.cir"))
    print(f"Trouvé {len(netlists)} benchmarks à traiter.")
    
    for netlist in netlists:
        base_name = os.path.splitext(os.path.basename(netlist))[0]
        output_img = os.path.join(OUTPUT_DIR, f"schematic_{base_name}.png")
        
        print(f"\n>>> Traitement de : {base_name}")
        renderer.draw_from_netlist(netlist, output_img)

if __name__ == "__main__":
    main()