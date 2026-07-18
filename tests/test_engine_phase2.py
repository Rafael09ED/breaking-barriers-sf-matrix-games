from io import StringIO

import pytest

from takeoff.controllers import ProposalResult
from takeoff.engine import run_live_game
from takeoff.events import GameAborted
from takeoff.models import (
    ActorId,
    Adjudication,
    Argument,
    AssessedClaim,
    AssessedReason,
    FactChange,
    Visibility,
)
from takeoff.openrouter import ModelTransportError
from takeoff.scenario import build_scenario
from takeoff.transcript import JsonlEventStore
from takeoff.umpire import AdjudicationResult


class PersonaController:
    def __init__(self) -> None:
        self.actors: list[ActorId] = []

    def propose(self, context):
        self.actors.append(context.actor.id)
        return ProposalResult(
            argument=Argument(
                action=f"{context.actor.id.value} pursues its own doctrine.",
                intended_result=f"Advance {context.actor.id.value}'s objectives.",
                reasons=(context.actor.private_brief,),
            ),
            attempts=1,
        )


class FailingController:
    def propose(self, context):
        raise ModelTransportError("network unavailable")


class PassUmpire:
    def adjudicate(self, context):
        return AdjudicationResult(
            adjudication=Adjudication(
                veto=None,
                pros=tuple(
                    AssessedReason(
                        claim=reason,
                        rationale="Specific",
                        reason_index=index,
                    )
                    for index, reason in enumerate(context.argument.reasons, start=1)
                ),
                cons=(
                    AssessedClaim(claim="Constraint one", rationale="Limited"),
                    AssessedClaim(claim="Constraint two", rationale="Limited"),
                ),
                public_action_summary="The actor takes a bounded action.",
                public_cons=("Constraint one", "Constraint two"),
                pro_strength=1,
                pro_strength_rationale="One specific supporting factor.",
                con_strength=0,
                con_strength_rationale="No material opposition.",
                net_mod=len(context.argument.reasons),
                success_narration="The bounded action advanced.",
                failure_narration="The attempt created a complication.",
                public_success_narration="The bounded action advanced.",
                public_failure_narration="The attempt created a complication.",
                new_facts_success=(
                    FactChange(operation="add", fact_id=None, text="The bounded action advanced.", visibility=Visibility.PUBLIC),
                ),
                new_facts_failure=(
                    FactChange(operation="add", fact_id=None, text="A complication emerged.", visibility=Visibility.PUBLIC),
                ),
                visibility=Visibility.PUBLIC,
            ),
            attempts=1,
        )


def test_engine_requests_each_actor_in_rotating_order(tmp_path) -> None:
    controller = PersonaController()
    store = JsonlEventStore(tmp_path / "game.jsonl")

    state = run_live_game(
        build_scenario(turns=2),
        store,
        controller,
        PassUmpire(),
        roller=lambda rules: (3, 3),
        write=StringIO().write,
    )

    assert controller.actors == [
        ActorId.CEO,
        ActorId.ALIGN,
        ActorId.POTUS,
        ActorId.CHINA,
        ActorId.AGENT4,
        ActorId.ALIGN,
        ActorId.POTUS,
        ActorId.CHINA,
        ActorId.AGENT4,
        ActorId.CEO,
    ]
    assert len(state.arguments) == 10
    assert all(not event.scaffold for event in state.arguments)
    assert len({event.argument.action for event in state.arguments[:5]}) == 5


def test_network_failure_persists_abort_event(tmp_path) -> None:
    store = JsonlEventStore(tmp_path / "game.jsonl")

    with pytest.raises(ModelTransportError, match="network unavailable"):
        run_live_game(
            build_scenario(turns=1),
            store,
            FailingController(),
            PassUmpire(),
            write=StringIO().write,
        )

    events = store.load()
    assert isinstance(events[-1], GameAborted)
    assert "network unavailable" in events[-1].reason