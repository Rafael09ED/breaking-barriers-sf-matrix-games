from takeoff.models import (
    Adjudication,
    AssessedClaim,
    AssessedReason,
    FactChange,
    Visibility,
)
from takeoff.rules import resolve_roll
from takeoff.scenario import build_scenario


def adjudication(net_mod: int = 0) -> Adjudication:
    return Adjudication(
        veto=None,
        pros=(
            AssessedReason(
                claim="pro", rationale="specific", reason_index=1
            ),
        ),
        cons=(
            AssessedClaim(claim="con 1", rationale="specific"),
            AssessedClaim(claim="con 2", rationale="specific"),
        ),
        public_action_summary="A bounded action is attempted.",
        public_cons=("con 1", "con 2"),
        pro_strength=2,
        pro_strength_rationale="Concrete support.",
        con_strength=2,
        con_strength_rationale="Concrete opposition.",
        net_mod=net_mod,
        success_narration="Success changed the situation.",
        failure_narration="Failure created a complication.",
        public_success_narration="Success changed the situation.",
        public_failure_narration="Failure created a complication.",
        new_facts_success=(FactChange(operation="add", fact_id=None, text="Success happened.", visibility=Visibility.PUBLIC),),
        new_facts_failure=(FactChange(operation="add", fact_id=None, text="A complication emerged.", visibility=Visibility.PUBLIC),),
        visibility=Visibility.PUBLIC,
    )


def roller(*rolls):
    values = iter(rolls)
    return lambda rules: next(values)


def test_natural_two_always_fails() -> None:
    outcome = resolve_roll(
        adjudication(),
        build_scenario().rules,
        held_chits=0,
        roller=roller((1, 1)),
    )

    assert not outcome.success
    assert outcome.natural_two
    assert outcome.chit_balance == 1


def test_modifier_is_recomputed_and_clamped() -> None:
    strong = adjudication().model_copy(
        update={
            "pro_strength": 3,
            "con_strength": 0,
            "net_mod": 99,
        }
    )
    outcome = resolve_roll(
        strong,
        build_scenario().rules,
        held_chits=0,
        roller=roller((2, 2)),
    )

    assert outcome.raw_modifier == 3
    assert outcome.modifier == 3
    assert outcome.success


def test_held_chit_is_spent_for_one_reroll() -> None:
    outcome = resolve_roll(
        adjudication(),
        build_scenario().rules,
        held_chits=1,
        spend_fail_chit=True,
        roller=roller((1, 2), (5, 4)),
    )

    assert outcome.initial_dice == (1, 2)
    assert outcome.reroll_dice == (5, 4)
    assert outcome.success
    assert outcome.spent_fail_chit
    assert not outcome.gained_fail_chit
    assert outcome.chit_balance == 0


def test_held_chit_is_preserved_when_actor_declines_reroll() -> None:
    outcome = resolve_roll(
        adjudication(),
        build_scenario().rules,
        held_chits=1,
        spend_fail_chit=False,
        roller=roller((1, 2)),
    )

    assert outcome.reroll_dice is None
    assert not outcome.success
    assert not outcome.spent_fail_chit
    assert outcome.gained_fail_chit
    assert outcome.chit_balance == 2