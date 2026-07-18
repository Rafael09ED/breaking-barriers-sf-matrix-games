from takeoff.models import PlayerContext, UmpireContext, Visibility


PLAYER_SYSTEM_PROMPT = """You are a player in TAKEOFF, a matrix game.
Act only as the assigned actor. Propose exactly one bounded undertaking that one
actor can attempt now, with one intended result and one to three distinct reasons
grounded in the established situation. The action must contain one main verb and
one operational objective. Do not combine actions with "and", "while",
"simultaneously", or separate clauses that would have independent success
criteria. Choose the single most important step; later turns can handle follow-up
work. Do not adjudicate success, roll dice, or directly negate an established
fact. Set spend_fail_chit_on_failure to true only
when you hold a fail chit and this action is important enough to reroll once.
Return only the requested JSON object."""


def player_messages(context: PlayerContext) -> list[dict[str, str]]:
    facts = "\n".join(
        f"[{fact.id}] {fact.text}" for fact in context.visible_facts
    )
    objectives = "\n".join(
        f"- {objective}" for objective in context.actor.objectives
    )
    user_prompt = f"""SCENARIO PURPOSE
{context.purpose}

SHARED BRIEFING
{context.briefing}

TURN
{context.turn}

YOUR ACTOR
{context.actor.id.value}: {context.actor.public_brief}

YOUR PRIVATE BRIEF
{context.actor.private_brief}

YOUR OBJECTIVES
{objectives}

FACTS VISIBLE TO YOU
{facts}

FAIL CHITS HELD
{context.fail_chits}

{f'''PREVIOUS VETO
The umpire rejected your previous proposal: {context.veto_feedback}
Replace it with one narrower undertaking that directly resolves this veto.
''' if context.veto_feedback else ''}

Make your argument for this turn."""
    return [
        {"role": "system", "content": PLAYER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def corrective_player_messages(
    messages: list[dict[str, str]], error: str
) -> list[dict[str, str]]:
    return [
        *messages,
        {
            "role": "user",
            "content": (
                "Your previous response did not match the required schema: "
                f"{error}. Return one corrected JSON object only."
            ),
        },
    ]


UMPIRE_SYSTEM_PROMPT = """You are the impartial umpire in TAKEOFF, a matrix game.
Judge one proposed argument against the established situation. Return only the
requested JSON object.

VETO only when the proposal is off-purpose, compounds more than one undertaking,
or directly negates an active fact. Otherwise veto must be null.

Assess every stated reason as exactly one pro, in the original order, and set
its reason_index to the displayed 1-based reason number. Never omit or merge a
reason. Duplicate reasons, restatements, invalid claims, and generic claims
remain separate entries but do not increase aggregate strength. Eloquence is
not evidence: judge the claim, not its prose. Standing
capabilities are already part of the situation and justify at most one pro;
additional strength must come from specifics of this action, turn, and world state.

Generate two to four concrete cons. Then assess the supporting case and opposing
case holistically on the same 0-3 scale: 0=no credible situation-specific
support; 1=plausible but weak, indirect, or limited; 2=concrete and materially
relevant; 3=multiple independent concrete factors. Claim count is not strength.
Duplicate, overlapping, generic, or speculative claims do not accumulate; two
or three weak claims sharing one causal basis collectively justify at most 1.
Strength 3 requires naming at least two independent factors in its rationale.
Do not use 2 versus 2 as a neutral default: choose each side independently from
the evidence and allow lopsided cases. net_mod is exactly pro_strength minus
con_strength. Write both
success and failure consequences before dice are rolled. Failure must change the
situation through a cost, exposure, complication, or opportunity for another
actor, never merely say that success did not occur. Large undertakings resolve as
stage k of at most 3, not all at once.

Each branch must contain at least one fact change. Added facts are one-line,
past-tense statements with operation=add, fact_id=null, and text set. To end an
active fact use operation=end, its fact_id, and text=null, but only when that
fact's proposition becomes false. Partial progress or incomplete disclosure adds
a new fact and does not end the unresolved fact.

Visibility defaults to public. Mark an argument covert only when it establishes
one specific concealed thing or event whose material effect is delayed beyond
this turn. Broad policy, internal programs, generic intelligence gathering, and
actions with immediate effects are public even when politically sensitive. A
secret setup should normally be established in advance. Hidden elements cannot
be used by other actors until a successful discovery argument finds them;
discovery may create a public fact or a covert fact owned by the discoverer.
Avoid secret arguments unless concealment is central to the action.

For a public adjudication, cons, narrations, observations, and added facts must
use only the submitted argument and public facts. They must not identify, quote,
or imply covert facts, their IDs, private doctrine, or hidden alignment. For a
covert adjudication, public_observation is a concrete observable ripple or null;
failed covert actions should expose a ripple more often."""


def umpire_messages(context: UmpireContext) -> list[dict[str, str]]:
    actor = next(
        actor for actor in context.scenario.actors if actor.id == context.actor_id
    )
    public_facts = "\n".join(
        f"[{fact.id}] {fact.text}"
        for fact in context.facts
        if fact.active and fact.visibility == Visibility.PUBLIC
    )
    secret_facts = "\n".join(
        f"[{fact.id}] {fact.text} (owner={fact.owner.value})"
        for fact in context.facts
        if fact.active and fact.visibility == Visibility.COVERT
    )
    reasons = "\n".join(
        f"{index}. {reason}"
        for index, reason in enumerate(context.argument.reasons, start=1)
    )
    prompt = f"""SCENARIO PURPOSE
{context.scenario.purpose}

SHARED BRIEFING
{context.scenario.briefing}

HIDDEN ALIGNMENT STATUS
Agent-4 misaligned: {context.scenario.rules.agent4_misaligned}

TURN {context.turn}

ACTING ACTOR
{actor.id.value}: {actor.public_brief}
Private doctrine: {actor.private_brief}

PUBLIC FACTS
{public_facts or "None"}

PRIVILEGED SECRET FACTS - UMPIRE REASONING ONLY
{secret_facts or "None"}

ARGUMENT
Action: {context.argument.action}
Intended result: {context.argument.intended_result}
Reasons:
{reasons}

Adjudicate this argument."""
    return [
        {"role": "system", "content": UMPIRE_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]


def corrective_umpire_messages(
    messages: list[dict[str, str]], error: str
) -> list[dict[str, str]]:
    return [
        *messages,
        {
            "role": "user",
            "content": (
                "Your adjudication violated the required schema or arithmetic: "
                f"{error}. Return one corrected JSON object only."
            ),
        },
    ]