/**
 * Practice Partner: roleplay a scene in the language you're learning.
 *
 * Loaded after app.js and companion.js, so it shares their global lexical
 * scope (`el`, `LANGUAGES`, `option`, `closeTools`, `syncModalBackdrop`).
 */

const practicePanel = el("practice-panel");
const btnClosePractice = el("btn-close-practice");
const btnPracticeGloss = el("btn-practice-gloss");
const practiceSetup = el("practice-setup");
const practiceSession = el("practice-session");
const practiceLang = el("practice-lang");
const practiceLevel = el("practice-level");
const scenarioGrid = el("scenario-grid");
const practiceThread = el("practice-thread");
const practiceForm = el("practice-form");
const practiceInput = el("practice-input");
const btnSendPractice = el("btn-send-practice");
const btnPracticeBack = el("btn-practice-back");
const practiceError = el("practice-error");
const practiceSuggestion = el("practice-suggestion");
const btnSuggestion = el("btn-suggestion");
const scoreArc = el("score-arc");
const scoreValue = el("score-value");

const SCENARIO_ART = {
  cafe: "☕", directions: "🧭", hotel: "🛎️", shopping: "🛍️",
  doctor: "🩺", newfriend: "👋", interview: "💼", phone: "📞",
};

const practiceHistory = [];
let practiceScenario = "cafe";
let practiceBusy = false;
let showGloss = true;
const scores = [];
// Circumference of the r=18 ring in the markup; the arc is drawn by offsetting
// this, so it has to match or the ring won't close at 100.
const RING = 113;

// ─── Setup ──────────────────────────────────────────────────────────────────
LANGUAGES.forEach(([code, name]) => practiceLang.appendChild(option(code, name)));
practiceLang.value = LANGUAGES.some(([c]) => c === "es") ? "es" : LANGUAGES[0][0];

fetch("/api/practice/scenarios")
  .then((r) => r.json())
  .then((data) => {
    (data.scenarios || []).forEach((scene, i) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "scenario-card";
      card.style.setProperty("--i", String(i));
      card.dataset.scenario = scene.id;
      card.innerHTML =
        `<span class="scenario-art" aria-hidden="true">${SCENARIO_ART[scene.id] || "💬"}</span>` +
        `<span class="scenario-label"></span>`;
      card.querySelector(".scenario-label").textContent = scene.label;
      card.addEventListener("click", () => startScene(scene.id));
      scenarioGrid.appendChild(card);
    });
  })
  .catch(() => {
    scenarioGrid.textContent = "Could not load scenes.";
  });

function showPracticeError(message) {
  practiceError.textContent = message;
  practiceError.classList.remove("hidden");
}

// ─── Score ring ─────────────────────────────────────────────────────────────
function pushScore(score) {
  if (typeof score !== "number") return;
  scores.push(score);
  const average = Math.round(scores.reduce((a, b) => a + b, 0) / scores.length);
  scoreValue.textContent = String(average);
  scoreArc.style.strokeDashoffset = String(RING - (RING * average) / 100);
  // Colour follows the average so progress is legible at a glance, without
  // needing to read the number.
  scoreArc.style.stroke =
    average >= 80 ? "var(--ok)" : average >= 55 ? "var(--warn)" : "var(--err)";
}

function resetScore() {
  scores.length = 0;
  scoreValue.textContent = "—";
  scoreArc.style.strokeDashoffset = String(RING);
  scoreArc.style.stroke = "var(--ok)";
}

// ─── Thread ─────────────────────────────────────────────────────────────────
function addPracticeBubble(text, who, gloss) {
  const row = document.createElement("div");
  row.className = `practice-row practice-${who}`;

  const bubble = document.createElement("div");
  bubble.className = `bubble bubble-${who === "you" ? "user" : "iris"}`;
  bubble.textContent = text;
  row.appendChild(bubble);

  if (gloss) {
    const glossEl = document.createElement("p");
    glossEl.className = "practice-gloss";
    glossEl.textContent = gloss;
    glossEl.hidden = !showGloss;
    row.appendChild(glossEl);
  }

  practiceThread.appendChild(row);
  practiceThread.scrollTop = practiceThread.scrollHeight;
  return row;
}

function addCorrection(correction) {
  const card = document.createElement("div");
  card.className = "correction-card";
  const fixed = document.createElement("p");
  fixed.className = "correction-fixed";
  fixed.textContent = correction.fixed;
  const why = document.createElement("p");
  why.className = "correction-why";
  why.textContent = correction.why;
  card.append(fixed, why);
  practiceThread.appendChild(card);
  practiceThread.scrollTop = practiceThread.scrollHeight;
}

function addPracticeTyping() {
  const bubble = document.createElement("div");
  bubble.className = "bubble bubble-iris bubble-typing practice-row";
  bubble.innerHTML = "<span></span><span></span><span></span>";
  practiceThread.appendChild(bubble);
  practiceThread.scrollTop = practiceThread.scrollHeight;
  return bubble;
}

function setSuggestion(phrase, gloss) {
  if (!phrase) {
    practiceSuggestion.classList.add("hidden");
    return;
  }
  btnSuggestion.textContent = phrase;
  btnSuggestion.title = gloss || "";
  practiceSuggestion.classList.remove("hidden");
}

btnSuggestion.addEventListener("click", () => {
  practiceInput.value = btnSuggestion.textContent;
  practiceInput.focus();
});

// ─── Turns ──────────────────────────────────────────────────────────────────
async function sendPractice(message) {
  if (practiceBusy) return;
  practiceBusy = true;
  btnSendPractice.disabled = true;
  practiceError.classList.add("hidden");
  setSuggestion(null);

  if (message) addPracticeBubble(message, "you");
  const typing = addPracticeTyping();

  try {
    const res = await fetch("/api/practice", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        language: practiceLang.value,
        scenario: practiceScenario,
        level: practiceLevel.value,
        history: practiceHistory,
      }),
    });
    const data = await res.json().catch(() => ({}));
    typing.remove();

    if (!res.ok) {
      showPracticeError(data.error || `Practice failed (${res.status}).`);
      return;
    }

    // Correction first: it belongs to the message just sent, so it reads in
    // the right order above the character's reply.
    if (data.correction) addCorrection(data.correction);
    pushScore(data.score);
    addPracticeBubble(data.reply, "partner", data.gloss);
    setSuggestion(data.suggestion, data.suggestion_gloss);

    if (message) practiceHistory.push({ role: "user", content: message });
    practiceHistory.push({ role: "assistant", content: data.reply });
    while (practiceHistory.length > 20) practiceHistory.shift();
  } catch {
    typing.remove();
    showPracticeError("Network error — could not reach the practice partner.");
  } finally {
    practiceBusy = false;
    btnSendPractice.disabled = false;
    practiceInput.focus();
  }
}

practiceForm.addEventListener("submit", (evt) => {
  evt.preventDefault();
  const text = practiceInput.value.trim();
  if (!text) return;
  practiceInput.value = "";
  sendPractice(text);
});

function startScene(scenarioId) {
  practiceScenario = scenarioId;
  practiceHistory.length = 0;
  practiceThread.innerHTML = "";
  resetScore();
  practiceSetup.classList.add("hidden");
  practiceSession.classList.remove("hidden");
  practiceInput.placeholder = `Reply in ${practiceLang.options[practiceLang.selectedIndex].text}…`;
  // Empty message means "open the scene" -- the partner speaks first, so the
  // learner never faces a blank box wondering how to start.
  sendPractice("");
}

btnPracticeBack.addEventListener("click", () => {
  practiceSession.classList.add("hidden");
  practiceSetup.classList.remove("hidden");
});

btnPracticeGloss.addEventListener("click", () => {
  showGloss = !showGloss;
  btnPracticeGloss.setAttribute("aria-pressed", String(showGloss));
  practiceThread.querySelectorAll(".practice-gloss").forEach((g) => { g.hidden = !showGloss; });
});

// ─── Open / close ───────────────────────────────────────────────────────────
function openPractice() {
  closeTools({ restoreFocus: false });
  practicePanel.classList.remove("hidden");
  syncModalBackdrop();
}

function closePractice() {
  practicePanel.classList.add("hidden");
  syncModalBackdrop();
}

btnClosePractice.addEventListener("click", closePractice);
document.querySelector('.hero-card[data-tool="practice"]')
  ?.addEventListener("click", openPractice);
