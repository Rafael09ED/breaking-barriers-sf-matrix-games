from takeoff.events import GameState
from takeoff.models import (
    ActorId,
    Adjudication,
    Audience,
    Fact,
    PlayerContext,
    UmpireContext,
    Visibility,
)


def visible_facts(
    state: GameState,
    audience: ActorId | Audience,
) -> tuple[Fact, ...]:
    facts = (fact for fact in state.facts.values() if fact.active)
    if audience == Audience.UMPIRE:
        return tuple(facts)
    return tuple(
        fact
        for fact in facts
        if fact.visibility == Visibility.PUBLIC or audience in fact.known_by
    )


def build_player_context(state: GameState, actor_id: ActorId) -> PlayerContext:
    if state.scenario is None or state.current_turn < 1:
        raise ValueError("an active game turn is required to build player context")
    actor = next(
        (candidate for candidate in state.scenario.actors if candidate.id == actor_id),
        None,
    )
    if actor is None:
        raise ValueError(f"unknown actor: {actor_id}")
    return PlayerContext(
        purpose=state.scenario.purpose,
        briefing=state.scenario.briefing,
        turn=state.current_turn,
        actor=actor,
        visible_facts=visible_facts(state, actor_id),
        fail_chits=state.fail_chits.get(actor_id, 0),
    )


def build_umpire_context(
    state: GameState, actor_id: ActorId, argument
) -> UmpireContext:
    if state.scenario is None or state.current_turn < 1:
        raise ValueError("an active game turn is required to build umpire context")
    return UmpireContext(
        scenario=state.scenario,
        turn=state.current_turn,
        actor_id=actor_id,
        argument=argument,
        facts=visible_facts(state, Audience.UMPIRE),
    )


def materialize_fact_changes(
    state: GameState,
    actor_id: ActorId,
    adjudication: Adjudication,
    success: bool,
) -> tuple[tuple[Fact, ...], tuple[str, ...], tuple[str, ...]]:
    changes = (
        adjudication.new_facts_success
        if success
        else adjudication.new_facts_failure
    )
    next_number = max(
        (int(fact_id[1:]) for fact_id in state.facts if fact_id[1:].isdigit()),
        default=0,
    )
    added: list[Fact] = []
    ended: list[str] = []
    public_ended: list[str] = []
    active_ids = {fact.id for fact in state.facts.values() if fact.active}
    for change in changes:
        if change.operation == "end":
            fact_id = change.fact_id or ""
            ended.append(fact_id)
            fact = state.facts.get(fact_id)
            if fact is not None and fact.visibility == Visibility.PUBLIC:
                public_ended.append(fact_id)
            continue
        unknown_sources = set(change.source_fact_ids) - active_ids
        if unknown_sources:
            raise ValueError(
                "cannot source a fact from inactive or unknown facts: "
                + ", ".join(sorted(unknown_sources))
            )
        next_number += 1
        added.append(
            Fact(
                id=f"F{next_number}",
                text=change.text or "",
                visibility=change.visibility or Visibility.PUBLIC,
                known_by=change.known_by,
                source_fact_ids=change.source_fact_ids,
            )
        )
    return tuple(added), tuple(ended), tuple(public_ended)