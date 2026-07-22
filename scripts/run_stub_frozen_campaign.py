from __future__ import annotations

import argparse

from knowledge_stub_lib import run_stub_frozen_campaign


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the stub frozen campaign")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    run_stub_frozen_campaign(trials=args.trials, run_id=args.run_id)


if __name__ == "__main__":
    main()
