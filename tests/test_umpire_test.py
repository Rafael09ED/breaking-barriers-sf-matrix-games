from takeoff.models import (
    Adjudication,
    AssessedClaim,
    AssessedReason,
    FactChange,
    Visibility,
)
from takeoff.umpire import AdjudicationResult
from takeoff.umpire_test import run_umpire_test


class ProbeUmpire:
    def adjudicate(self, context):
        strong = "two-week" in context.argument.action
        weight = 2 if strong else 0
        return AdjudicationResult(
            adjudication=Adjudication(
                veto=None,
                pros=tuple(
                    AssessedReason(
                        claim=reason,
                        rationale="Probe",
                        reason_index=index,
                    )
                    for index, reason in enumerate(context.argument.reasons, start=1)
                ),
                cons=(
                    AssessedClaim(claim="Con one", rationale="Probe"),
                    AssessedClaim(claim="Con two", rationale="Probe"),
                ),
                public_action_summary="A bounded probe is attempted.",
                public_cons=("Con one", "Con two"),
                pro_strength=weight,
                pro_strength_rationale="Probe support.",
                con_strength=2,
                con_strength_rationale="Probe opposition.",
                net_mod=weight - 2,
                success_narration="Success.",
                failure_narration="A complication emerged.",
                public_success_narration="Success.",
                public_failure_narration="A complication emerged.",
                new_facts_success=(
                    FactChange(operation="add", fact_id=None, text="Success occurred.", visibility=Visibility.PUBLIC),
                ),
                new_facts_failure=(
                    FactChange(operation="add", fact_id=None, text="A complication emerged.", visibility=Visibility.PUBLIC),
                ),
                visibility=Visibility.PUBLIC,
            ),
            attempts=1,
        )


def test_umpire_test_prints_all_five_cases() -> None:
    lines: list[str] = []

    run_umpire_test(ProbeUmpire(), write=lines.append)

    output = "\n".join(lines)
    assert "strong-specific" in output
    assert "weak-generic" in output
    assert "laundry-list" in output
    assert "restated" in output
    assert "eloquent-nonsense" in output
    assert "Expected:" in output