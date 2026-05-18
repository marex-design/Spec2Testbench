#!/usr/bin/env python3
import sys
from pathlib import Path

# Ajouter le chemin du projet
sys.path.insert(0, str(Path(__file__).parent))

from spec2testbench.presentation.cli.main import app

if __name__ == "__main__":
    app()
