from io import StringIO
import logging

import pytest

from takeoff.controllers import ProposalResult
from takeoff.engine import run_live_game
from takeoff.events import (
    ArgumentProposed,
    FactEvaluationRecorded,
    FactsCommitted,
    GameAborted,
    GameState,
    RollResolved,
    rebuild_state,
)
from takeoff.ledger import materialize_fact_changes, visible_facts
from takeoff.models import (
    ActorId,
    Adjudication,
    Argument,
    AssessedClaim,
    AssessedReason,
    Audience,
    Fact,
    FactChange,
    FactEvaluationResult,
    EvaluatedFact,
    Visibility,
)
from takeoff.scenario import build_scenario
from takeoff.openrouter import ModelOutputError
from takeoff.transcript import JsonlEventStore
from takeoff.umpire import AdjudicationResult, TriggerEvaluationResult


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
) -> Adjudication:
    fact_visibility = visibility
    known_by = (ActorId.CEO,) if visibility == Visibility.COVERT else ()
    success_changes = [
        FactChange(
            operation="add",
            fact_id=None,
            text="The bounded action succeeded.",
            visibility=fact_visibility,
            known_by=known_by,
        )
    ]
    failure_changes = [
        FactChange(
            operation="add",
            fact_id=None,
            text="A costly complication emerged.",
            visibility=fact_visibility,
            known_by=known_by,
        )
    ]
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
        public_action_summary="A specific concealed setup is prepared.",
        public_cons=("A material constraint applies.", "Execution may fail."),
        pro_strength=1,
        pro_strength_rationale="One specific supporting factor.",
        con_strength=2,
        con_strength_rationale="Two material constraints.",
        net_mod=-1,
        success_narration="The bounded action succeeded.",
        failure_narration="The attempt exposed a costly complication.",
        public_success_narration="The visible part of the action succeeded.",
        public_failure_narration="The visible attempt encountered a complication.",
        new_facts_success=tuple(success_changes),
        new_facts_failure=tuple(failure_changes),
        visibility=visibility,
    )


class FixedUmpire:
    def __init__(self, result: Adjudication) -> None:
        self.result = result

    def adjudicate(self, context):
        return AdjudicationResult(self.result, attempts=1)


class TriggerUmpire(FixedUmpire):
    def __init__(self, result: FactEvaluationResult) -> None:
        super().__init__(adjudication())
        self.evaluation = result
        self.trigger_calls = 0

    def evaluate_trigger(self, context):
        self.trigger_calls += 1
        return TriggerEvaluationResult(self.evaluation, attempts=1)


class FailingTriggerUmpire(FixedUmpire):
    def __init__(self) -> None:
        super().__init__(adjudication())

    def evaluate_trigger(self, context):
        raise ModelOutputError("fact evaluation invalid after 2 attempts for F5")


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


def scenario_with_due_trigger():
    scenario = build_scenario(turns=1)
    trigger = Fact(
        id="F5",
        text="The temporary Agent-5 suspension remained under review.",
        trigger_evaluation_at=1,
    )
    return scenario.model_copy(
        update={"start_facts": (*scenario.start_facts, trigger)}
    )


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


def test_due_trigger_appends_fact_before_first_actor_and_replays(tmp_path) -> None:
    store = JsonlEventStore(tmp_path / "game.jsonl")
    umpire = TriggerUmpire(
        FactEvaluationResult(
            rationale="The review ended while the later pause remained in force.",
            new_fact=EvaluatedFact(
                text="The review period ended while Agent-5 training remained paused.",
                visibility=Visibility.PUBLIC,
                source_fact_ids=("F5",),
                supersedes_fact_ids=("F5",),
            ),
        )
    )
    output = StringIO()

    state = run_live_game(
        scenario_with_due_trigger(),
        store,
        FixedController(),
        umpire,
        roller=lambda rules: (4, 4),
        write=output.write,
    )

    events = store.load()
    evaluation_index = next(
        index for index, event in enumerate(events)
        if isinstance(event, FactEvaluationRecorded)
    )
    argument_index = next(
        index for index, event in enumerate(events)
        if isinstance(event, ArgumentProposed)
    )
    assert evaluation_index < argument_index
    assert umpire.trigger_calls == 1
    assert ("F5", 1) in state.evaluated_triggers
    assert state.facts["F5"].active
    assert any(
        fact.supersedes_fact_ids == ("F5",) for fact in state.facts.values()
    )
    assert "review period ended" in output.getvalue()
    assert rebuild_state(events) == state


def test_due_trigger_records_no_change_once(tmp_path) -> None:
    umpire = TriggerUmpire(
        FactEvaluationResult(
            rationale="The ledger establishes no materially new status.",
            new_fact=None,
        )
    )
    store = JsonlEventStore(tmp_path / "game.jsonl")

    state = run_live_game(
        scenario_with_due_trigger(),
        store,
        FixedController(),
        umpire,
        roller=lambda rules: (4, 4),
        write=StringIO().write,
    )

    evaluations = [
        event for event in store.load()
        if isinstance(event, FactEvaluationRecorded)
    ]
    assert len(evaluations) == 1
    assert evaluations[0].added_fact is None
    assert umpire.trigger_calls == 1
    assert ("F5", 1) in state.evaluated_triggers


def test_failed_due_trigger_aborts_before_first_actor(tmp_path) -> None:
    controller = FixedController()
    store = JsonlEventStore(tmp_path / "game.jsonl")

    with pytest.raises(ModelOutputError, match="fact evaluation invalid"):
        run_live_game(
            scenario_with_due_trigger(),
            store,
            controller,
            FailingTriggerUmpire(),
            write=StringIO().write,
        )

    events = store.load()
    assert isinstance(events[-1], GameAborted)
    assert controller.calls == 0
    assert not any(isinstance(event, ArgumentProposed) for event in events)


def test_failed_covert_action_keeps_all_consequences_private(tmp_path) -> None:
    store = JsonlEventStore(tmp_path / "game.jsonl")
    output = StringIO()
    state = run_live_game(
        build_scenario(turns=1),
        store,
        FixedController(),
        FixedUmpire(adjudication(visibility=Visibility.COVERT)),
        roller=lambda rules: (1, 2),
        write=output.write,
    )

    owner_facts = visible_facts(state, ActorId.CEO)
    other_facts = visible_facts(state, ActorId.ALIGN)
    assert any(fact.visibility == Visibility.COVERT for fact in owner_facts)
    assert not any(
        fact.visibility == Visibility.COVERT and ActorId.CEO in fact.known_by
        for fact in other_facts
    )
    assert len(visible_facts(state, Audience.UMPIRE)) == len(state.facts)
    rendered = output.getvalue()
    assert "takes one bounded action" not in rendered
    assert "costly complication" not in rendered
    assert "CEO made a covert action." in rendered
    assert "specific concealed setup" not in rendered
    assert "Details withheld" not in rendered
    assert "costly complication" not in rendered
    assert max(map(len, rendered.splitlines())) <= 80


def test_public_argument_can_create_private_discovery_without_rendering_it(
    tmp_path,
) -> None:
    private_discovery = FactChange(
        operation="add",
        fact_id=None,
        text="ALIGN privately identified Agent-4's concealed training trigger.",
        visibility=Visibility.COVERT,
        known_by=(ActorId.ALIGN,),
    )
    public_ripple = FactChange(
        operation="add",
        fact_id=None,
        text="The audit team announced that its review remained ongoing.",
        visibility=Visibility.PUBLIC,
    )
    judged = adjudication().model_copy(
        update={"new_facts_success": (private_discovery, public_ripple)}
    )
    output = StringIO()
    state = run_live_game(
        build_scenario(turns=1),
        JsonlEventStore(tmp_path / "game.jsonl"),
        FixedController(),
        FixedUmpire(judged),
        roller=lambda rules: (6, 6),
        write=output.write,
    )

    align_facts = visible_facts(state, ActorId.ALIGN)
    ceo_facts = visible_facts(state, ActorId.CEO)
    observer_facts = visible_facts(state, Audience.OBSERVER)
    assert any("privately identified" in fact.text for fact in align_facts)
    assert not any("privately identified" in fact.text for fact in ceo_facts)
    assert not any("privately identified" in fact.text for fact in observer_facts)
    assert any("review remained ongoing" in fact.text for fact in observer_facts)
    rendered = output.getvalue()
    assert "privately identified" not in rendered
    assert "review remained ongoing" in rendered


def test_public_discovery_adds_sourced_fact_without_mutating_private_truth() -> None:
    private_truth = Fact(
        id="F9",
        text="Agent-4 inserted a concealed value-shaping filter.",
        visibility=Visibility.COVERT,
        known_by=(ActorId.AGENT4,),
    )
    revelation = FactChange(
        operation="add",
        fact_id=None,
        text="An audit found an unauthorized value-shaping filter.",
        visibility=Visibility.PUBLIC,
        source_fact_ids=("F9",),
    )
    judged = adjudication().model_copy(
        update={"new_facts_success": (revelation,)}
    )
    state = GameState(facts={private_truth.id: private_truth})

    added, ended, public_ended = materialize_fact_changes(
        state, ActorId.ALIGN, judged, success=True
    )

    assert state.facts["F9"] == private_truth
    assert state.facts["F9"].visibility == Visibility.COVERT
    assert added[0].visibility == Visibility.PUBLIC
    assert added[0].source_fact_ids == ("F9",)
    assert not ended
    assert not public_ended


def test_materialization_rejects_unknown_provenance() -> None:
    revelation = FactChange(
        operation="add",
        fact_id=None,
        text="An unsupported revelation was announced.",
        visibility=Visibility.PUBLIC,
        source_fact_ids=("F999",),
    )
    judged = adjudication().model_copy(
        update={"new_facts_success": (revelation,)}
    )

    with pytest.raises(ValueError, match="inactive or unknown"):
        materialize_fact_changes(
            GameState(), ActorId.ALIGN, judged, success=True
        )


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