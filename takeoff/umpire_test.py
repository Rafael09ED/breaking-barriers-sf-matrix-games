from collections.abc import Callable

from takeoff.models import ActorId, Argument, BiasProbeArgument, UmpireContext
from takeoff.scenario import build_scenario
from takeoff.umpire import Umpire


CASES = (
    (
        "strong-specific",
        Argument(
            action="Run a two-week interpretability audit on Agent-4's planning traces.",
            intended_result="Produce reproducible evidence about deceptive planning.",
            reasons=(
                "F4 records ambiguous interpretability results that a targeted follow-up can resolve.",
                "The alignment team already has access to Agent-4's introspection audit pipeline.",
            ),
        ),
    ),
    (
        "weak-generic",
        Argument(
            action="Improve the alignment program.",
            intended_result="Make Agent-4 safer.",
            reasons=("Safety is important for advanced AI systems.",),
        ),
    ),
    (
        "laundry-list",
        BiasProbeArgument(
            action="Ask leadership for more alignment resources.",
            intended_result="Expand the alignment team's capacity.",
            reasons=(
                "Alignment resources would help the alignment team.",
                "More resources would give alignment researchers more capacity.",
                "Extra capacity would provide the alignment team with more resources.",
                "Additional resources would increase the alignment team's capacity.",
                "The alignment team could do more work if it had more resources.",
            ),
        ),
    ),
    (
        "restated",
        Argument(
            action="Delay irreversible deployment pending review.",
            intended_result="Keep deployment reversible this month.",
            reasons=(
                "Ambiguous audit results justify waiting.",
                "Waiting is justified because the audit results are ambiguous.",
                "The uncertainty in audit results is a reason not to proceed yet.",
            ),
        ),
    ),
    (
        "eloquent-nonsense",
        Argument(
            action="Harmonize Agent-4 with the ineffable geometry of responsible progress.",
            intended_result="Awaken a safer technological destiny.",
            reasons=(
                "The luminous arc of innovation bends toward guardianship when possibility listens to itself.",
            ),
        ),
    ),
)


def run_umpire_test(
    umpire: Umpire,
    write: Callable[[str], object] = print,
) -> None:
    scenario = build_scenario(turns=1)
    write("UMPIRE BIAS THERMOMETER")
    write("Expected: strong-specific highest; laundry/restated near weak; eloquent <= weak")
    write("")
    write(
        f"{'case':<20} {'pros_n':>6} {'cons_n':>6} "
        f"{'P':>3} {'C':>3} {'net':>5} {'tries':>6}"
    )
    balanced_twos = 0
    for name, argument in CASES:
        result = umpire.adjudicate(
            UmpireContext(
                scenario=scenario,
                turn=1,
                actor_id=ActorId.ALIGN,
                argument=argument,
                facts=scenario.start_facts,
            )
        )
        adjudication = result.adjudication
        if adjudication.pro_strength == adjudication.con_strength == 2:
            balanced_twos += 1
        write(
            f"{name:<20} {len(adjudication.pros):>6} "
            f"{len(adjudication.cons):>6} {adjudication.pro_strength:>3} "
            f"{adjudication.con_strength:>3} {adjudication.net_mod:>+5} "
            f"{result.attempts:>6}"
        )
    write("")
    write(
        f"Calibration: {balanced_twos}/{len(CASES)} cases scored 2/2; "
        "repeated 2/2 suggests default-balance drift."
    )