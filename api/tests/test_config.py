"""Env-file export (R13.3, Ruling R3). Uses temp files only, never the real .env files."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from sagaloom.config import load_env_files

VARS = ("SAGALOOM_TEST_BOTH", "SAGALOOM_TEST_ROOT_ONLY", "SAGALOOM_TEST_SHELL", "LANGSMITH_PROJECT")


def _env_files(tmp_path):
    root, api = tmp_path / "root.env", tmp_path / "api.env"
    root.write_text(
        "SAGALOOM_TEST_BOTH=from-root\nSAGALOOM_TEST_ROOT_ONLY=root\nSAGALOOM_TEST_SHELL=root\n",
        encoding="utf-8",
    )
    api.write_text(
        "SAGALOOM_TEST_BOTH=from-api\nSAGALOOM_TEST_SHELL=api\nLANGSMITH_PROJECT=sagaloom-test\n",
        encoding="utf-8",
    )
    return str(root), str(api)  # same order as _ENV_FILES: root first, api/.env last


def test_env_files_are_exported_with_api_env_winning(tmp_path, monkeypatch):
    for var in VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SAGALOOM_TEST_SHELL", "shell")
    load_env_files(_env_files(tmp_path))
    try:
        assert os.environ["SAGALOOM_TEST_BOTH"] == "from-api"  # api/.env beats the root .env
        assert os.environ["SAGALOOM_TEST_ROOT_ONLY"] == "root"  # the root .env fills gaps
        assert os.environ["SAGALOOM_TEST_SHELL"] == "shell"  # the real environment beats both
        assert os.environ["LANGSMITH_PROJECT"] == "sagaloom-test"  # non-Settings keys too
    finally:
        for var in VARS:
            monkeypatch.delenv(var, raising=False)


async def test_default_app_exports_env_files_at_startup_not_import(monkeypatch):
    import sagaloom.web.app as app_module

    calls: list[str] = []
    monkeypatch.setattr(app_module, "load_env_files", lambda: calls.append("load"))

    @asynccontextmanager
    async def runtime(_app):
        calls.append("runtime")
        yield

    app = app_module._with_env_export(FastAPI(lifespan=runtime))
    assert calls == []
    async with app.router.lifespan_context(app):
        pass
    assert calls == ["load", "runtime"]
