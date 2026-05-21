"""Test configuration.

Two test types:
- Deterministic (test_validate.py) — run on every commit, no LLM
- LLM-assessed (test_assignments.py) — run on demand, uses scoring models

Set RUN_LLM_TESTS=1 to include LLM-assessed tests.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "llm" in item.keywords and not os.environ.get("RUN_LLM_TESTS"):
            item.add_marker(pytest.mark.skip(reason="Set RUN_LLM_TESTS=1 to run"))


def pytest_configure(config):
    config.addinivalue_line("markers", "llm: tests that call LLM APIs (slow, costs tokens)")
