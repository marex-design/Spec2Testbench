from __future__ import annotations

import os

import pytest


def pytest_runtest_setup(item):
    if "llm_live" not in item.keywords:
        return
    if os.getenv("RUN_LLM_LIVE", "").strip() != "1":
        pytest.skip("RUN_LLM_LIVE=1 is required for llm_live tests.")
