"""Developer settings store (R12.4)."""

from sagaloom.settings_store import DevSettings, DevSettingsPatch, DevSettingsStore


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
