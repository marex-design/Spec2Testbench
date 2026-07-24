from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "scripts" / "freeze_paper_public_evidence.py"


def _parse_wrapper_args(argv: list[str]) -> list[str]:
    forwarded = [argv[0]]
    index = 1
    while index < len(argv):
        token = argv[index]
        if token == "--freeze-id":
            if index + 1 >= len(argv):
                raise SystemExit("--freeze-id requires a value")
            os.environ["SPEC2TESTBENCH_FREEZE_ID"] = argv[index + 1]
            index += 2
            continue
        if token == "--freeze-root":
            if index + 1 >= len(argv):
                raise SystemExit("--freeze-root requires a value")
            os.environ["SPEC2TESTBENCH_FREEZE_ROOT"] = argv[index + 1]
            index += 2
            continue
        forwarded.append(token)
        index += 1
    return forwarded


def main() -> None:
    sys.argv = _parse_wrapper_args(sys.argv)
    sys.argv[0] = str(TARGET)
    runpy.run_path(str(TARGET), run_name="__main__")


if __name__ == "__main__":
    main()
