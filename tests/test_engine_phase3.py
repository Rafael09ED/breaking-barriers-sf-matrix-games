from io import StringIO
import logging

import pytest

from takeoff.controllers import ProposalResult
from takeoff.engine import run_live_game
from takeoff.events import FactsCommitted, GameAborted, RollResolved, rebuild_state
from takeoff.ledger import visible_facts
from takeoff.models import (
    ActorId,
    Adjudication,
    Argument,
    AssessedClaim,
    AssessedReason,
    Audience,
    FactChange,
    Visibility,
)
from takeoff.scenario import build_scenario
from takeoff.openrouter import ModelOutputError
from takeoff.transcript import JsonlEventStore
from takeoff.umpire import AdjudicationResult


class FixedController:
    def __init__(self) -> None:
        self.calls = 0

    def propose(self, context):
        self.calls += 1
        return ProposalResult(
            argument=Argument(
                action=f"{context.actor.id.value} takes one bounded action.",
                intended_result="Change the situation in one specific way.",
                reasons=("An established fact supports this action.",),
            ),
            attempts=1,
        )


def adjudication(
    *,
    visibility: Visibility = Visibility.PUBLIC,
    veto: str | None = None,
    public_observation: str | None = None,
) -> Adjudication:
    return Adjudication(
        veto=veto,
        pros=(
            AssessedReason(
                claim="Supported", rationale="Specific", reason_index=1
            ),
        ),
        cons=(
            AssessedClaim(claim="Constraint one", rationale="Specific"),
            AssessedClaim(claim="Constraint two", rationale="Specific"),
        ),
        pro_strength=1,
        pro_strength_rationale="One specific supporting factor.",
        con_strength=2,
        con_strength_rationale="Two material constraints.",
        net_mod=-1,
        success_narration="The bounded action succeeded.",
        failure_narration="The attempt exposed a costly complication.",
        new_facts_success=(
            FactChange(operation="add", fact_id=None, text="The bounded action succeeded."),
        ),
        new_facts_failure=(
            FactChange(operation="add", fact_id=None, text="A costly complication emerged."),
        ),
        visibility=visibility,
        public_observation=public_observation,
    )


class FixedUmpire:
    def __init__(self, result: Adjudication) -> None:
        self.result = result

    def adjudicate(self, context):
        return AdjudicationResult(self.result, attempts=1)


class DoubleVetoUmpire:
    def adjudicate(self, context):
        return AdjudicationResult(
            adjudication(veto="The proposal directly negates an active fact."),
            attempts=1,
        )


class FirstVetoUmpire:
    def __init__(self) -> None:
        self.calls = 0

    def adjudicate(self, context):
        self.calls += 1
        if self.calls == 1:
            return AdjudicationResult(
                adjudication(
                    veto="The proposal combines an audit and a briefing."
                ),
                attempts=1,
            )
        return AdjudicationResult(adjudication(), attempts=1)


class RecordingController(FixedController):
    def __init__(self) -> None:
        super().__init__()
        self.actors: list[ActorId] = []
        self.veto_feedback: list[str | None] = []

    def propose(self, context):
        self.actors.append(context.actor.id)
        self.veto_feedback.append(context.veto_feedback)
        return super().propose(context)


class InvalidUmpire:
    def adjudicate(self, context):
        raise ModelOutputError(
            "umpire response invalid after 2 attempts for CEO: "
            "attempt 1: bad arithmetic | attempt 2: missing failure fact"
        )


class InterruptedController:
    def propose(self, context):
        raise KeyboardInterrupt


def test_every_actor_turn_commits_a_fact(tmp_path) -> None:
    store = JsonlEventStore(tmp_path / "game.jsonl")

    state = run_live_game(
        build_scenario(turns=1),
        store,
        FixedController(),
        FixedUmpire(adjudication()),
        roller=lambda rules: (4, 4),
        write=StringIO().write,
    )

    commits = [event for event in store.load() if isinstance(event, FactsCommitted)]
    assert len(commits) == 5
    assert all(event.added or event.ended for event in commits)
    assert len(state.facts) == 9


def test_failed_covert_action_hides_fact_but_commits_public_observation(tmp_path) -> None:
    store = JsonlEventStore(tmp_path / "game.jsonl")
    output = StringIO()
    state = run_live_game(
        build_scenario(turns=1),
        store,
        FixedController(),
        FixedUmpire(
            adjudication(
                visibility=Visibility.COVERT,
                public_observation="Network defenders observed unusual access patterns.",
            )
        ),
        roller=lambda rules: (1, 2),
        write=output.write,
    )

    owner_facts = visible_facts(state, ActorId.CEO)
    other_facts = visible_facts(state, ActorId.ALIGN)
    assert any(fact.visibility == Visibility.COVERT for fact in owner_facts)
    assert not any(
        fact.visibility == Visibility.COVERT and fact.owner == ActorId.CEO
        for fact in other_facts
    )
    assert any("unusual access" in fact.text for fact in other_facts)
    assert len(visible_facts(state, Audience.UMPIRE)) == len(state.facts)
    rendered = output.getvalue()
    assert "takes one bounded action" not in rendered
    assert "costly complication" not in rendered
    assert "SECRET ARGUMENT" in rendered
    assert "unusual access patterns" in rendered
    assert max(map(len, rendered.splitlines())) <= 80


def test_natural_two_renders_required_phrase(tmp_path) -> None:
    output = StringIO()
    store = JsonlEventStore(tmp_path / "game.jsonl")

    run_live_game(
        build_scenario(turns=1),
        store,
        FixedController(),
        FixedUmpire(adjudication()),
        roller=lambda rules: (1, 1),
        write=output.write,
    )

    rolls = [event for event in store.load() if isinstance(event, RollResolved)]
    assert all(event.outcome.natural_two and not event.outcome.success for event in rolls)
    assert "not at this time" in output.getvalue()


def test_second_veto_aborts_without_mutating_facts(tmp_path) -> None:
    controller = FixedController()
    store = JsonlEventStore(tmp_path / "game.jsonl")
    output = StringIO()

    with pytest.raises(ModelOutputError, match="vetoed both proposals"):
        run_live_game(
            build_scenario(turns=1),
            store,
            controller,
            DoubleVetoUmpire(),
            write=output.write,
        )

    events = store.load()
    state = rebuild_state(events)
    assert controller.calls == 2
    assert not state.rolls
    assert len(state.facts) == 4
    assert isinstance(events[-1], GameAborted)
    assert "second veto" in events[-1].reason
    assert "game aborted" in output.getvalue()
    assert "forced pass" not in output.getvalue()


def test_first_veto_retries_same_actor_with_feedback_before_advancing(tmp_path) -> None:
    controller = RecordingController()

    run_live_game(
        build_scenario(turns=1),
        JsonlEventStore(tmp_path / "game.jsonl"),
        controller,
        FirstVetoUmpire(),
        roller=lambda rules: (4, 4),
        write=StringIO().write,
    )

    assert controller.actors[:3] == [ActorId.CEO, ActorId.CEO, ActorId.ALIGN]
    assert controller.veto_feedback[:3] == [
        None,
        "The proposal combines an audit and a briefing.",
        None,
    ]


def test_invalid_umpire_response_logs_and_aborts_without_consequence(
    tmp_path, caplog
) -> None:
    store = JsonlEventStore(tmp_path / "game.jsonl")

    with caplog.at_level(logging.ERROR), pytest.raises(ModelOutputError):
        run_live_game(
            build_scenario(turns=1),
            store,
            FixedController(),
            InvalidUmpire(),
            write=StringIO().write,
        )

    events = store.load()
    state = rebuild_state(events)
    assert isinstance(events[-1], GameAborted)
    assert "attempt 1: bad arithmetic" in events[-1].reason
    assert "attempt 2: missing failure fact" in events[-1].reason
    assert "Model response failed" in caplog.text
    assert len(state.facts) == 4
    assert not state.adjudications
    assert not state.rolls
    assert not any(isinstance(event, FactsCommitted) for event in events)


def test_keyboard_interrupt_is_persisted_without_state_consequence(tmp_path) -> None:
    store = JsonlEventStore(tmp_path / "game.jsonl")

    with pytest.raises(KeyboardInterrupt):
        run_live_game(
            build_scenario(turns=1),
            store,
            InterruptedController(),
            FixedUmpire(adjudication()),
            write=StringIO().write,
        )

    events = store.load()
    state = rebuild_state(events)
    assert isinstance(events[-1], GameAborted)
    assert events[-1].reason == "Interrupted by user."
    assert state.abort_reason == "Interrupted by user."
    assert not state.arguments
    assert not state.rolls