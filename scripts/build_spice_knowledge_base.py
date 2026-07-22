from __future__ import annotations

import argparse

from knowledge_stub_lib import build_spice_knowledge_base


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the SPICE knowledge base")
    parser.add_argument("--knowledge-root")
    args = parser.parse_args()
    build_spice_knowledge_base()


if __name__ == "__main__":
    main()
