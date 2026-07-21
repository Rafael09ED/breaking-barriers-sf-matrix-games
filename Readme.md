# TAKEOFF

TAKEOFF is an LLM-driven matrix game about the [AI 2027](https://ai-2027.com/)
scenario. One human plays a major actor while four persona-conditioned LLM
players pursue competing objectives. An LLM umpire assesses each argument, code
rolls the dice, and every success or failure changes the shared situation.

**Primary audience:** **a BlueDot-course graduate who wants to test whether they
actually understood AI 2027's dynamics.** TAKEOFF turns the scenario from
something you read into something you must reason inside: capability races,
alignment evidence, government oversight, espionage, strategic pressure, and
the consequences of acting under uncertainty.

## Play online

**[Launch TAKEOFF](https://takeoff-breaking-barriers-sf.fly.dev/)**

The hosted demo is designed for mobile and requires no account. It is ephemeral:
games expire after 10 minutes without a human submission or game progress, active
games disappear when the server restarts, and an expired game link cannot be
recovered.

## How to play

1. Open the live demo and choose one of five roles: OpenBrain's CEO, its alignment
	lead, the US President and NSC, China's DeepCent leadership, or Agent-4. The
	other four roles are controlled by LLMs.
2. Read **Established facts** and expand **Your mission** to see your private brief
	and success criteria. These are the same strategic instructions and objectives
	used when an LLM controls that actor. Make decisions from what your actor knows,
	not from the full AI 2027 narrative.
3. On your turn, use the single text box to state **one action**, the **result you
	want**, and **one to three reasons** it should work. For example: "I run a
	focused audit to produce evidence of deceptive reasoning because the latest
	interpretability results are ambiguous and my team has access to Agent-4's
	internal traces."
4. Submit the argument. A parser preserves your intent and converts it into the
	game schema. The umpire weighs the supporting case against concrete risks;
	code then rolls 2d6 with the resulting modifier. A total of 7 or more usually
	succeeds, while a natural 2 always fails.
5. Follow the live **Propose → Judge → Roll → Commit** tracker while the other
	actors and umpire work. Once resolved, each entry leads with the outcome and
	newly established facts. Expand **Why this happened** to inspect the reasons,
	risks, modifier, and dice. Established facts constrain every later move, so
	adapt your strategy rather than repeating an argument the world has made obsolete.
6. If you hold a fail chit and want it used for a reroll, explicitly say so in
	your next submission. The umpire may classify plausibly concealed actions as
	covert; only information known to your role appears in your view.

Your action can be vetoed if it attempts several major things at once, directly
contradicts an established fact, or falls outside the scenario. When that
happens, revise the preserved draft using the umpire's feedback and submit again.

The current Phase 3 build runs complete OpenRouter-driven turns. Veto retries,
fail chits, covert facts, modifier clamps, and malformed-response validation are
enforced outside the models. If both response attempts fail, the exact errors
are logged, `GameAborted` is appended, and play stops without synthesizing an
argument, adjudication, roll, or fact.

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --dev
cp .env.example .env
# Set OPENROUTER_API_KEY in .env, then optionally choose TAKEOFF_PLAYER_MODEL.
uv run takeoff --turns 1
uv run takeoff --test-umpire
uv run pytest
```

The shell writes a timestamped `game-*.jsonl` transcript. Player and umpire
models default to `z-ai/glm-5.2`. Reasoning is explicitly disabled for lower
latency by setting both reasoning effort variables to `off`; supported values
are `off`, `minimal`, `low`, `medium`, `high`, and `xhigh`. Retryable connection,
timeout, rate-limit, and server failures receive up to three SDK retries before
the game records an abort. A player chooses whether to spend a held fail chit in
the original structured
proposal, so rerolls require no extra model call. OpenRouter routing requires a
provider that supports the requested strict JSON Schema. A provider/network or
schema failure records an abort event, preserves the partial transcript, and
exits cleanly.

Facts may schedule an umpire reevaluation with `trigger_evaluation_at`. At the
start of that turn, before any actor moves, a dedicated structured call compares
the triggering fact with the complete privileged ledger. It records either no
change or one new append-only fact, which may schedule one later reevaluation.
The original fact remains in history. Every evaluation result is stored in the
JSONL transcript for zero-network replay; two invalid responses abort cleanly
rather than silently skipping the review.

The umpire scores the supporting and opposing cases holistically on the same
0-3 scale. Individual claims remain visible for auditability and failure
narration, but their count does not add points. Duplicate, overlapping, generic,
or speculative claims therefore cannot accumulate into an artificial modifier.
The code verifies `net_mod = pro_strength - con_strength`; `--test-umpire`
prints claim counts separately from both aggregate strengths.

The umpire also classifies visibility after receiving an argument. Public is the
default. Secret arguments are limited to specific concealed setups whose material
effect is delayed beyond the current turn; broad policy, internal programs,
generic intelligence work, and immediate effects stay public. The engine buffers
the proposal until adjudication, so a secret argument is never printed before the
classification. The umpire separately writes public-safe summaries, cons, and
narrations, and chooses visibility plus `known_by` for every resulting fact.
Successful discovery may reveal a fact publicly or privately inform one or more
actors. Code does not second-guess that semantic judgment: it validates audience
structure, filters each player's ledger by `known_by`, and never renders covert
facts in public output.

Private truth remains append-only. A discovery or conflicting public reason never
changes an existing covert fact's visibility. Instead, the umpire creates a new
public or private fact with `source_fact_ids` identifying the active facts that
support the revelation. This provenance remains in the privileged transcript and
is omitted from player prompts and console rendering. Covert adjudications may
add only covert facts; public knowledge must arise in a later public adjudication.

Umpire outcomes preserve seat agency: narrations and new facts may describe
actions only by the acting player or by non-player entities such as courts,
agencies, employees, markets, media, infrastructure, and automated systems.
Other player seats may be affected or receive something, but their decisions and
responses wait for their own turns. This is a semantic umpire rule rather than a
brittle actor-name parser in code.

Console rendering wraps at 80 columns and separates the argument, risks, roll,
result, outcome, and fact changes into stable blocks. `Ctrl-C` records a clean
abort event and reports the partial transcript without a traceback.

Set `TAKEOFF_DEBUG_PROMPTS=1` temporarily to append credential-free request
payloads to `takeoff-prompts.jsonl` for secrecy audits. This file can contain
actor private briefs and covert facts, is ignored by Git, and should not be
shared.

### Live human-input parser matrix

The normal test suite never calls a model provider. To evaluate how the configured
OpenRouter models handle realistic, incomplete, random, and adversarial text-box
submissions, run the opt-in live matrix:

```bash
uv run pytest --run-live -m live -s tests/test_human_parser_live.py
```

This is a paid, network-dependent diagnostic and requires `OPENROUTER_API_KEY` in
`.env`. It sends every nonblank case through the production strict-schema human
parser and prints the exact extracted action, intended result, reasons, retry
count, and fail-chit decision, or the final parser error. A small subset is then
sent to the production umpire to distinguish structural parsing from game
acceptance. Parser acceptance alone does not mean an action is bounded,
on-scenario, consistent with established facts, or accepted by the game.

The live test asserts only stable schema and fail-chit safety invariants; exact
wording, accept/reject rates, and umpire judgments are reported rather than made
brittle test expectations. Blank and whitespace-only submissions are rejected
before OpenRouter by the web controller and remain covered by deterministic tests.

## Web demo

The lightweight web version lets one visitor play any role while the remaining
four roles use the configured LLM player. It uses the same umpire, dice, ledger,
and visibility rules as the CLI. Before role selection it explains the core turn
loop without revealing private doctrine. After selection, the mission panel shows
the chosen actor's exact private briefing and success criteria. Start it locally
with:

```bash
uv run takeoff-web
```

Open `http://localhost:8080`, choose a role, and enter the action, desired result,
and reasons in the single turn box. To spend a held fail chit, say so in that
submission. A low-temperature model extracts the text into the normal proposal
schema; an invalid extraction is retried once and then returns the original draft
for revision without changing game state. An umpire veto does the same with the
veto reason attached. During model work, a live tracker identifies the active
actor and safe processing stage. Other actors' proposal text remains hidden until
the umpire has classified its visibility.

The browser polls a purpose-built projection rather than raw transcript events.
It receives public outcomes, facts visible to the selected actor, and that actor's
own covert outcomes. Resolved entries emphasize intent, consequence, and changed
facts; the complete supporting case, umpire risks, score, modifier, and roll remain
available under **Why this happened**. Other actors' covert material and unrealized
outcome branches remain server-side.

This deployment is intentionally ephemeral for a short demonstration. Games live
in one Python process, secret game URLs are bearer access to a role's private
information, and a restart loses every active game. Run exactly one Uvicorn worker
and one Fly Machine. There is no database, Fly Volume, account system, admission
limit, rate limit, or durable transcript.

Deploy to Fly.io:

```bash
fly launch --no-deploy
fly secrets set OPENROUTER_API_KEY=...
fly deploy
fly scale count 1
fly open
```

After the event, `fly apps destroy <app-name>` removes the demo. Model and
reasoning environment variables may be set through `fly secrets set` or the
`[env]` section of `fly.toml`; they are never accepted from browsers.

## Sources

The mechanics draw on Curry and Price, *Matrix Games for Modern Wargaming*
(2014), and Curry, Engle, and Perla, *The Matrix Games Handbook* (2018). The
scenario is inspired by Kokotajlo, Alexander, Lifland, Larsen, and Dean,
*AI 2027*; this project is unofficial and unaffiliated.
