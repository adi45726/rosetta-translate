const LANGUAGES = JSON.parse(document.getElementById("languages-data").textContent);

const el = (id) => document.getElementById(id);
const sourceLang = el("source-lang");
const targetLang = el("target-lang");
const sourceText = el("source-text");
const targetText = el("target-text");
const charCount = el("char-count");
const detectedPill = el("detected-pill");
const statusPill = el("status-pill");
const errorBanner = el("error-banner");
const btnCopy = el("btn-copy");
const btnSwap = el("btn-swap");
const themeToggle = el("theme-toggle");

const MAX_LEN = 500;
const state = { lastDetected: null, lastTranslation: "" };

// ─── Theme ──────────────────────────────────────────────────────────────────
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  themeToggle.textContent = theme === "dark" ? "◑" : "◐";
}
const savedTheme = localStorage.getItem("rosetta-theme");
if (savedTheme) applyTheme(savedTheme);
themeToggle.addEventListener("click", () => {
  const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
  localStorage.setItem("rosetta-theme", next);
  applyTheme(next);
});

// ─── Populate language selects ──────────────────────────────────────────────
function option(value, label) {
  const o = document.createElement("option");
  o.value = value;
  o.textContent = label;
  return o;
}

sourceLang.appendChild(option("auto", "Detect language"));
LANGUAGES.forEach(([code, name]) => sourceLang.appendChild(option(code, name)));
LANGUAGES.forEach(([code, name]) => targetLang.appendChild(option(code, name)));

sourceLang.value = "auto";
targetLang.value = LANGUAGES.some(([code]) => code === "es") ? "es" : LANGUAGES[0][0];

// ─── Char counter ───────────────────────────────────────────────────────────
function updateCharCount() {
  const n = sourceText.value.length;
  charCount.textContent = `${n} / ${MAX_LEN}`;
  charCount.classList.toggle("over-limit", n > MAX_LEN);
}

// ─── Translate (debounced) ──────────────────────────────────────────────────
let debounceTimer = null;
function scheduleTranslate() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(runTranslate, 350);
}

async function runTranslate() {
  const text = sourceText.value;
  errorBanner.classList.add("hidden");

  if (!text.trim()) {
    targetText.innerHTML = '<span class="hint">Translation will appear here.</span>';
    detectedPill.classList.add("hidden");
    statusPill.textContent = "";
    statusPill.className = "status-pill";
    btnCopy.disabled = true;
    state.lastTranslation = "";
    return;
  }

  statusPill.textContent = "translating…";
  statusPill.className = "status-pill";

  try {
    const res = await fetch("/api/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, source: sourceLang.value, target: targetLang.value }),
    });
    const data = await res.json();

    if (!res.ok) {
      statusPill.textContent = "error";
      statusPill.className = "status-pill err";
      errorBanner.textContent = data.error || "translation failed";
      errorBanner.classList.remove("hidden");
      return;
    }

    targetText.textContent = data.translated_text;
    state.lastTranslation = data.translated_text;
    btnCopy.disabled = false;

    if (data.detected_source) {
      state.lastDetected = data.detected_source;
      detectedPill.textContent = `Detected: ${data.detected_source_name || data.detected_source}`;
      detectedPill.classList.remove("hidden");
    } else {
      detectedPill.classList.add("hidden");
    }

    statusPill.textContent = "done";
    statusPill.className = "status-pill ok";
  } catch (err) {
    statusPill.textContent = "error";
    statusPill.className = "status-pill err";
    errorBanner.textContent = "network error — could not reach the server";
    errorBanner.classList.remove("hidden");
  }
}

sourceText.addEventListener("input", () => {
  updateCharCount();
  scheduleTranslate();
});
sourceLang.addEventListener("change", scheduleTranslate);
targetLang.addEventListener("change", scheduleTranslate);

// ─── Swap ───────────────────────────────────────────────────────────────────
btnSwap.addEventListener("click", () => {
  if (sourceLang.value === "auto") {
    if (!state.lastDetected) return; // nothing to swap to yet
    const newSource = targetLang.value;
    targetLang.value = state.lastDetected;
    sourceLang.value = newSource;
  } else {
    const tmp = sourceLang.value;
    sourceLang.value = targetLang.value;
    targetLang.value = tmp;
  }
  if (state.lastTranslation) {
    sourceText.value = state.lastTranslation;
    updateCharCount();
  }
  scheduleTranslate();
});

// ─── Copy ───────────────────────────────────────────────────────────────────
btnCopy.addEventListener("click", async () => {
  if (!state.lastTranslation) return;
  try {
    await navigator.clipboard.writeText(state.lastTranslation);
    btnCopy.textContent = "Copied!";
    btnCopy.classList.add("copied");
    setTimeout(() => {
      btnCopy.textContent = "Copy";
      btnCopy.classList.remove("copied");
    }, 1500);
  } catch {
    // Clipboard API unavailable (e.g. insecure context) -- fail silently, copy just won't work.
  }
});

updateCharCount();
