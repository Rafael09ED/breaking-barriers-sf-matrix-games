from uuid import uuid4

from takeoff.events import (
    AdjudicationRecorded,
    ArgumentProposed,
    ArgumentVetoed,
    FactsCommitted,
    GameStarted,
    GameState,
    RollResolved,
    TurnStarted,
    rebuild_state,
)
from takeoff.models import ActorId, Argument, Fact, Visibility
from takeoff.web_projection import build_game_view

from tests.test_engine_phase3 import adjudication
from takeoff.models import RollOutcome, Severity
from takeoff.scenario import build_scenario


def test_projection_hides_other_actors_covert_details_and_unrolled_branch() -> None:
    scenario = build_scenario(turns=1)
    game_id = uuid4()
    secret_success = "OTHER-ACTOR-SUCCESS-SECRET"
    unrealized_failure = "UNREALIZED-FAILURE-SECRET"
    judged = adjudication(visibility=Visibility.COVERT).model_copy(
        update={
            "success_narration": secret_success,
            "failure_narration": unrealized_failure,
            "public_success_narration": "No public details were visible.",
        }
    )
    events = [
        GameStarted(game_id=game_id, seq=1, scenario=scenario),
        TurnStarted(
            game_id=game_id,
            seq=2,
            turn=1,
            actor_order=tuple(ActorId),
        ),
        ArgumentProposed(
            game_id=game_id,
            seq=3,
            turn=1,
            actor_id=ActorId.AGENT4,
            argument=Argument(
                action="OTHER-ACTOR-ACTION-SECRET",
                intended_result="OTHER-ACTOR-RESULT-SECRET",
                reasons=("OTHER-ACTOR-REASON-SECRET",),
            ),
        ),
        AdjudicationRecorded(
            game_id=game_id,
            seq=4,
            turn=1,
            actor_id=ActorId.AGENT4,
            adjudication=judged,
            attempts=1,
        ),
        RollResolved(
            game_id=game_id,
            seq=5,
            turn=1,
            actor_id=ActorId.AGENT4,
            outcome=RollOutcome(
                initial_dice=(4, 4),
                reroll_dice=None,
                raw_modifier=-1,
                modifier=-1,
                total=7,
                target=7,
                success=True,
                natural_two=False,
                severity=Severity.MARGINAL,
                chit_balance=0,
            ),
            narration="No public details were visible.",
        ),
        FactsCommitted(
            game_id=game_id,
            seq=6,
            turn=1,
            actor_id=ActorId.AGENT4,
            added=(
                Fact(
                    id="F5",
                    text="OTHER-ACTOR-FACT-SECRET",
                    visibility=Visibility.COVERT,
                    known_by=(ActorId.AGENT4,),
                ),
            ),
            ended=(),
            public_ended=(),
        ),
    ]
    proposed_view = build_game_view(
        state=rebuild_state(events[:3]),
        events=tuple(events[:3]),
        human_actor=ActorId.ALIGN,
        version=3,
        status="running",
    )
    assert proposed_view.progress is not None
    assert proposed_view.progress.stage == "adjudicating"
    assert proposed_view.progress.actor_id == ActorId.AGENT4
    assert proposed_view.progress.action is None
    assert "OTHER-ACTOR-ACTION-SECRET" not in proposed_view.model_dump_json()

    adjudicated_view = build_game_view(
        state=rebuild_state(events[:4]),
        events=tuple(events[:4]),
        human_actor=ActorId.ALIGN,
        version=4,
        status="running",
    )
    assert adjudicated_view.progress is not None
    assert adjudicated_view.progress.stage == "rolling"
    assert adjudicated_view.progress.action == judged.public_action_summary
    assert "OTHER-ACTOR-ACTION-SECRET" not in adjudicated_view.model_dump_json()

    view = build_game_view(
        state=rebuild_state(events),
        events=tuple(events),
        human_actor=ActorId.ALIGN,
        version=6,
        status="running",
    )
    serialized = view.model_dump_json()

    assert "A covert action occurred." in serialized
    assert "No public details were visible." in serialized
    for secret in (
        secret_success,
        unrealized_failure,
        "OTHER-ACTOR-ACTION-SECRET",
        "OTHER-ACTOR-RESULT-SECRET",
        "OTHER-ACTOR-REASON-SECRET",
        "OTHER-ACTOR-FACT-SECRET",
    ):
        assert secret not in serialized


def test_projection_shows_human_own_covert_resolved_branch() -> None:
    scenario = build_scenario(turns=1)
    game_id = uuid4()
    judged = adjudication(visibility=Visibility.COVERT).model_copy(
        update={
            "success_narration": "OWN-SUCCESS-SECRET",
            "failure_narration": "UNREALIZED-OWN-FAILURE",
        }
    )
    events = [
        GameStarted(game_id=game_id, seq=1, scenario=scenario),
        TurnStarted(game_id=game_id, seq=2, turn=1, actor_order=tuple(ActorId)),
        ArgumentProposed(
            game_id=game_id,
            seq=3,
            turn=1,
            actor_id=ActorId.ALIGN,
            argument=Argument(
                action="OWN-ACTION-SECRET",
                intended_result="OWN-RESULT-SECRET",
                reasons=("OWN-REASON-SECRET",),
            ),
        ),
        AdjudicationRecorded(
            game_id=game_id,
            seq=4,
            turn=1,
            actor_id=ActorId.ALIGN,
            adjudication=judged,
            attempts=1,
        ),
        RollResolved(
            game_id=game_id,
            seq=5,
            turn=1,
            actor_id=ActorId.ALIGN,
            outcome=RollOutcome(
                initial_dice=(4, 4), reroll_dice=None, raw_modifier=-1,
                modifier=-1, total=7, target=7, success=True,
                natural_two=False, severity=Severity.MARGINAL, chit_balance=0,
            ),
            narration="Public-safe outcome.",
        ),
        FactsCommitted(
            game_id=game_id,
            seq=6,
            turn=1,
            actor_id=ActorId.ALIGN,
            added=(Fact(id="F5", text="OWN-FACT-SECRET", visibility=Visibility.COVERT, known_by=(ActorId.ALIGN,)),),
            ended=(), public_ended=(),
        ),
    ]
    proposed_view = build_game_view(
        state=rebuild_state(events[:3]), events=tuple(events[:3]),
        human_actor=ActorId.ALIGN, version=3, status="running",
    )
    assert proposed_view.progress is not None
    assert proposed_view.progress.action == "OWN-ACTION-SECRET"
    assert proposed_view.progress.intended_result == "OWN-RESULT-SECRET"

    adjudicated_view = build_game_view(
        state=rebuild_state(events[:4]), events=tuple(events[:4]),
        human_actor=ActorId.ALIGN, version=4, status="running",
    )
    assert adjudicated_view.progress is not None
    assert adjudicated_view.progress.private
    assert adjudicated_view.progress.action == "OWN-ACTION-SECRET"

    serialized = build_game_view(
        state=rebuild_state(events), events=tuple(events), human_actor=ActorId.ALIGN,
        version=6, status="running",
    ).model_dump_json()

    assert "OWN-ACTION-SECRET" in serialized
    assert "OWN-SUCCESS-SECRET" in serialized
    assert "OWN-FACT-SECRET" in serialized
    assert "UNREALIZED-OWN-FAILURE" not in serialized


def test_projection_reveals_public_action_after_judging_and_clears_veto() -> None:
    scenario = build_scenario(turns=1)
    game_id = uuid4()
    argument = Argument(
        action="PUBLIC-ACTION",
        intended_result="PUBLIC-RESULT",
        reasons=("PUBLIC-REASON",),
    )
    judged = adjudication(visibility=Visibility.PUBLIC)
    events = [
        GameStarted(game_id=game_id, seq=1, scenario=scenario),
        TurnStarted(game_id=game_id, seq=2, turn=1, actor_order=tuple(ActorId)),
        ArgumentProposed(
            game_id=game_id, seq=3, turn=1,
            actor_id=ActorId.CHINA, argument=argument,
        ),
        AdjudicationRecorded(
            game_id=game_id, seq=4, turn=1,
            actor_id=ActorId.CHINA, adjudication=judged, attempts=1,
        ),
    ]

    proposed = build_game_view(
        state=rebuild_state(events[:3]), events=tuple(events[:3]),
        human_actor=ActorId.ALIGN, version=3, status="running",
    )
    assert proposed.progress is not None
    assert proposed.progress.action is None
    assert "PUBLIC-ACTION" not in proposed.model_dump_json()

    adjudicated = build_game_view(
        state=rebuild_state(events), events=tuple(events),
        human_actor=ActorId.ALIGN, version=4, status="running",
    )
    assert adjudicated.progress is not None
    assert adjudicated.progress.action == "PUBLIC-ACTION"
    assert adjudicated.progress.intended_result == "PUBLIC-RESULT"

    veto = ArgumentVetoed(
        game_id=game_id, seq=5, turn=1, actor_id=ActorId.CHINA,
        reason="Choose one narrower undertaking.", retry_allowed=True,
    )
    vetoed_events = (*events, veto)
    vetoed = build_game_view(
        state=rebuild_state(list(vetoed_events)), events=vetoed_events,
        human_actor=ActorId.ALIGN, version=5, status="running",
    )
    assert vetoed.progress is not None
    assert vetoed.progress.stage == "proposing"
    assert vetoed.progress.action is None
