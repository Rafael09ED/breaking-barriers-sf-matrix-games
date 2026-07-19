from collections.abc import Callable
import logging
import sys
from uuid import uuid4

from takeoff.events import (
    AdjudicationRecorded,
    ArgumentProposed,
    ArgumentVetoed,
    FactsCommitted,
    FactEvaluationRecorded,
    GameAborted,
    GameEvent,
    GameStarted,
    GameState,
    RollResolved,
    TurnStarted,
    reduce_event,
)
from takeoff.controllers import Controller
from takeoff.ledger import (
    build_player_context,
    build_fact_evaluation_context,
    build_umpire_context,
    materialize_evaluated_fact,
    materialize_fact_changes,
)
from takeoff.models import Scenario
from takeoff.openrouter import ModelOutputError, ModelTransportError
from takeoff.render import render_event, render_events
from takeoff.rules import resolve_roll, roll_dice, rotating_order
from takeoff.transcript import JsonlEventStore
from takeoff.umpire import Umpire


logger = logging.getLogger(__name__)


def run_live_game(
    scenario: Scenario,
    store: JsonlEventStore,
    controller: Controller,
    umpire: Umpire,
    roller=roll_dice,
    write: Callable[[str], object] = sys.stdout.write,
    on_commit: Callable[[GameEvent, GameState], object] | None = None,
) -> GameState:
    game_id = uuid4()
    state = GameState()

    def commit(event: GameEvent, *, display: bool = True) -> None:
        nonlocal state
        store.append(event)
        state = reduce_event(state, event)
        if on_commit is not None:
            on_commit(event, state)
        if display:
            text = render_event(event)
            if text:
                write(text + "\n\n")

    commit(GameStarted(game_id=game_id, seq=1, scenario=scenario))
    seq = 2
    actor_ids = tuple(actor.id for actor in scenario.actors)
    for turn in range(1, scenario.rules.turns + 1):
        order = rotating_order(actor_ids, turn)
        commit(
            TurnStarted(
                game_id=game_id,
                seq=seq,
                turn=turn,
                actor_order=order,
            )
        )
        seq += 1
        due_facts = sorted(
            (
                fact
                for fact in state.facts.values()
                if fact.active
                and fact.trigger_evaluation_at == turn
                and (fact.id, turn) not in state.evaluated_triggers
            ),
            key=lambda fact: (
                (0, int(fact.id[1:]))
                if fact.id.startswith("F") and fact.id[1:].isdigit()
                else (1, fact.id)
            ),
        )
        for trigger_fact in due_facts:
            try:
                evaluated = umpire.evaluate_trigger(
                    build_fact_evaluation_context(state, trigger_fact)
                )
                added_fact = materialize_evaluated_fact(
                    state, evaluated.evaluation
                )
                commit(
                    FactEvaluationRecorded(
                        game_id=game_id,
                        seq=seq,
                        turn=turn,
                        trigger_fact_id=trigger_fact.id,
                        rationale=evaluated.evaluation.rationale,
                        added_fact=added_fact,
                        attempts=evaluated.attempts,
                    )
                )
                seq += 1
            except (ModelTransportError, ModelOutputError) as error:
                error_kind = (
                    "OpenRouter request failed"
                    if isinstance(error, ModelTransportError)
                    else "Model response failed"
                )
                logger.error("%s: %s", error_kind, error)
                commit(
                    GameAborted(
                        game_id=game_id,
                        seq=seq,
                        reason=f"{error_kind}: {error}",
                    )
                )
                raise
        for actor_id in order:
            try:
                resolved = False
                veto_feedback: str | None = None
                for veto_attempt in range(2):
                    player_context = build_player_context(state, actor_id).model_copy(
                        update={"veto_feedback": veto_feedback}
                    )
                    proposal = controller.propose(player_context)
                    argument_event = ArgumentProposed(
                        game_id=game_id,
                        seq=seq,
                        turn=turn,
                        actor_id=actor_id,
                        argument=proposal.argument,
                        attempts=proposal.attempts,
                        spend_fail_chit_on_failure=proposal.spend_fail_chit_on_failure,
                    )
                    commit(argument_event, display=False)
                    seq += 1
                    judged = umpire.adjudicate(
                        build_umpire_context(state, actor_id, proposal.argument)
                    )
                    adjudication_event = AdjudicationRecorded(
                        game_id=game_id,
                        seq=seq,
                        turn=turn,
                        actor_id=actor_id,
                        adjudication=judged.adjudication,
                        attempts=judged.attempts,
                    )
                    commit(adjudication_event, display=False)
                    seq += 1
                    if judged.adjudication.veto is not None:
                        retry_allowed = veto_attempt == 0
                        veto_event = ArgumentVetoed(
                            game_id=game_id,
                            seq=seq,
                            turn=turn,
                            actor_id=actor_id,
                            reason=judged.adjudication.veto,
                            retry_allowed=retry_allowed,
                        )
                        commit(veto_event, display=False)
                        seq += 1
                        write(render_events([argument_event, veto_event]))
                        if retry_allowed:
                            veto_feedback = judged.adjudication.veto
                            continue
                        raise ModelOutputError(
                            f"umpire vetoed both proposals for {actor_id.value}; "
                            f"second veto: {judged.adjudication.veto}"
                        )

                    outcome = resolve_roll(
                        judged.adjudication,
                        scenario.rules,
                        state.fail_chits.get(actor_id, 0),
                        proposal.spend_fail_chit_on_failure,
                        roller,
                    )
                    narration = (
                        judged.adjudication.public_success_narration
                        if outcome.success
                        else judged.adjudication.public_failure_narration
                    )
                    roll_event = RollResolved(
                        game_id=game_id,
                        seq=seq,
                        turn=turn,
                        actor_id=actor_id,
                        outcome=outcome,
                        narration=narration,
                    )
                    commit(roll_event, display=False)
                    seq += 1
                    added, ended, public_ended = materialize_fact_changes(
                        state, actor_id, judged.adjudication, outcome.success
                    )
                    facts_event = FactsCommitted(
                        game_id=game_id,
                        seq=seq,
                        turn=turn,
                        actor_id=actor_id,
                        added=added,
                        ended=ended,
                        public_ended=public_ended,
                    )
                    commit(facts_event, display=False)
                    seq += 1
                    write(
                        render_events(
                            [
                                argument_event,
                                adjudication_event,
                                roll_event,
                                facts_event,
                            ]
                        )
                    )
                    resolved = True
                    break
                if not resolved:
                    raise RuntimeError("actor turn ended without a consequence")
            except (ModelTransportError, ModelOutputError) as error:
                error_kind = (
                    "OpenRouter request failed"
                    if isinstance(error, ModelTransportError)
                    else "Model response failed"
                )
                logger.error("%s: %s", error_kind, error)
                commit(
                    GameAborted(
                        game_id=game_id,
                        seq=seq,
                        reason=f"{error_kind}: {error}",
                    )
                )
                raise
            except KeyboardInterrupt:
                commit(
                    GameAborted(
                        game_id=game_id,
                        seq=seq,
                        reason="Interrupted by user.",
                    )
                )
                raise

    return state