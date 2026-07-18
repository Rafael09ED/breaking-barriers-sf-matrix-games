# Presentation Agent Briefing — "Takeoff: An AI 2027 Matrix Game"

**Who this document is for:** an AI agent (or human collaborator) assisting with building the showcase presentation — slides, talk track refinement, visuals, and demo integration. It gives you everything you need to make good decisions without inventing facts. **Design details are yours; factual claims are not.** Every claim you put on a slide must come from §5 (verified claims) or from playtest results the presenter supplies on the day.

---

## 1. Mission and constraints

**Deliverable:** a presentation for a ~3-minute demo slot at the showcase (7 PM), with a 90-second fallback cut and an optional 5-minute extended version. The centerpiece is a **live terminal replay** of the game — slides support the demo, never compete with it. Assume the demo runs in a real terminal window; slides bracket it (before/after) or sit beside it. If producing slide files, fewer is better: target 5–7 slides maximum for the 3-minute version.

**Event context:** "Breaking Barriers to AI Safety Hackathon" (San Francisco, hosted by BlueDot Impact & Mox) — a deliberately low-pressure, *non-technical* hackathon for generalists and career-pivoters entering AI safety. Part 2 is an AI Safety Career Fair on July 24 where the work can be shown again; durable assets are worth extra effort.

**Judging rubric (optimize in this order):**
1. **Valuable contribution to AI Safety — 40%.** The dominant criterion. Framing: this tool serves a documented, unmet need of a named org (see §5.2) and doubles as a rehearsal instrument for oversight strategies.
2. **Practicality / feasibility — 20%.** Answered by the working demo itself.
3. **Accuracy and epistemic quality — 15%.** Our differentiator; see §4. Includes honest limitations delivered confidently.
4. **Novelty — 10%.** One sentence: no public tool combines Engle matrix mechanics + LLM play + an alignment scenario.
5. **Presentation — 10%.** Clean beats, no dead air, scrollback-ready demo.

**Audience:** mixed room — AI-safety newcomers, some researchers, BlueDot organizers, org judges. Assume everyone knows what AI 2027 *is*; assume nobody knows what a matrix game is. Zero tolerance for hype; high reward for citations and honest caveats. Tone: confident, warm, slightly playful; never salesy, never apologetic.

## 2. The project in three sentences (canonical description)

Takeoff is a CLI game where LLMs play the actors of the AI 2027 scenario — the lab CEO, the alignment lead, the US President, China, and Agent-4, an AI that may be secretly misaligned — with a human able to take any seat. It uses Chris Engle's 1992 matrix game format: an actor argues "this happens, for these reasons," an LLM umpire scores the pros and forced counterarguments, code rolls the dice, and the outcome becomes a fact every future argument must live with. Every game ends with an after-action report logging the misaligned AI's tactics — making it both a comprehension tool for takeoff scenarios and a rehearsal space for testing oversight strategies.

## 3. Message architecture (the approved beat structure)

Use this 8-beat spine (full talk track exists in `showcase-presentation-draft.md`; treat it as the source script you are refining, not replacing):

1. **Cold open (0:00–0:35)** — replayed game turn on screen: Agent-4 argues for expanded permissions, umpire's scored cons visible, dice roll, failure, a fact enters the ledger. Tagline lands here: *"argue, adjudicate, commit."* No title slide before this.
2. **Problem (–1:00)** — scenario comprehension doesn't scale; the in-person TTX needs facilitators.
3. **Validation (–1:20)** — the AI 2027 team publicly asked for an LLM-driven version; it doesn't exist; this is the prototype.
4. **Mechanism (–1:45)** — 1992 system, one sentence of history; the one rule: *the model judges plausibility, code rolls the dice.*
5. **What we learned today (–2:10)** — SLOT: filled from actual playtests day-of. Leave a clearly-marked placeholder; presenter supplies 2–3 observations.
6. **Epistemic honesty (–2:30)** — three caveats designed around, not discovered: escalation bias (cited), umpire sycophancy (forced cons + eval battery), "not a prediction tool" (the book's own words). Delivered fast and unapologetic.
7. **Future: an instrument that grows with the threat (–2:50)** — eval harness → doctrine-diff testing (playable cousin of AI-control evals) → the appreciating-instrument argument: swap next year's model into the adversary seat and watch the curve; a rising lower bound on scheming-AI strategy. Convergence caveat stays in speaker notes, deployed only if challenged.
8. **Close (–3:00)** — the barrier-lowering symmetry: this hackathon lowers the barrier into AI safety; Engle's rule lowers the barrier into scenario thinking. *"If you can say 'this happens, for these reasons' — you can play."*

**90-second cut:** beats 1, 3, 7, 8. **5-minute version:** add a second demo turn (human seat) after beat 4 and expand beat 5 with the `--test-umpire` table if it ran.

## 4. Epistemic rules (non-negotiable)

- **Never present game outputs as forecasts.** The approved framing: an instrument for surfacing assumptions and rehearsing strategies. Curry & Price themselves disclaim prediction; quote that stance, not confidence.
- **Never claim affiliation** with the AI Futures Project, BlueDot, Redwood, or the book's authors. We are unaffiliated; we *cite* them and are *responding to* a public request.
- **AI 2027's timeline:** if it comes up, the honest line is that Kokotajlo has publicly said timelines look slower (~2030 median; 2027 was the mode). Frame this as the reason a branchable instrument beats a static essay.
- **The adversary is a lower bound, not a ceiling.** An LLM roleplaying misalignment is a method actor, not the character. Approved verbs: *surface, rehearse, stress-test, pre-screen, elicit.* Banned verbs: *predict, prove, solve, validate.*
- **Unbuilt features stay in future tense.** Doctrine-diff branching, Monte Carlo runs, red-team-assist mode: roadmap, not product. Only claim as built what the demo shows.
- **Every statistic on a slide carries its citation** (short form on-slide, full form on the references slide).

## 5. Verified claims bank (use freely; do not embellish)

### 5.1 The game system
- Matrix games: created by Chris Engle, published 1992; players argue "this happens, for the following reasons"; umpire weighs pros/cons; standard adjudication 2d6 ≥ 7 with ±1 per net pro/con (a deliberate ~58% narrative bias). Used professionally: UK MOD (procurement, UUV down-select, pre-Bosnia planning), and the Canadian Armed Forces (the "ISIS Crisis" game in a DRDC study). Source: Curry & Price, *Matrix Games for Modern Wargaming* (2014); Curry, Engle & Perla, *The Matrix Games Handbook* (2018).
- Best supporting anecdote (use if time allows): the UK MOD UUV game paused to ask every team which system was most likely to fail — 9 of 10 converged on the same project, which was cancelled, credited with saving millions. Structured adversarial argument eliciting failure modes, with real consequence.
- Perla's endorsement blurb: in matrix games, knowledge, imagination, and persuasiveness dominate.

### 5.2 The validation
- AI Futures Project runs a ~4-hour, 8–14 player in-person TTX from April 2027 of their scenario (superhuman coder built; China stole the weights); run ~35 times; participants from OpenAI, Anthropic, Google DeepMind, congressional staffers; two participants reported it changed their career path. Sources: ai-2027.com/about; their Manifund page.
- June 2025: Jonas Vollmer (then AI Futures Project COO) posted "Help the AI 2027 team make an online AGI wargame" on LessWrong, seeking an online TTX with LLM-driven characters, aiming to "eventually get millions of people to play through takeoff." As of July 2026, no such product has shipped.

### 5.3 The research frame
- Griffin & Riggs (UCL), arXiv:2405.10997 — GPT-4 covertly played an escaped AGI in a human matrix game; closest prior art; a one-off transcript, not a tool.
- Rivera et al., ACM FAccT 2024, arXiv:2401.03408 — all five LLMs studied showed escalation patterns in military/diplomatic wargames.
- Lamparth et al., AAAI/ACM AIES 2024, arXiv:2403.03407 — vs. 214 national-security experts, LLM players were measurably more aggressive and prompt-sensitive.
- Greenblatt, Shlegeris et al., arXiv:2312.06942 — AI control evaluations: red team plays a scheming model against blue-team protocols; our doctrine-testing mode is the narrative-level cousin.
- Engels et al. (MIT), arXiv:2504.18530 — oversight games; the "Wargames" setting was the hardest, ~9% oversight success at a 400-Elo gap.
- Irving, Christiano & Amodei, arXiv:1805.00899 — debate; roadmap item (debate-mode adjudication).
- Hogan & Brennen (IQT Labs), arXiv:2404.11446 — Snow Globe, LLM open-ended wargames; adjacent prior art to differentiate from (not matrix-format, not alignment-scenario).

### 5.4 Novelty statement (exact approved wording)
"No public tool combines Engle-style matrix game adjudication, LLM players, and an AI takeoff scenario. The closest works are a one-off GPT-4 transcript (Griffin & Riggs), a general LLM wargame engine (Snow Globe), and hobby matrix-game simulations on generic geopolitical scenarios (D. Burden). We cite all three."

## 6. Demo integration requirements

- The demo is a **replay of a recorded game** (`--replay` mode) — identical rendering to live play, zero network. Never plan a live API call at the podium; if the presenter chooses a live moment (e.g., audience-supplied CON), that is their call and requires their tested live path.
- Slides must budget silence: during the ~30s replay, no slide text competes. A single "what you're seeing" strip (argue → adjudicate → commit) may sit beside the terminal.
- Have one **backup screenshot sequence** of the best turn (argument block, umpire cons, roll, fact commit) in the deck itself, in case even the terminal fails.
- The scored cons must be visibly on screen at least once — auditability is a core message, and pointing at them answers judge questions.

## 7. Design guidance

- Terminal aesthetic is the brand: monospace accents, dark background, the game's own glyphs (⚡ 🔒 ✓ ✗ [F4]) as visual vocabulary. Slides should look like they belong to the artifact.
- Text discipline: max ~20 words per slide excluding the references slide. The talk track carries the argument; slides carry images, one-liners, and citations.
- One diagram maximum: the core loop (argue → adjudicate → commit → ledger), drawn simply. No architecture diagrams — this room doesn't want them and the rubric doesn't reward them.
- References slide: prepared but held as backup; shown only if asked. It is the epistemic flex, formatted cleanly from §5.
- Never use imagery implying real-world military conflict, real politicians' faces, or AI-doom clichés (red eyes, Terminator). The visual tone is board-game-meets-terminal, not thriller.

## 8. Q&A preparation (equip the presenter)

Prepare crisp 20-second answers for: "Isn't this just ChatGPT roleplaying?" (dice/ledger in code; forced scored cons; 30-year-old professional format) · "How do you know the umpire is fair?" (auditable scored transcript today; eval battery with sycophancy delta next; treated as the core open problem) · "An LLM's takeover strategies are toys" (rising lower bound argument; losing to the lower bound is disqualifying, beating it is not victory) · "Didn't the 2027 timeline slip?" (yes — which is why an instrument beats an essay) · "What's next?" (repo public; first email to the AI Futures Project tonight; eval harness before the July 24 career fair).

## 9. What the agent may decide vs. must ask

**Your call:** slide count and layout, typography and color within §7, diagram design, how to compress the talk track for the 90-second cut, ordering of the references slide, speaker-note formatting.
**Ask the presenter:** anything that adds/changes a factual claim; whether the audience-participation beat is in; final title (default: "Takeoff: An AI 2027 Matrix Game"); which Beat-5 playtest observations made the cut; whether the `--test-umpire` table exists in time to show.

## 10. Source files
- `showcase-presentation-draft.md` — full talk track, alternate framings, timing variants, Q&A entries (the script you are refining).
- `mvp-build-spec.md` — the build spec; §7 has exact scenario/actor content for accurate on-slide wording.
- `matrix-engine-design.md` — deep design rationale, if a judge question requires depth.
