from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, TypeAdapter, model_validator

from takeoff.models import (
    ActorId,
    Adjudication,
    Argument,
    Fact,
    RollOutcome,
    Scenario,
    StrictModel,
)
from takeoff.rules import rotating_order


SCHEMA_VERSION = 1


class EventBase(StrictModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    game_id: UUID
    seq: int = Field(ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="before")
    @classmethod
    def discard_legacy_fallback_marker(cls, data: object) -> object:
        if isinstance(data, dict) and "used_fallback" in data:
            data = {key: value for key, value in data.items() if key != "used_fallback"}
        return data


class GameStarted(EventBase):
    type: Literal["game_started"] = "game_started"
    scenario: Scenario


class TurnStarted(EventBase):
    type: Literal["turn_started"] = "turn_started"
    turn: int = Field(ge=1)
    actor_order: tuple[ActorId, ...]


class ArgumentProposed(EventBase):
    type: Literal["argument_proposed"] = "argument_proposed"
    turn: int = Field(ge=1)
    actor_id: ActorId
    argument: Argument
    scaffold: bool = False
    attempts: int = Field(default=1, ge=1, le=2)
    spend_fail_chit_on_failure: bool = False


class ArgumentVetoed(EventBase):
    type: Literal["argument_vetoed"] = "argument_vetoed"
    turn: int = Field(ge=1)
    actor_id: ActorId
    reason: str
    retry_allowed: bool


class AdjudicationRecorded(EventBase):
    type: Literal["adjudication_recorded"] = "adjudication_recorded"
    turn: int = Field(ge=1)
    actor_id: ActorId
    adjudication: Adjudication
    attempts: int = Field(ge=1, le=2)


class RollResolved(EventBase):
    type: Literal["roll_resolved"] = "roll_resolved"
    turn: int = Field(ge=1)
    actor_id: ActorId
    outcome: RollOutcome
    narration: str


class FactsCommitted(EventBase):
    type: Literal["facts_committed"] = "facts_committed"
    turn: int = Field(ge=1)
    actor_id: ActorId
    added: tuple[Fact, ...]
    ended: tuple[str, ...]
    public_ended: tuple[str, ...]


class FactEvaluationRecorded(EventBase):
    type: Literal["fact_evaluation_recorded"] = "fact_evaluation_recorded"
    turn: int = Field(ge=1)
    trigger_fact_id: str
    rationale: str
    added_fact: Fact | None
    attempts: int = Field(ge=1, le=2)


class GameAborted(EventBase):
    type: Literal["game_aborted"] = "game_aborted"
    reason: str


GameEvent = Annotated[
    GameStarted
    | TurnStarted
    | ArgumentProposed
    | ArgumentVetoed
    | AdjudicationRecorded
    | RollResolved
    | FactsCommitted
    | FactEvaluationRecorded
    | GameAborted,
    Field(discriminator="type"),
]
EVENT_ADAPTER = TypeAdapter(GameEvent)


class GameState(StrictModel):
    game_id: UUID | None = None
    last_seq: int = 0
    scenario: Scenario | None = None
    facts: dict[str, Fact] = Field(default_factory=dict)
    current_turn: int = 0
    actor_order: tuple[ActorId, ...] = ()
    arguments: tuple[ArgumentProposed, ...] = ()
    adjudications: tuple[AdjudicationRecorded, ...] = ()
    rolls: tuple[RollResolved, ...] = ()
    fail_chits: dict[ActorId, int] = Field(default_factory=dict)
    evaluated_triggers: tuple[tuple[str, int], ...] = ()
    abort_reason: str | None = None


def reduce_event(state: GameState, event: GameEvent) -> GameState:
    expected_seq = state.last_seq + 1
    if event.seq != expected_seq:
        raise ValueError(f"expected event sequence {expected_seq}, got {event.seq}")

    if isinstance(event, GameStarted):
        if state.game_id is not None:
            raise ValueError("game_started must be the first event")
        return GameState(
            game_id=event.game_id,
            last_seq=event.seq,
            scenario=event.scenario,
            facts={fact.id: fact for fact in event.scenario.start_facts},
        )

    if state.game_id is None or state.scenario is None:
        raise ValueError("game_started must precede all other events")
    if event.game_id != state.game_id:
        raise ValueError("event game_id does not match the active game")

    if isinstance(event, TurnStarted):
        if event.turn != state.current_turn + 1:
            raise ValueError("turns must start sequentially")
        expected_order = rotating_order(
            tuple(actor.id for actor in state.scenario.actors), event.turn
        )
        if event.actor_order != expected_order:
            raise ValueError("actor order does not match the rotating turn order")
        return state.model_copy(
            update={
                "last_seq": event.seq,
                "current_turn": event.turn,
                "actor_order": event.actor_order,
            }
        )

    if isinstance(event, GameAborted):
        if state.abort_reason is not None:
            raise ValueError("game is already aborted")
        return state.model_copy(
            update={"last_seq": event.seq, "abort_reason": event.reason}
        )

    if event.turn != state.current_turn:
        raise ValueError("event turn does not match the active turn")
    if isinstance(event, FactEvaluationRecorded):
        trigger = state.facts.get(event.trigger_fact_id)
        trigger_key = (event.trigger_fact_id, event.turn)
        if trigger is None:
            raise ValueError("cannot evaluate an unknown triggering fact")
        if trigger.trigger_evaluation_at != event.turn:
            raise ValueError("fact evaluation does not match its scheduled turn")
        if trigger_key in state.evaluated_triggers:
            raise ValueError("fact evaluation trigger was already consumed")
        facts = dict(state.facts)
        if event.added_fact is not None:
            if event.added_fact.id in facts:
                raise ValueError(f"fact id already exists: {event.added_fact.id}")
            facts[event.added_fact.id] = event.added_fact
        return state.model_copy(
            update={
                "last_seq": event.seq,
                "facts": facts,
                "evaluated_triggers": (*state.evaluated_triggers, trigger_key),
            }
        )
    if event.actor_id not in state.actor_order:
        raise ValueError("argument actor is not in the active turn order")
    if isinstance(event, ArgumentProposed):
        return state.model_copy(
            update={
                "last_seq": event.seq,
                "arguments": (*state.arguments, event),
            }
        )
    if isinstance(event, ArgumentVetoed):
        return state.model_copy(update={"last_seq": event.seq})
    if isinstance(event, AdjudicationRecorded):
        return state.model_copy(
            update={
                "last_seq": event.seq,
                "adjudications": (*state.adjudications, event),
            }
        )
    if isinstance(event, RollResolved):
        return state.model_copy(
            update={
                "last_seq": event.seq,
                "rolls": (*state.rolls, event),
                "fail_chits": {
                    **state.fail_chits,
                    event.actor_id: event.outcome.chit_balance,
                },
            }
        )

    facts = dict(state.facts)
    for fact_id in event.ended:
        fact = facts.get(fact_id)
        if fact is None or not fact.active:
            raise ValueError(f"cannot end inactive or unknown fact {fact_id}")
        facts[fact_id] = fact.model_copy(update={"active": False})
    for fact in event.added:
        if fact.id in facts:
            raise ValueError(f"fact id already exists: {fact.id}")
        facts[fact.id] = fact
    return state.model_copy(update={"last_seq": event.seq, "facts": facts})


def rebuild_state(events: list[GameEvent]) -> GameState:
    state = GameState()
    for event in events:
        state = reduce_event(state, event)
    return state