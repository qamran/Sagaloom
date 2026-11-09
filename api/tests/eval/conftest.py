"""Evals run on one shared session event loop, like the app (one uvicorn loop).

langchain-openai caches one async HTTP client per process. With a loop per test, a later test
reuses a pooled connection bound to an earlier, closed loop and its first call raises
`RuntimeError: Event loop is closed` (#30). Only tests under this directory are changed; the
unit suite keeps its per-test loops.
"""

from pathlib import Path

import pytest
from pytest_asyncio import is_async_test

from sagaloom.llm import install_warning_filters

_EVAL_DIR = Path(__file__).resolve().parent

install_warning_filters()


def pytest_collection_modifyitems(items):
    session_loop = pytest.mark.asyncio(loop_scope="session")
    for item in items:
        if is_async_test(item) and _EVAL_DIR in Path(item.path).resolve().parents:
            item.add_marker(session_loop, append=False)
