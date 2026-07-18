import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str
    player_model: str
    umpire_model: str
    player_reasoning_effort: str
    umpire_reasoning_effort: str
    debug_prompts_path: Path | None
    app_url: str | None
    app_name: str

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(dotenv_path=".env")
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required for live play")
        return cls(
            openrouter_api_key=api_key,
            player_model=os.getenv("TAKEOFF_PLAYER_MODEL", "z-ai/glm-5.2"),
            umpire_model=os.getenv("TAKEOFF_UMPIRE_MODEL", "z-ai/glm-5.2"),
            player_reasoning_effort=_reasoning_effort(
                "TAKEOFF_PLAYER_REASONING_EFFORT"
            ),
            umpire_reasoning_effort=_reasoning_effort(
                "TAKEOFF_UMPIRE_REASONING_EFFORT"
            ),
            debug_prompts_path=(
                Path(os.getenv("TAKEOFF_DEBUG_PROMPTS_FILE", "takeoff-prompts.jsonl"))
                if os.getenv("TAKEOFF_DEBUG_PROMPTS", "").lower()
                in {"1", "true", "yes"}
                else None
            ),
            app_url=os.getenv("OPENROUTER_APP_URL") or None,
            app_name=os.getenv("OPENROUTER_APP_NAME", "TAKEOFF"),
        )


def _reasoning_effort(name: str) -> str:
    effort = os.getenv(name, "off").strip().lower()
    supported = {"off", "minimal", "low", "medium", "high", "xhigh"}
    if effort not in supported:
        choices = ", ".join(sorted(supported))
        raise ValueError(f"{name} must be one of: {choices}")
    return effort