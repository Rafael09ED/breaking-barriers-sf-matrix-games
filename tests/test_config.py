import pytest

from takeoff.config import Settings


def test_settings_require_openrouter_key(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        Settings.from_env()


def test_settings_load_model_configuration(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("TAKEOFF_PLAYER_MODEL", "example/player-model")
    monkeypatch.setenv("TAKEOFF_UMPIRE_MODEL", "example/umpire-model")
    monkeypatch.setenv("TAKEOFF_PLAYER_REASONING_EFFORT", "high")
    monkeypatch.setenv("TAKEOFF_UMPIRE_REASONING_EFFORT", "xhigh")

    settings = Settings.from_env()

    assert settings.openrouter_api_key == "test-key"
    assert settings.player_model == "example/player-model"
    assert settings.umpire_model == "example/umpire-model"
    assert settings.player_reasoning_effort == "high"
    assert settings.umpire_reasoning_effort == "xhigh"
    assert settings.debug_prompts_path is None


def test_settings_default_to_reasoning_off(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("TAKEOFF_PLAYER_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("TAKEOFF_UMPIRE_REASONING_EFFORT", raising=False)

    settings = Settings.from_env()

    assert settings.player_reasoning_effort == "off"
    assert settings.umpire_reasoning_effort == "off"


def test_settings_reject_unknown_reasoning_effort(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("TAKEOFF_PLAYER_REASONING_EFFORT", "extreme")

    with pytest.raises(ValueError, match="must be one of"):
        Settings.from_env()