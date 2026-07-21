const $ = (selector) => document.querySelector(selector);

const ROLE_LABELS = {
  CEO: "OpenBrain CEO",
  ALIGN: "Alignment Lead",
  POTUS: "US President & NSC",
  CHINA: "DeepCent Leadership",
  AGENT4: "Agent-4",
};

const TURN_STAGES = ["proposing", "adjudicating", "rolling", "committing"];

async function readJson(response) {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
}

async function startIndex() {
  try {
    const data = await readJson(await fetch("/api/roles"));
    $("#purpose").textContent = data.purpose;
    $("#briefing").textContent = data.briefing;
    $("#rules-summary").textContent = `${data.mechanics.turns} turns · 2d6 + modifier · ${data.mechanics.target}+ succeeds`;
    for (const role of data.roles) {
      const button = document.createElement("button");
      button.className = "role-button";
      button.type = "button";
      const name = document.createElement("strong");
      name.textContent = role.label;
      const code = document.createElement("small");
      code.textContent = role.id;
      const brief = document.createElement("span");
      brief.textContent = role.brief;
      button.append(name, code, brief);
      button.addEventListener("click", () => createGame(role.id, button));
      $("#roles").append(button);
    }
  } catch (error) {
    $("#start-error").hidden = false;
    $("#start-error").textContent = error.message;
  }
}

async function createGame(actorId, button) {
  button.disabled = true;
  try {
    const game = await readJson(await fetch("/api/games", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({actor_id: actorId}),
    }));
    location.assign(game.url);
  } catch (error) {
    button.disabled = false;
    $("#start-error").hidden = false;
    $("#start-error").textContent = error.message;
  }
}

function gameToken() {
  return location.pathname.split("/").filter(Boolean).at(-1);
}

let viewVersion = null;
let pendingSubmission = null;
let pollTimer = null;
let pollingActive = true;

async function pollGame() {
  const query = viewVersion === null ? "" : `?after_version=${viewVersion}`;
  try {
    const response = await fetch(`/api/games/${gameToken()}${query}`);
    if (response.status === 404) {
      pollingActive = false;
      showExpiredGame();
      return;
    }
    if (response.status === 204) return;
    const view = await readJson(response);
    if (view.status === "starting") {
      viewVersion = view.version;
      $("#activity").textContent = "Starting game...";
      return;
    }
    viewVersion = view.version;
    renderGame(view);
  } catch (error) {
    $("#activity").textContent = error.message;
  } finally {
    if (pollingActive) pollTimer = setTimeout(pollGame, 1000);
  }
}

function showExpiredGame() {
  $("#composer").hidden = true;
  $("#activity-panel").hidden = true;
  $(".game-layout").hidden = true;
  $("#session-error").hidden = false;
  document.title = "GAME EXPIRED // TAKEOFF";
}

function renderGame(view) {
  $("#role").textContent = ROLE_LABELS[view.human_actor] || view.human_actor;
  $("#turn").textContent = `TURN ${view.turn}/${view.total_turns}`;
  $("#chits").textContent = `${view.fail_chits} FAIL CHIT${view.fail_chits === 1 ? "" : "S"}`;
  $("#public-brief").textContent = view.public_brief;
  $("#private-brief").textContent = view.private_brief;
  $("#shared-briefing").textContent = view.shared_briefing;
  renderList($("#objectives"), view.objectives, (item) => item);
  renderFacts(view.facts);
  renderOutcomes(view.outcomes, view.human_actor, view.progress, view.status);

  const waiting = view.status === "waiting_human";
  $("#composer").hidden = !waiting;
  $("#proposal").disabled = !waiting;
  $("#submit").disabled = !waiting;
  if (waiting && view.draft && $("#proposal").value !== view.draft) {
    $("#proposal").value = view.draft;
  }
  if (waiting) pendingSubmission = null;

  $("#input-note").textContent = view.fail_chits > 0
    ? "To reroll a failure, explicitly say to spend your fail chit."
    : "The umpire decides whether the action is covert.";

  const feedback = view.parse_error || view.feedback;
  $("#feedback").hidden = !feedback;
  $("#feedback").textContent = feedback || "";
  renderProgress(view);
}

function statusText(status, progress) {
  if (status === "running" && progress) {
    return ({
      proposing: "Formulating one bounded action...",
      adjudicating: "The umpire is weighing support and risks...",
      rolling: "The modifier is set. Rolling 2d6...",
      committing: "Committing the consequence to the shared world...",
    })[progress.stage];
  }
  return ({
    starting: "Starting game...",
    waiting_human: "Your move. Submit one action and its case.",
    parsing: "Interpreting your action without changing its intent...",
    running: "The game is advancing...",
    completed: "Game complete.",
    failed: "The game stopped. Refreshing will not restart it.",
  })[status] || status;
}

function renderProgress(view) {
  const progress = view.progress;
  const actor = progress ? (ROLE_LABELS[progress.actor_id] || progress.actor_id) : "GAME";
  $("#activity-actor").textContent = view.status === "waiting_human" ? "YOUR TURN" : actor;
  $("#activity").textContent = statusText(view.status, progress);

  let activeStage = progress?.stage || null;
  if (view.status === "parsing" || view.status === "waiting_human") activeStage = "proposing";
  const activeIndex = TURN_STAGES.indexOf(activeStage);
  for (const item of $("#turn-steps").children) {
    const itemIndex = TURN_STAGES.indexOf(item.dataset.stage);
    item.classList.toggle("active", itemIndex === activeIndex);
    item.classList.toggle("done", activeIndex > itemIndex);
  }
}

function renderFacts(facts) {
  $("#fact-count").textContent = facts.length;
  $("#facts").replaceChildren(...facts.map((fact) => {
    const item = document.createElement("li");
    item.textContent = `[${fact.id}] ${fact.text}`;
    if (fact.visibility === "covert") {
      item.className = "fact-private";
      item.textContent = `[PRIVATE ${fact.id}] ${fact.text}`;
    }
    return item;
  }));
}

function renderOutcomes(outcomes, humanActor, progress, status) {
  const expandedOutcomes = new Set(
    [...document.querySelectorAll(".outcome-details[open]")]
      .map((details) => details.closest(".outcome")?.dataset.outcomeKey)
      .filter(Boolean),
  );
  $("#outcome-count").textContent = `${outcomes.length} outcome${outcomes.length === 1 ? "" : "s"}`;
  $("#empty-transcript").hidden = outcomes.length > 0 || (status === "running" && progress);
  const entries = [...outcomes].reverse().map((outcome) => {
    const article = document.createElement("article");
    article.className = `outcome actor-${outcome.actor_id.toLowerCase()}`;
    article.dataset.outcomeKey = `${outcome.turn}:${outcome.actor_id}`;
    if (outcome.actor_id === humanActor) article.classList.add("outcome-human");
    const actor = ROLE_LABELS[outcome.actor_id] || outcome.actor_id;
    const meta = element("div", "outcome-meta", `TURN ${outcome.turn} // ${actor}`);
    if (outcome.private) meta.append(element("span", "private-tag", "PRIVATE"));
    article.append(meta, element("p", `result${outcome.success ? "" : " failure"}`, `${outcome.success ? "SUCCESS" : "FAILURE"} // ${outcome.severity.toUpperCase()}`));
    article.append(element("h2", "", outcome.action));
    if (outcome.intended_result) article.append(element("p", "intent", `INTENDED: ${outcome.intended_result}`));
    article.append(element("p", "narration", outcome.narration));
    for (const fact of outcome.facts) article.append(element("p", "new-fact", `+ [${fact.id}] ${fact.text}`));
    const details = document.createElement("details");
    details.className = "outcome-details";
    details.open = expandedOutcomes.has(article.dataset.outcomeKey);
    details.append(element("summary", "", "Why this happened"));
    if (outcome.reasons.length) details.append(element("p", "judgment", "PLAYER'S CASE"), textList("ol", outcome.reasons));
    if (outcome.cons.length) details.append(element("p", "judgment", "UMPIRE RISKS"), textList("ul", outcome.cons));
    details.append(element("p", "roll-line", `SUPPORT ${outcome.support} // OPPOSITION ${outcome.opposition} // MOD ${signed(outcome.modifier)} // 2D6 [${outcome.roll}]`));
    article.append(details);
    return article;
  });
  if (status === "running" && progress) entries.unshift(renderActiveTurn(progress));
  $("#outcomes").replaceChildren(...entries);
}

function renderActiveTurn(progress) {
  const article = document.createElement("article");
  article.className = `outcome outcome-progress actor-${progress.actor_id.toLowerCase()}`;
  const actor = ROLE_LABELS[progress.actor_id] || progress.actor_id;
  const meta = element("div", "outcome-meta", `IN PROGRESS // ${actor}`);
  if (progress.private) meta.append(element("span", "private-tag", "PRIVATE"));
  article.append(meta, element("h2", "", progress.action || `${actor} is preparing an action.`));
  if (progress.intended_result) article.append(element("p", "intent", `INTENDED: ${progress.intended_result}`));
  article.append(element("p", "progress-note", statusText("running", progress)));
  return article;
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = text;
  return node;
}
function textList(tag, values) {
  const list = document.createElement(tag);
  for (const value of values) list.append(element("li", "", value));
  return list;
}
function renderList(parent, values, text) {
  parent.replaceChildren(...values.map((value) => element("li", "", text(value))));
}
function signed(value) { return value >= 0 ? `+${value}` : String(value); }

async function submitProposal() {
  const text = $("#proposal").value;
  if (!text.trim()) {
    $("#feedback").hidden = false;
    $("#feedback").textContent = "Describe an action before submitting.";
    return;
  }
  if (!pendingSubmission) pendingSubmission = crypto.randomUUID();
  $("#submit").disabled = true;
  $("#proposal").disabled = true;
  try {
    await readJson(await fetch(`/api/games/${gameToken()}/proposal`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text, submission_id: pendingSubmission}),
    }));
    $("#composer").hidden = true;
    $("#activity").textContent = "Parsing your action...";
  } catch (error) {
    $("#feedback").hidden = false;
    $("#feedback").textContent = error.message;
    $("#submit").disabled = false;
    $("#proposal").disabled = false;
  }
}

if (document.body.dataset.page === "index") startIndex();
if (document.body.dataset.page === "game") {
  $("#submit").addEventListener("click", submitProposal);
  pollGame();
}
