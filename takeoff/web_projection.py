from pydantic import Field

from takeoff.events import (
    AdjudicationRecorded,
    ArgumentProposed,
    FactsCommitted,
    FactEvaluationRecorded,
    GameEvent,
    GameState,
    RollResolved,
    TurnStarted,
)
from takeoff.ledger import visible_facts
from takeoff.models import ActorId, Fact, StrictModel, Visibility


class WebOutcome(StrictModel):
    turn: int
    actor_id: ActorId
    action: str
    intended_result: str
    reasons: tuple[str, ...]
    cons: tuple[str, ...]
    support: int
    opposition: int
    modifier: int
    roll: str
    success: bool
    severity: str
    narration: str
    facts: tuple[Fact, ...]
    private: bool = False


class GameView(StrictModel):
    version: int = Field(ge=0)
    status: str
    turn: int = Field(ge=0)
    human_actor: ActorId
    public_brief: str
    private_brief: str
    objectives: tuple[str, ...]
    fail_chits: int = Field(ge=0)
    facts: tuple[Fact, ...]
    outcomes: tuple[WebOutcome, ...]
    feedback: str | None = None
    parse_error: str | None = None
    draft: str = ""


def build_game_view(
    *,
    state: GameState,
    events: tuple[GameEvent, ...],
    human_actor: ActorId,
    version: int,
    status: str,
    feedback: str | None = None,
    parse_error: str | None = None,
    draft: str = "",
) -> GameView:
    if state.scenario is None:
        raise ValueError("game has not started")
    actor = next(actor for actor in state.scenario.actors if actor.id == human_actor)
    return GameView(
        version=version,
        status=status,
        turn=state.current_turn,
        human_actor=human_actor,
        public_brief=actor.public_brief,
        private_brief=actor.private_brief,
        objectives=actor.objectives,
        fail_chits=state.fail_chits.get(human_actor, 0),
        facts=visible_facts(state, human_actor),
        outcomes=_resolved_outcomes(events, human_actor),
        feedback=feedback,
        parse_error=parse_error,
        draft=draft,
    )


def _resolved_outcomes(
    events: tuple[GameEvent, ...], human_actor: ActorId
) -> tuple[WebOutcome, ...]:
    arguments: dict[tuple[int, ActorId], ArgumentProposed] = {}
    adjudications: dict[tuple[int, ActorId], AdjudicationRecorded] = {}
    rolls: dict[tuple[int, ActorId], RollResolved] = {}
    outcomes: list[WebOutcome] = []
    for event in events:
        if isinstance(event, TurnStarted):
            continue
        if isinstance(event, ArgumentProposed):
            arguments[(event.turn, event.actor_id)] = event
        elif isinstance(event, AdjudicationRecorded):
            adjudications[(event.turn, event.actor_id)] = event
        elif isinstance(event, RollResolved):
            rolls[(event.turn, event.actor_id)] = event
        elif isinstance(event, FactsCommitted):
            key = (event.turn, event.actor_id)
            argument = arguments.get(key)
            judged = adjudications.get(key)
            roll = rolls.get(key)
            if argument is None or judged is None or roll is None:
                continue
            adjudication = judged.adjudication
            own_private = (
                event.actor_id == human_actor
                and adjudication.visibility == Visibility.COVERT
            )
            public = adjudication.visibility == Visibility.PUBLIC
            if public or own_private:
                action = (
                    argument.argument.action
                    if public or own_private
                    else adjudication.public_action_summary
                )
                intended_result = argument.argument.intended_result
                reasons = argument.argument.reasons
                cons = (
                    tuple(claim.claim for claim in adjudication.cons)
                    if own_private
                    else adjudication.public_cons
                )
                narration = (
                    (
                        adjudication.success_narration
                        if roll.outcome.success
                        else adjudication.failure_narration
                    )
                    if own_private
                    else roll.narration
                )
            else:
                action = "A covert action occurred."
                intended_result = ""
                reasons = ()
                cons = ()
                narration = roll.narration
            visible_added = tuple(
                fact
                for fact in event.added
                if fact.visibility == Visibility.PUBLIC
                or human_actor in fact.known_by
            )
            dice = roll.outcome.reroll_dice or roll.outcome.initial_dice
            outcomes.append(
                WebOutcome(
                    turn=event.turn,
                    actor_id=event.actor_id,
                    action=action,
                    intended_result=intended_result,
                    reasons=reasons,
                    cons=cons,
                    support=adjudication.pro_strength,
                    opposition=adjudication.con_strength,
                    modifier=roll.outcome.modifier,
                    roll="+".join(str(die) for die in dice),
                    success=roll.outcome.success,
                    severity=roll.outcome.severity.value,
                    narration=narration,
                    facts=visible_added,
                    private=own_private,
                )
            )
        elif isinstance(event, FactEvaluationRecorded):
            continue
    return tuple(outcomes)