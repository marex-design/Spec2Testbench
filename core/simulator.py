from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Any


class NgspiceSimulator:
    def __init__(self, ngspice_command: str = "ngspice", timeout_seconds: int = 30):
        self.ngspice_command = ngspice_command
        self.timeout_seconds = timeout_seconds

    def run(self, circuit_path: str | Path, log_path: str | Path) -> Dict[str, Any]:
        circuit_path = Path(circuit_path)
        log_path = Path(log_path)

        if not circuit_path.exists():
            raise FileNotFoundError(f"Circuit file not found: {circuit_path}")

        log_path.parent.mkdir(parents=True, exist_ok=True)

        command = [
            self.ngspice_command,
            "-b",
            "-o",
            str(log_path),
            str(circuit_path),
        ]

        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )

            return {
                "success": process.returncode == 0,
                "returncode": process.returncode,
                "command": " ".join(command),
                "circuit_path": str(circuit_path),
                "log_path": str(log_path),
                "stdout": process.stdout,
                "stderr": process.stderr,
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "returncode": None,
                "command": " ".join(command),
                "circuit_path": str(circuit_path),
                "log_path": str(log_path),
                "stdout": "",
                "stderr": f"Simulation timed out after {self.timeout_seconds} seconds",
            }


def run_ngspice(
    circuit_path: str | Path,
    log_path: str | Path,
    ngspice_command: str = "ngspice",
    timeout_seconds: int = 30,
) -> Dict[str, Any]:
    simulator = NgspiceSimulator(
        ngspice_command=ngspice_command,
        timeout_seconds=timeout_seconds,
    )
    return simulator.run(circuit_path, log_path)