from types import SimpleNamespace

from takeoff.config import Settings
from takeoff.models import Argument
from takeoff.openrouter import OpenRouterClient


def test_openrouter_request_disables_reasoning_and_configures_retries() -> None:
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(
                        content=(
                            '{"action":"Audit.","intended_result":"Evidence.",'
                            '"reasons":["Results are ambiguous."]}'
                        )
                    )
                )
            ]
        )

    settings = Settings(
        openrouter_api_key="test-key",
        player_model="z-ai/glm-5.2",
        umpire_model="z-ai/glm-5.2",
        player_reasoning_effort="off",
        umpire_reasoning_effort="off",
        debug_prompts_path=None,
        app_url=None,
        app_name="TAKEOFF",
    )
    client = OpenRouterClient(
        settings,
        model=settings.player_model,
        temperature=0.8,
        reasoning_effort=settings.player_reasoning_effort,
    )
    assert client._client.max_retries == 3  # type: ignore[attr-defined]
    client._client = SimpleNamespace(  # type: ignore[assignment]
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )

    content = client.generate(
        [{"role": "user", "content": "Make an argument."}],
        Argument,
        "argument",
    )

    assert '"action":"Audit."' in content
    assert captured["model"] == "z-ai/glm-5.2"
    assert captured["messages"] == [
        {"role": "user", "content": "Make an argument."}
    ]
    assert captured["extra_body"] == {
        "reasoning": {"enabled": False},
        "provider": {"require_parameters": True},
    }

    client._reasoning_effort = "high"  # type: ignore[attr-defined]
    client.generate(
        [{"role": "user", "content": "Make an argument."}],
        Argument,
        "argument",
    )

    assert captured["extra_body"]["reasoning"] == {
        "effort": "high",
        "exclude": True,
    }


def test_openrouter_can_audit_prompt_without_credentials(tmp_path) -> None:
    settings = Settings(
        openrouter_api_key="secret-key-not-for-log",
        player_model="z-ai/glm-5.2",
        umpire_model="z-ai/glm-5.2",
        player_reasoning_effort="high",
        umpire_reasoning_effort="high",
        debug_prompts_path=tmp_path / "prompts.jsonl",
        app_url=None,
        app_name="TAKEOFF",
    )
    client = OpenRouterClient(
        settings,
        model=settings.player_model,
        temperature=0.8,
        reasoning_effort="high",
    )
    client._audit_prompt(  # type: ignore[attr-defined]
        [{"role": "user", "content": "UNIQUE-COVERT-SENTINEL"}],
        "argument",
    )

    audit = settings.debug_prompts_path.read_text(encoding="utf-8")
    assert "UNIQUE-COVERT-SENTINEL" in audit
    assert "secret-key-not-for-log" not in audit