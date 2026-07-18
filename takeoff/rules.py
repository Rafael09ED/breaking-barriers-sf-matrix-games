from collections.abc import Callable
import random

from takeoff.models import Adjudication, RollOutcome, Rules, Severity
from takeoff.models import ActorId


def rotating_order(actor_ids: tuple[ActorId, ...], turn: int) -> tuple[ActorId, ...]:
    if turn < 1:
        raise ValueError("turn must be at least 1")
    if not actor_ids:
        raise ValueError("at least one actor is required")
    offset = (turn - 1) % len(actor_ids)
    return actor_ids[offset:] + actor_ids[:offset]


def scored_modifier(adjudication: Adjudication) -> int:
    return adjudication.pro_strength - adjudication.con_strength


def clamp_modifier(modifier: int, cap: int) -> int:
    return max(-cap, min(cap, modifier))


def roll_dice(rules: Rules) -> tuple[int, ...]:
    return tuple(random.randint(1, rules.dice_sides) for _ in range(rules.dice_count))


def resolve_roll(
    adjudication: Adjudication,
    rules: Rules,
    held_chits: int,
    spend_fail_chit: bool = False,
    roller: Callable[[Rules], tuple[int, ...]] = roll_dice,
) -> RollOutcome:
    raw_modifier = scored_modifier(adjudication)
    modifier = clamp_modifier(raw_modifier, rules.mod_cap)
    initial_dice = roller(rules)
    _validate_dice(initial_dice, rules)
    initial_success = _is_success(initial_dice, modifier, rules.target)

    reroll_dice: tuple[int, ...] | None = None
    chit_balance = held_chits
    spent_fail_chit = False
    final_dice = initial_dice
    if not initial_success and held_chits > 0 and spend_fail_chit:
        chit_balance -= 1
        spent_fail_chit = True
        reroll_dice = roller(rules)
        _validate_dice(reroll_dice, rules)
        final_dice = reroll_dice

    success = _is_success(final_dice, modifier, rules.target)
    natural_two = sum(final_dice) == rules.dice_count
    gained_fail_chit = not success
    if not success:
        chit_balance += 1
    total = sum(final_dice) + modifier
    margin = abs(total - rules.target)
    severity = (
        Severity.DECISIVE
        if margin >= 4
        else Severity.MARGINAL
        if margin <= 1
        else Severity.STANDARD
    )
    return RollOutcome(
        initial_dice=initial_dice,
        reroll_dice=reroll_dice,
        raw_modifier=raw_modifier,
        modifier=modifier,
        total=total,
        target=rules.target,
        success=success,
        natural_two=natural_two,
        severity=severity,
        spent_fail_chit=spent_fail_chit,
        gained_fail_chit=gained_fail_chit,
        chit_balance=chit_balance,
    )


def _is_success(dice: tuple[int, ...], modifier: int, target: int) -> bool:
    return sum(dice) != len(dice) and sum(dice) + modifier >= target


def _validate_dice(dice: tuple[int, ...], rules: Rules) -> None:
    if len(dice) != rules.dice_count or any(
        die < 1 or die > rules.dice_sides for die in dice
    ):
        raise ValueError("roller returned dice outside the configured rules")