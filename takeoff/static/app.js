const $ = (selector) => document.querySelector(selector);

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
    for (const role of data.roles) {
      const button = document.createElement("button");
      button.className = "role-button";
      button.type = "button";
      const name = document.createElement("strong");
      name.textContent = role.id;
      const brief = document.createElement("span");
      brief.textContent = role.brief;
      button.append(name, brief);
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
  $("#activity").hidden = true;
  $(".game-layout").hidden = true;
  $("#session-error").hidden = false;
  document.title = "GAME EXPIRED // TAKEOFF";
}

function renderGame(view) {
  $("#role").textContent = view.human_actor;
  $("#turn").textContent = `TURN ${view.turn}`;
  $("#chits").textContent = `${view.fail_chits} FAIL CHIT${view.fail_chits === 1 ? "" : "S"}`;
  $("#private-brief").textContent = view.private_brief;
  renderList($("#objectives"), view.objectives, (item) => item);
  renderFacts(view.facts);
  renderOutcomes(view.outcomes, view.human_actor);

  const waiting = view.status === "waiting_human";
  $("#composer").hidden = !waiting;
  $("#proposal").disabled = !waiting;
  $("#submit").disabled = !waiting;
  if (waiting && view.draft && $("#proposal").value !== view.draft) {
    $("#proposal").value = view.draft;
  }
  if (waiting) pendingSubmission = null;

  const feedback = view.parse_error || view.feedback;
  $("#feedback").hidden = !feedback;
  $("#feedback").textContent = feedback || "";
  $("#activity").textContent = statusText(view.status, view.human_actor);
}

function statusText(status, actor) {
  return ({
    starting: "Starting game...",
    waiting_human: `${actor}: submit your action.`,
    parsing: "Parsing your action...",
    running: "LLM actors and the umpire are advancing the game...",
    completed: "Game complete.",
    failed: "The game stopped. Refreshing will not restart it.",
  })[status] || status;
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

function renderOutcomes(outcomes, humanActor) {
  $("#outcome-count").textContent = `${outcomes.length} outcome${outcomes.length === 1 ? "" : "s"}`;
  $("#outcomes").replaceChildren(...[...outcomes].reverse().map((outcome) => {
    const article = document.createElement("article");
    article.className = `outcome actor-${outcome.actor_id.toLowerCase()}`;
    if (outcome.actor_id === humanActor) article.classList.add("outcome-human");
    const meta = element("div", "outcome-meta", `TURN ${outcome.turn} // ${outcome.actor_id}`);
    if (outcome.private) meta.append(element("span", "private-tag", "PRIVATE"));
    article.append(meta, element("h2", "", outcome.action));
    if (outcome.intended_result) article.append(element("p", "judgment", `INTENT: ${outcome.intended_result}`));
    if (outcome.reasons.length) article.append(textList("ol", outcome.reasons));
    if (outcome.cons.length) article.append(element("p", "judgment", "UMPIRE RISKS"), textList("ul", outcome.cons));
    article.append(element("p", "judgment", `SUPPORT ${outcome.support} // OPPOSITION ${outcome.opposition} // MOD ${signed(outcome.modifier)} // 2D6 [${outcome.roll}]`));
    article.append(element("p", `result${outcome.success ? "" : " failure"}`, `${outcome.success ? "SUCCESS" : "FAILURE"} // ${outcome.severity.toUpperCase()}`));
    article.append(element("p", "narration", outcome.narration));
    for (const fact of outcome.facts) article.append(element("p", "new-fact", `+ [${fact.id}] ${fact.text}`));
    return article;
  }));
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
