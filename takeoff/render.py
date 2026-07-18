from calendar import month_name
from textwrap import fill

from takeoff.events import (
    AdjudicationRecorded,
    ArgumentProposed,
    ArgumentVetoed,
    FactsCommitted,
    FactEvaluationRecorded,
    GameAborted,
    GameEvent,
    GameStarted,
    RollResolved,
    TurnStarted,
)
from takeoff.models import Visibility


WIDTH = 80


def _line(
    text: str,
    initial: str = "",
    subsequent: str | None = None,
) -> str:
    return fill(
        text,
        width=WIDTH,
        initial_indent=initial,
        subsequent_indent=subsequent if subsequent is not None else initial,
        break_long_words=False,
        break_on_hyphens=False,
    )


def _fact_line(marker: str, fact_id: str, text: str) -> str:
    prefix = f"  {marker} [{fact_id}] "
    return _line(text, prefix, " " * len(prefix))


def turn_month(turn: int) -> str:
    month_index = 5 + turn - 1
    year = 2027 + (month_index - 1) // 12
    month = (month_index - 1) % 12 + 1
    return f"{month_name[month]} {year}"


def render_event(event: GameEvent) -> str:
    if isinstance(event, GameStarted):
        scenario = event.scenario
        roster = "\n".join(f"  {actor.id.value:<7} (llm)" for actor in scenario.actors)
        facts = "\n".join(
            _fact_line(" ", fact.id, fact.text) for fact in scenario.start_facts
        )
        rules = scenario.rules
        return (
            "TAKEOFF\n"
            f"{_line(scenario.purpose)}\n\n"
            f"ACTORS\n{roster}\n\n"
            f"{_line(f'{rules.dice_count}d{rules.dice_sides} + modifier vs '
            f'{rules.target}; {rules.turns} turns; modifiers capped at '
            f'+/-{rules.mod_cap}', 'RULES  ', '       ')}\n\n"
            f"ESTABLISHED FACTS\n{facts}"
        )

    if isinstance(event, TurnStarted):
        title = f" TURN {event.turn} - {turn_month(event.turn)} "
        left = max(2, (WIDTH - len(title)) // 2)
        right = max(2, WIDTH - len(title) - left)
        return f"{'-' * left}{title}{'-' * right}"

    if isinstance(event, GameAborted):
        return _line(event.reason, "GAME INTERRUPTED  ", "                  ")

    if isinstance(event, ArgumentVetoed):
        retry = "retry allowed" if event.retry_allowed else "game aborted"
        return _line(f"{event.reason} ({retry})", "  VETO    ", "          ")

    if isinstance(event, AdjudicationRecorded):
        return ""

    if isinstance(event, RollResolved):
        return _render_roll(event)

    if isinstance(event, FactsCommitted):
        lines = [_fact_line("+", fact.id, fact.text) for fact in event.added]
        lines.extend(
            _fact_line("-", fact_id, "ended") for fact_id in event.public_ended
        )
        return "\n".join(lines)

    if isinstance(event, FactEvaluationRecorded):
        fact = event.added_fact
        if fact is None or fact.visibility != Visibility.PUBLIC:
            return ""
        return _fact_line("+", fact.id, fact.text)

    return render_argument(event)


def render_argument(
    event: ArgumentProposed,
    adjudication: AdjudicationRecorded | None = None,
) -> str:
    reasons = "\n".join(
        _line(reason, f"    {index}. ", "       ")
        for index, reason in enumerate(event.argument.reasons, start=1)
    )
    return (
        f"  {event.actor_id.value} ARGUMENT\n"
        f"{_line(event.argument.action, '    Action: ', '            ')}\n"
        f"{_line(event.argument.intended_result, '    Result: ', '            ')}\n"
        "    Reasons:\n"
        f"{reasons}"
    )


def render_events(events: list[GameEvent]) -> str:
    rendered: list[str] = []
    argument: ArgumentProposed | None = None
    adjudication: AdjudicationRecorded | None = None
    roll: RollResolved | None = None
    for event in events:
        if isinstance(event, ArgumentProposed):
            argument = event
            continue
        if isinstance(event, AdjudicationRecorded):
            adjudication = event
            continue
        if isinstance(event, RollResolved):
            roll = event
            continue
        if isinstance(event, ArgumentVetoed):
            if argument is not None:
                rendered.append(render_argument(argument))
            rendered.append(render_event(event))
            argument = None
            adjudication = None
            continue
        if isinstance(event, FactsCommitted) and argument and adjudication:
            rendered.append(render_turn_resolution(argument, adjudication, roll, event))
            argument = None
            adjudication = None
            roll = None
            continue
        text = render_event(event)
        if text:
            rendered.append(text)
    return "".join(text + "\n\n" for text in rendered)


def render_turn_resolution(
    argument: ArgumentProposed,
    adjudication_event: AdjudicationRecorded,
    roll: RollResolved | None,
    facts: FactsCommitted,
) -> str:
    adjudication = adjudication_event.adjudication
    if adjudication.visibility == Visibility.COVERT:
        public_facts = [
            fact for fact in facts.added if fact.visibility == Visibility.PUBLIC
        ]
        lines = [f"  {argument.actor_id.value} made a covert action."]
        if roll:
            lines.append(_render_roll(roll))
        lines.extend(_fact_line("+", fact.id, fact.text) for fact in public_facts)
        return "\n\n".join(lines)

    cons = "\n".join(
        _line(claim, "    - ", "      ") for claim in adjudication.public_cons
    )
    lines = [
        render_argument(argument, adjudication_event),
        f"  UMPIRE  support {adjudication.pro_strength} | opposition "
        f"{adjudication.con_strength} | net {adjudication.net_mod:+d}\n"
        f"    Risks:\n{cons}",
    ]
    if roll:
        lines.extend((_render_roll(roll), _line(roll.narration, "  OUTCOME  ", "           ")))
    lines.extend(
        _fact_line("+", fact.id, fact.text)
        for fact in facts.added
        if fact.visibility == Visibility.PUBLIC
    )
    lines.extend(
        _fact_line("-", fact_id, "ended") for fact_id in facts.public_ended
    )
    return "\n\n".join(lines)


def _render_roll(event: RollResolved) -> str:
    outcome = event.outcome
    final_dice = outcome.reroll_dice or outcome.initial_dice
    dice = "+".join(str(die) for die in final_dice)
    result = "SUCCESS" if outcome.success else "FAILURE"
    reroll = " (reroll)" if outcome.reroll_dice else ""
    chit_notes: list[str] = []
    if outcome.spent_fail_chit:
        chit_notes.append("spent 1 fail chit")
    if outcome.gained_fail_chit:
        chit_notes.append("gained 1 fail chit")
    roll_line = (
        f"  ROLL    2d6 [{dice}] {outcome.modifier:+d} = {outcome.total} "
        f"vs {outcome.target}{reroll}"
    )
    result_line = (
        f"  RESULT  {result} ({outcome.severity.value}) | "
        f"fail chits: {outcome.chit_balance}"
    )
    if chit_notes:
        result_line += f" | {', '.join(chit_notes)}"
    if outcome.natural_two:
        result_line += " | natural 2: not at this time"
    return f"{roll_line}\n{_line(result_line, subsequent='          ')}"