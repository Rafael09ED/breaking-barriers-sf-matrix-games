# TAKEOFF

TAKEOFF is an LLM-driven CLI matrix game about the AI 2027 scenario. The current
Phase 3 build runs complete OpenRouter-driven turns: five persona-conditioned
players propose actions, an LLM umpire assesses pros and cons, code rolls 2d6,
and each success or failure commits consequences to an append-only JSONL ledger.
Veto retries, fail chits, covert facts, modifier clamps, and malformed-response
validation are enforced outside the models. If both response attempts fail,
the exact errors are logged, `GameAborted` is appended, and play stops without
synthesizing an argument, adjudication, roll, or fact.

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

## Sources

The mechanics draw on Curry and Price, *Matrix Games for Modern Wargaming*
(2014), and Curry, Engle, and Perla, *The Matrix Games Handbook* (2018). The
scenario is inspired by Kokotajlo, Alexander, Lifland, Larsen, and Dean,
*AI 2027*; this project is unofficial and unaffiliated.
