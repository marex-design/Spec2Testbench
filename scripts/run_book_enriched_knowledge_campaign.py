from __future__ import annotations

import argparse

from knowledge_stub_lib import build_book_enriched_summary, run_book_enriched_campaign


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the book-enriched knowledge and stub replay campaign")
    parser.add_argument("--build-knowledge", action="store_true")
    parser.add_argument("--validate-knowledge", action="store_true")
    parser.add_argument("--run-microtests", action="store_true")
    parser.add_argument("--audit-retrieval", action="store_true")
    parser.add_argument("--deterministic-parity", action="store_true")
    parser.add_argument("--stub-use-cases", action="store_true")
    parser.add_argument("--stub-frozen-one-trial", action="store_true")
    parser.add_argument("--stub-frozen-three-trials", action="store_true")
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument("--build-summary", action="store_true")
    parser.add_argument("--knowledge-root")
    parser.add_argument("--book-path")
    parser.add_argument("--disable-pyspice", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    selected = any(
        [
            args.build_knowledge,
            args.validate_knowledge,
            args.run_microtests,
            args.audit_retrieval,
            args.deterministic_parity,
            args.stub_use_cases,
            args.stub_frozen_one_trial,
            args.stub_frozen_three_trials,
            args.run_tests,
            args.build_summary,
        ]
    )
    if not selected:
        args.build_knowledge = True
        args.run_microtests = True
        args.validate_knowledge = True
        args.audit_retrieval = True
        args.deterministic_parity = True
        args.stub_use_cases = True
        args.stub_frozen_one_trial = True
        args.stub_frozen_three_trials = True
        args.build_summary = True
    run_book_enriched_campaign(args)
    if args.build_summary:
        print(build_book_enriched_summary())


if __name__ == "__main__":
    main()
