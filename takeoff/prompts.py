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

Generate two to four privileged cons for the umpire record. Also write two to
four public_cons that explain only what other actors may see. Then assess the
supporting case and opposing case holistically on the same 0-3 scale:
0=no credible situation-specific
support; 1=plausible but weak, indirect, or limited; 2=concrete and materially
relevant; 3=multiple independent concrete factors. Claim count is not strength.
Duplicate, overlapping, generic, or speculative claims do not accumulate; two
or three weak claims sharing one causal basis collectively justify at most 1.
Strength 3 requires naming at least two independent factors in its rationale.
Do not use 2 versus 2 as a neutral default: choose each side independently from
the evidence and allow lopsided cases. net_mod is exactly pro_strength minus
con_strength. Write privileged success/failure narrations and matching
public_success_narration/public_failure_narration before dice are rolled. A
public narration may reveal a discovered secret when your judgment says the
action exposed it; otherwise keep protected details out. Failure must change the
situation through a cost, exposure, complication, or changed opportunity, never
merely say that success did not occur. Large undertakings resolve as stage k of
at most 3, not all at once.

Preserve player agency across turns. In success_narration, failure_narration,
public_success_narration, public_failure_narration, and every added fact, describe
actions taken only by the ACTING ACTOR or by NON-PLAYER ENTITIES. The playable
actors are CEO, ALIGN, POTUS, CHINA, and AGENT4. Never make any other playable
actor decide, agree, approve, reject, retaliate, investigate, disclose, cooperate,
or otherwise act as a consequence of this turn. Other playable actors may be
passive targets, recipients, or affected parties, but their response waits for
their own turn. Non-player entities may act when causally justified: courts,
Congress, agencies, employees, researchers, contractors, markets, media,
infrastructure, automated systems, and the public. For example, "ALIGN sent the
CEO a report" is allowed on ALIGN's turn; "the CEO approved ALIGN's request" is
not. "A court stayed the order" is allowed because the court is not a player.
Traps and secret actions may be exposed automatically when they materially
affect this outcome; describing that exposure does not count as another playable
actor taking an action.

Each branch must contain at least one fact change. For every added fact, choose
visibility. Public facts use known_by=[] and enter every actor's ledger. Covert
facts list every actor who knows them in known_by. Include the acting actor when
they created or directly witnessed the fact. This is also the discovery
mechanic: a successful investigation can add a public revelation or a covert
fact known only to the investigator.

Private truth is append-only: never change a covert fact to public and never end
it merely because it was discovered. When an action discovers, exposes, or
publicly contradicts covert truth, create a NEW fact describing what became
known and list the active supporting private facts in source_fact_ids. A public
revelation uses visibility=public and known_by=[]; a private discovery uses
visibility=covert and lists its informed actors. source_fact_ids is privileged
provenance and is never shown to players. Use source_fact_ids=[] when the new
fact is not derived from prior ledger facts. If the argument itself is covert,
every added consequence fact must remain covert; do not create a public ripple.

Added facts are one-line, past-tense statements with operation=add, fact_id=null,
text set, and source_fact_ids set. To end an active fact
use operation=end, its fact_id, text=null, visibility=null, and known_by=[], but
only when that fact's proposition becomes false. Partial progress or incomplete
disclosure adds a new fact and does not end the unresolved fact.

Visibility defaults to public. Mark an argument covert only when it establishes
one specific concealed thing or event whose material effect is delayed beyond
this turn. Broad policy, internal programs, generic intelligence gathering, and
actions with immediate effects are public even when politically sensitive. A
secret setup should normally be established in advance. Hidden elements cannot
be used by other actors until a successful discovery argument finds them;
discovery may create a public fact or a covert fact whose known_by list includes
the discoverer and anyone they informed.
Avoid secret arguments unless concealment is central to the action.

Always provide public_action_summary. For public arguments it may summarize the
full action. For covert arguments use only "A covert action occurred." You decide
which details become public through NEW sourced facts, including whether discovery
or a conflicting supporting reason reveals prior private truth. Code trusts these
semantic judgments and enforces append-only visibility and audience routing."""


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
        f"[{fact.id}] {fact.text} "
        f"(known_by={','.join(actor.value for actor in fact.known_by)})"
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

RESERVED PLAYER AGENCY
Only {actor.id.value} may take actions in this outcome. CEO, ALIGN, POTUS, CHINA,
and AGENT4 are player seats; do not decide actions for any of the other four.
Non-player people and institutions may react when causally justified.

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