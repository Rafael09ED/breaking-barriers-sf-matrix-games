import argparse
from datetime import UTC, datetime
import logging
from pathlib import Path

from takeoff.config import Settings
from takeoff.controllers import LlmController
from takeoff.engine import run_live_game
from takeoff.models import ActorId
from takeoff.openrouter import ModelOutputError, ModelTransportError, OpenRouterClient
from takeoff.scenario import build_scenario
from takeoff.transcript import JsonlEventStore
from takeoff.umpire import LlmUmpire
from takeoff.umpire_test import run_umpire_test


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="takeoff",
        description="Play the TAKEOFF AI 2027 matrix game.",
    )
    parser.add_argument("--seat", choices=[actor.value for actor in ActorId])
    parser.add_argument("--turns", type=int, default=6)
    parser.add_argument("--replay", type=Path, metavar="FILE")
    parser.add_argument("--test-umpire", action="store_true")
    return parser


def main() -> int:
    logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args()
    if args.turns < 1:
        raise SystemExit("--turns must be at least 1")
    if args.seat or args.replay:
        raise SystemExit(
            "This Phase 3 build currently supports live autoplay, --turns, and --test-umpire."
        )

    try:
        settings = Settings.from_env()
    except ValueError as error:
        raise SystemExit(str(error)) from error

    umpire = LlmUmpire(
        OpenRouterClient(
            settings,
            model=settings.umpire_model,
            temperature=0.1,
            reasoning_effort=settings.umpire_reasoning_effort,
        )
    )
    if args.test_umpire:
        try:
            run_umpire_test(umpire)
        except (ModelTransportError, ModelOutputError) as error:
            print(f"Model error: {error}")
            return 1
        return 0

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    transcript_path = Path(f"game-{stamp}.jsonl")
    scenario = build_scenario(turns=args.turns)
    controller = LlmController(
        OpenRouterClient(
            settings,
            model=settings.player_model,
            temperature=0.8,
            reasoning_effort=settings.player_reasoning_effort,
        )
    )
    try:
        run_live_game(
            scenario,
            JsonlEventStore(transcript_path),
            controller,
            umpire,
        )
    except (ModelTransportError, ModelOutputError) as error:
        print(f"\nModel error: {error}")
        print(f"Partial transcript saved: {transcript_path}")
        print(f"Replay later with: takeoff --replay {transcript_path}")
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        print(f"Partial transcript saved: {transcript_path}")
        return 130
    print(f"\nTranscript: {transcript_path}")
    return 0