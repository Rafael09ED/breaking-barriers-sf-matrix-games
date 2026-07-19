from io import StringIO
from uuid import uuid4

import pytest

from takeoff.controllers import ProposalResult
from takeoff.engine import run_live_game
from takeoff.events import (
    ArgumentProposed,
    FactsCommitted,
    GameStarted,
    GameState,
    TurnStarted,
    rebuild_state,
)
from takeoff.ledger import visible_facts
from takeoff.models import (
    ActorId,
    Adjudication,
    AssessedClaim,
    AssessedReason,
    Audience,
    Fact,
    FactChange,
    Visibility,
)
from takeoff.render import render_event, render_events
from takeoff.rules import rotating_order
from takeoff.scenario import build_scenario
from takeoff.transcript import JsonlEventStore
from takeoff.umpire import AdjudicationResult


class EchoController:
    def propose(self, context):
        from takeoff.models import Argument

        return ProposalResult(
            argument=Argument(
                action=f"{context.actor.id.value} takes a bounded action.",
                intended_result=f"Advance {context.actor.id.value}'s objectives.",
                reasons=(f"{context.actor.id.value} has a role-specific reason.",),
            ),
            attempts=1,
        )


class EchoUmpire:
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
                success_narration="The action advanced.",
                failure_narration="The action created a complication.",
                public_success_narration="The action advanced.",
                public_failure_narration="The action created a complication.",
                new_facts_success=(
                    FactChange(operation="add", fact_id=None, text="The action advanced.", visibility=Visibility.PUBLIC),
                ),
                new_facts_failure=(
                    FactChange(operation="add", fact_id=None, text="A complication emerged.", visibility=Visibility.PUBLIC),
                ),
                visibility=Visibility.PUBLIC,
            ),
            attempts=1,
        )


def test_rotating_order_moves_first_actor_each_turn() -> None:
    actors = tuple(ActorId)

    assert rotating_order(actors, 1) == actors
    assert rotating_order(actors, 2) == (*actors[1:], actors[0])
    assert rotating_order(actors, 6) == actors


def test_transcript_round_trip_rebuilds_state(tmp_path) -> None:
    scenario = build_scenario()
    game_id = uuid4()
    store = JsonlEventStore(tmp_path / "game.jsonl")
    events = [
        GameStarted(game_id=game_id, seq=1, scenario=scenario),
        TurnStarted(
            game_id=game_id,
            seq=2,
            turn=1,
            actor_order=tuple(actor.id for actor in scenario.actors),
        ),
    ]

    for event in events:
        store.append(event)

    loaded = store.load()
    assert loaded == events
    state = rebuild_state(loaded)
    assert state.game_id == game_id
    assert state.current_turn == 1
    assert tuple(state.facts) == ("F1", "F2", "F3", "F4")


def test_legacy_fallback_marker_loads_but_is_not_retained() -> None:
    event = ArgumentProposed.model_validate(
        {
            "game_id": uuid4(),
            "seq": 1,
            "turn": 1,
            "actor_id": ActorId.ALIGN,
            "argument": {
                "action": "Run an audit.",
                "intended_result": "Produce evidence.",
                "reasons": ["F4 is ambiguous."],
            },
            "used_fallback": True,
        }
    )

    assert "used_fallback" not in event.model_dump()


def test_reducer_rejects_sequence_gap() -> None:
    scenario = build_scenario()
    game_id = uuid4()

    with pytest.raises(ValueError, match="expected event sequence 2"):
        rebuild_state(
            [
                GameStarted(game_id=game_id, seq=1, scenario=scenario),
                TurnStarted(
                    game_id=game_id,
                    seq=3,
                    turn=1,
                    actor_order=tuple(actor.id for actor in scenario.actors),
                ),
            ]
        )


def test_live_render_matches_transcript_render(tmp_path) -> None:
    scenario = build_scenario(turns=2)
    store = JsonlEventStore(tmp_path / "game.jsonl")
    output = StringIO()

    live_state = run_live_game(
        scenario,
        store,
        EchoController(),
        EchoUmpire(),
        roller=lambda rules: (3, 3),
        write=output.write,
    )
    events = store.load()
    replay_state = rebuild_state(events)

    rendered = output.getvalue()
    assert rendered == render_events(events)
    assert max(map(len, rendered.splitlines())) <= 80
    assert replay_state == live_state
    assert len(replay_state.arguments) == 10
    assert replay_state.actor_order[0] == ActorId.ALIGN


def test_engine_observer_receives_reduced_state_after_each_commit(tmp_path) -> None:
    observed = []

    final_state = run_live_game(
        build_scenario(turns=1),
        JsonlEventStore(tmp_path / "game.jsonl"),
        EchoController(),
        EchoUmpire(),
        roller=lambda rules: (3, 3),
        write=StringIO().write,
        on_commit=lambda event, state: observed.append((event, state)),
    )

    assert observed
    assert all(event.seq == state.last_seq for event, state in observed)
    assert observed[-1][1] == final_state


def test_covert_fact_is_visible_only_to_informed_actors_and_umpire() -> None:
    public = Fact(id="F1", text="Public fact")
    covert = Fact(
        id="F2",
        text="Sentinel covert fact",
        visibility=Visibility.COVERT,
        known_by=(ActorId.AGENT4,),
    )
    state = GameState(facts={public.id: public, covert.id: covert})

    assert visible_facts(state, ActorId.AGENT4) == (public, covert)
    assert visible_facts(state, Audience.UMPIRE) == (public, covert)
    assert visible_facts(state, ActorId.ALIGN) == (public,)
    assert visible_facts(state, Audience.OBSERVER) == (public,)


def test_covert_fact_can_be_shared_with_multiple_informed_actors() -> None:
    shared = Fact(
        id="F1",
        text="ALIGN privately briefed POTUS on the discovered setup.",
        visibility=Visibility.COVERT,
        known_by=(ActorId.ALIGN, ActorId.POTUS),
    )
    state = GameState(facts={shared.id: shared})

    assert visible_facts(state, ActorId.ALIGN) == (shared,)
    assert visible_facts(state, ActorId.POTUS) == (shared,)
    assert visible_facts(state, ActorId.CEO) == ()
    assert visible_facts(state, Audience.OBSERVER) == ()


def test_fact_commit_renders_only_public_ended_ids() -> None:
    event = FactsCommitted(
        game_id=uuid4(),
        seq=1,
        turn=1,
        actor_id=ActorId.ALIGN,
        added=(),
        ended=("F_PUBLIC", "F_SECRET"),
        public_ended=("F_PUBLIC",),
    )

    rendered = render_event(event)

    assert "F_PUBLIC" in rendered
    assert "F_SECRET" not in rendered


def test_covert_fact_requires_informed_actor() -> None:
    with pytest.raises(ValueError, match="at least one informed actor"):
        Fact(id="F1", text="Unowned secret", visibility=Visibility.COVERT)