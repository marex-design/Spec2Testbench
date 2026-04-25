from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional


class MeasurementExtractor:
    def __init__(self, log_path: str | Path):
        self.log_path = Path(log_path)

    def read_log(self) -> str:
        if not self.log_path.exists():
            raise FileNotFoundError(f"Log file not found: {self.log_path}")
        return self.log_path.read_text(encoding="utf-8", errors="ignore")

    def extract_measurements(self) -> Dict[str, float]:
        text = self.read_log()
        measurements: Dict[str, float] = {}

        pattern = re.compile(
            r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)",
            re.MULTILINE,
        )

        for match in pattern.finditer(text):
            name = match.group(1).lower()
            value = float(match.group(2))
            measurements[name] = value

        return measurements

    def has_errors(self) -> bool:
        text = self.read_log().lower()
        error_keywords = [
            "error:",
            "failed",
            "aborted",
            "no such vector",
            "analysis not run",
            "doanalyses: not found",
        ]
        return any(keyword in text for keyword in error_keywords)

    def extract_errors(self) -> list[str]:
        text = self.read_log()
        errors = []

        for line in text.splitlines():
            lower = line.lower()
            if (
                "error:" in lower
                or "failed" in lower
                or "aborted" in lower
                or "analysis not run" in lower
                or "no such vector" in lower
            ):
                errors.append(line.strip())

        return errors

    def extract(self) -> Dict[str, object]:
        measurements = self.extract_measurements()
        errors = self.extract_errors()

        return {
            "log_path": str(self.log_path),
            "success": len(errors) == 0 and len(measurements) > 0,
            "measurements": measurements,
            "errors": errors,
        }


def extract_measurements(log_path: str | Path) -> Dict[str, float]:
    extractor = MeasurementExtractor(log_path)
    return extractor.extract_measurements()


def extract_log_results(log_path: str | Path) -> Dict[str, object]:
    extractor = MeasurementExtractor(log_path)
    return extractor.extract()