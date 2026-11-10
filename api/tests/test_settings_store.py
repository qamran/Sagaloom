"""Developer settings store (R12.4)."""

import pytest
from pydantic import ValidationError

from sagaloom.settings_store import (
    DevSettings,
    DevSettingsPatch,
    DevSettingsStore,
    enabled_tool_names,
)


def test_defaults_when_file_missing(tmp_path):
    assert DevSettingsStore(tmp_path / "settings.json").get() == DevSettings()


def test_update_persists_and_merges(tmp_path):
    path = tmp_path / "settings.json"
    store = DevSettingsStore(path)
    store.update(DevSettingsPatch(agent_temperature=0.7))
    store.update(DevSettingsPatch(guard_enabled=False))
    again = DevSettingsStore(path).get()
    assert again.agent_temperature == 0.7
    assert again.guard_enabled is False


def test_reset_system_prompt(tmp_path):
    store = DevSettingsStore(tmp_path / "settings.json")
    assert store.update(DevSettingsPatch(agent_system_prompt="Custom.")).agent_system_prompt == "Custom."
    assert store.update(DevSettingsPatch(reset_system_prompt=True)).agent_system_prompt is None


def test_store_ignores_invalid_fields(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"agent_temperature": 9, "guard_enabled": "yes", "agent_max_tokens": 512}', encoding="utf-8")
    got = DevSettingsStore(path).get()
    assert got.agent_temperature == 0.0
    assert got.guard_enabled is True
    assert got.agent_max_tokens == 512
    path.write_text("not json", encoding="utf-8")
    assert DevSettingsStore(path).get() == DevSettings()


def test_explicit_null_clears_max_tokens(tmp_path):
    store = DevSettingsStore(tmp_path / "settings.json")
    assert store.update(DevSettingsPatch(agent_max_tokens=512)).agent_max_tokens == 512
    store.update(DevSettingsPatch(agent_max_tokens=None))
    assert store.get().agent_max_tokens is None


def test_explicit_null_clears_system_prompt(tmp_path):
    store = DevSettingsStore(tmp_path / "settings.json")
    store.update(DevSettingsPatch(agent_system_prompt="Custom."))
    store.update(DevSettingsPatch(agent_system_prompt=None))
    assert store.get().agent_system_prompt is None


def test_unsent_fields_stay_unchanged(tmp_path):
    store = DevSettingsStore(tmp_path / "settings.json")
    store.update(DevSettingsPatch(agent_max_tokens=512))
    store.update(DevSettingsPatch(guard_enabled=False))
    assert store.get().agent_max_tokens == 512


def test_enabled_tools_persists_and_null_means_all(tmp_path):
    path = tmp_path / "settings.json"
    store = DevSettingsStore(path)
    assert store.get().enabled_tools is None
    store.update(DevSettingsPatch(enabled_tools=["real_world_reference"]))
    assert DevSettingsStore(path).get().enabled_tools == ["real_world_reference"]
    store.update(DevSettingsPatch(enabled_tools=None))
    assert DevSettingsStore(path).get().enabled_tools is None


def test_import_wiki_is_a_known_tool(tmp_path):
    store = DevSettingsStore(tmp_path / "settings.json")
    store.update(DevSettingsPatch(enabled_tools=["import_wiki"]))
    assert store.get().enabled_tools == ["import_wiki"]


def test_unknown_tool_is_a_validation_error():
    with pytest.raises(ValidationError):
        DevSettingsPatch(enabled_tools=["rm_rf"])


def test_core_tools_are_enabled_even_when_omitted():
    core = {"search_canon", "create_or_update_entry", "check_contradiction"}
    assert enabled_tool_names(DevSettings(enabled_tools=[])) == core
    assert enabled_tool_names(DevSettings(enabled_tools=["export_world"])) == core | {"export_world"}
    assert enabled_tool_names(DevSettings()) == core | {
        "export_world", "real_world_reference", "remember_preference", "import_wiki"
    }
    assert enabled_tool_names(DevSettings(enabled_tools=["import_wiki"])) == core | {"import_wiki"}


def test_tool_specs_match_the_built_tools():
    from unittest.mock import MagicMock

    from sagaloom.tools.canon_tools import CORE_TOOLS, TOOL_SPECS, make_tools

    built = {t.name: t.description for t in make_tools(None, None, None, wiki=MagicMock())}
    assert {s["name"]: s["description"] for s in TOOL_SPECS} == built
    assert {s["name"] for s in TOOL_SPECS if s["core"]} == CORE_TOOLS


def test_unknown_tools_warning_logged_once(tmp_path, caplog):
    import json
    import logging

    path = tmp_path / "settings.json"
    store = DevSettingsStore(path)
    path.write_text(json.dumps({"enabled_tools": ["nope"]}), encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="sagaloom.settings_store"):
        for _ in range(3):
            store.get()
    assert caplog.text.count("unknown tools") == 1
    path.write_text(json.dumps({"enabled_tools": ["other_bad"]}), encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="sagaloom.settings_store"):
        store.get()
        store.get()
    assert caplog.text.count("unknown tools") == 2
