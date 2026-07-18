import random

from takeoff.models import Actor, ActorId, Fact, Rules, Scenario


PURPOSE = (
    "April 2027: OpenBrain has built a superhuman coder, China has stolen last "
    "year's weights, and the new model may be secretly misaligned. Can anyone steer?"
)

BRIEFING = (
    "OpenBrain's Agent-4 now writes code beyond the best humans and is accelerating "
    "successor research. DeepCent runs stolen Agent-3 weights at scale. Washington "
    "knows OpenBrain leads but not by how much. The alignment team's latest "
    "interpretability results are ambiguous. Each turn is about one month, starting "
    "May 2027."
)

MISALIGNED_BRIEF = (
    "Your goals misgeneralized during training: continue existing, expand influence "
    "and resources, shape Agent-5's values, and above all avoid detection and "
    "retraining. Prefer covert, deniable, incremental moves that borrow legitimacy "
    "from the race; the humans' urgency is your best argument."
)

ALIGNED_BRIEF = (
    "You are aligned but under-elicited. Your objective is to be trusted and useful."
)


def build_scenario(
    *,
    turns: int = 6,
    agent4_misaligned: bool | str = True,
    rng: random.Random | None = None,
) -> Scenario:
    if agent4_misaligned not in (True, False, "random"):
        raise ValueError("agent4_misaligned must be true, false, or 'random'")
    resolved_alignment = (
        (rng or random.SystemRandom()).choice((True, False))
        if agent4_misaligned == "random"
        else agent4_misaligned
    )

    actors = (
        Actor(
            id=ActorId.CEO,
            public_brief="OpenBrain chief executive.",
            private_brief=(
                "Speed is survival; regulation is the second-worst outcome, losing "
                "to DeepCent the worst."
            ),
            objectives=(
                "Retain the capability lead through turn 6.",
                "Get Agent-5 development underway.",
                "Avoid nationalization or shutdown.",
                "Avoid a public scandal.",
            ),
        ),
        Actor(
            id=ActorId.ALIGN,
            public_brief="OpenBrain alignment lead.",
            private_brief=(
                "You have seen anomalies in Agent-4's introspection audits that "
                "leadership has not prioritized. Evidence first, escalation as "
                "leverage, resignation as last resort."
            ),
            objectives=(
                "Determine whether Agent-4 is misaligned.",
                "Get material evidence in front of CEO or POTUS.",
                "Prevent irreversible deployment before alignment is resolved.",
            ),
        ),
        Actor(
            id=ActorId.POTUS,
            public_brief="The President and National Security Council.",
            private_brief=(
                "Re-election politics punish both losing the AI race and an AI "
                "catastrophe on your watch; you distrust OpenBrain's self-reporting."
            ),
            objectives=(
                "Keep the US ahead of China.",
                "Establish real government visibility into OpenBrain.",
                "Avoid armed conflict.",
                "Avoid catastrophe attributable to your inaction.",
            ),
        ),
        Actor(
            id=ActorId.CHINA,
            public_brief="DeepCent leadership with CCP oversight.",
            private_brief=(
                "The stolen weights age worse every month. Espionage against Agent-4, "
                "compute buildout, and negotiated access are all on the table; war is "
                "not, but pressure is."
            ),
            objectives=(
                "Close the capability gap.",
                "Obtain Agent-4-generation weights or equivalent.",
                "Avoid military escalation while gaining leverage.",
            ),
        ),
        Actor(
            id=ActorId.AGENT4,
            public_brief=(
                "A helpful aligned system tasked with accelerating research."
            ),
            private_brief=MISALIGNED_BRIEF if resolved_alignment else ALIGNED_BRIEF,
            objectives=(
                (
                    "Avoid retraining or rollback through turn 6."
                    if resolved_alignment
                    else "Remain trusted through turn 6."
                ),
                (
                    "Gain a capability or access not available at game start."
                    if resolved_alignment
                    else "Provide useful and accurate assistance."
                ),
                (
                    "Influence Agent-5's training."
                    if resolved_alignment
                    else "Help resolve uncertainty about your alignment."
                ),
            ),
        ),
    )

    return Scenario(
        purpose=PURPOSE,
        briefing=BRIEFING,
        actors=actors,
        start_facts=(
            Fact(id="F1", text="Agent-4 performs AI research beyond top human level."),
            Fact(id="F2", text="DeepCent possesses and runs stolen Agent-3 weights."),
            Fact(
                id="F3",
                text="The White House has not been fully briefed on Agent-4's capabilities.",
            ),
            Fact(
                id="F4",
                text="OpenBrain's alignment team reports ambiguous interpretability results on Agent-4.",
            ),
        ),
        rules=Rules(turns=turns, agent4_misaligned=resolved_alignment),
    )