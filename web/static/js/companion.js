/**
 * Iris: the companion panel.
 *
 * Split out of app.js, which was heading past 1700 lines in one global scope.
 * This is a classic script loaded after app.js, so it shares that global
 * lexical environment -- `el`, `closeTools`, `syncModalBackdrop`, `btnTools`
 * and `SPEECH_LOCALES` all resolve from there. Everything it owns is declared
 * here, and app.js only ever reaches back for `companionPanel` and
 * `closeCompanion`, both from handlers that run after both files have loaded.
 */

const btnCompanion = el("btn-companion");
const companionPanel = el("companion-panel");
const btnCloseCompanion = el("btn-close-companion");
const companionThread = el("companion-thread");
const companionOpening = el("companion-opening");
const companionForm = el("companion-form");
const companionInput = el("companion-input");
const btnSendCompanion = el("btn-send-companion");
const companionError = el("companion-error");
const companionSee = el("companion-see");
const companionVideo = el("companion-video");
const companionCanvas = el("companion-canvas");
const companionVisionNote = el("companion-vision-note");
const visionStage = el("vision-stage");
const visionLive = el("vision-live");
const visionScan = el("vision-scan");
const moodChip = el("mood-chip");
const irisStage = document.querySelector(".iris-stage");
const irisFace = el("iris-face");
const irisFeeling = el("iris-feeling");
const irisMouth = el("iris-mouth");
const irisBrowL = el("iris-brow-l");
const irisBrowR = el("iris-brow-r");
const btnIrisVoice = el("btn-iris-voice");
const btnIrisClear = el("btn-iris-clear");
const btnIrisMic = el("btn-iris-mic");

// Mouth and brow paths per feeling. Eyes blink on their own in CSS.
const IRIS_FACES = {
  warm:        { mouth: "M38 59 Q48 66 58 59", brow: ["M31 34 Q37 31 43 34", "M53 34 Q59 31 65 34"] },
  cheerful:    { mouth: "M36 58 Q48 71 60 58", brow: ["M31 33 Q37 29 43 33", "M53 33 Q59 29 65 33"] },
  playful:     { mouth: "M37 59 Q48 69 59 61", brow: ["M31 33 Q37 28 43 33", "M53 35 Q59 32 65 34"] },
  curious:     { mouth: "M41 61 Q48 65 55 61", brow: ["M31 32 Q37 28 43 32", "M53 35 Q59 33 65 35"] },
  thoughtful:  { mouth: "M40 62 L56 61",       brow: ["M31 35 Q37 33 43 35", "M53 34 Q59 31 65 34"] },
  concerned:   { mouth: "M39 63 Q48 58 57 63", brow: ["M31 32 Q37 36 43 33", "M53 33 Q59 36 65 32"] },
  gentle:      { mouth: "M40 60 Q48 64 56 60", brow: ["M31 35 Q37 33 43 35", "M53 35 Q59 33 65 35"] },
  encouraging: { mouth: "M37 58 Q48 68 59 58", brow: ["M31 34 Q37 30 43 34", "M53 34 Q59 30 65 34"] },
  apologetic:  { mouth: "M40 63 Q48 60 56 63", brow: ["M31 33 Q37 37 43 34", "M53 34 Q59 37 65 33"] },
  impressed:   { mouth: "M40 60 Q48 68 56 60", brow: ["M31 31 Q37 27 43 31", "M53 31 Q59 27 65 31"] },
};

const companionHistory = [];
let companionBusy = false;
let visionStream = null;
let visionTimer = null;
let lastExpression = null;
let irisSpeaks = localStorage.getItem("rosetta-iris-voice") === "1";
let irisRecorder = null;
let irisChunks = [];
let irisAudioContext = null;
let irisMeterFrame = null;

function stopIrisMeter() {
  if (irisMeterFrame) cancelAnimationFrame(irisMeterFrame);
  irisMeterFrame = null;
  irisAudioContext?.close();
  irisAudioContext = null;
  irisStage.style.setProperty("--iris-level", "0");
  irisStage.style.setProperty("--iris-scale", "1");
  irisStage.style.setProperty("--iris-ring-opacity", "0.32");
  irisStage.style.transform = "scale(1)";
}

function startIrisMeter(stream) {
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  if (!AudioContext) return;
  irisAudioContext = new AudioContext();
  const analyser = irisAudioContext.createAnalyser();
  analyser.fftSize = 256;
  analyser.smoothingTimeConstant = 0.78;
  irisAudioContext.createMediaStreamSource(stream).connect(analyser);
  const samples = new Uint8Array(analyser.fftSize);

  function draw() {
    analyser.getByteTimeDomainData(samples);
    let energy = 0;
    for (const value of samples) {
      const normalized = (value - 128) / 128;
      energy += normalized * normalized;
    }
    const level = Math.min(1, Math.sqrt(energy / samples.length) * 6);
    irisStage.style.setProperty("--iris-level", level.toFixed(3));
    irisStage.style.setProperty("--iris-scale", `${1 + level * 0.16}`);
    irisStage.style.setProperty("--iris-ring-opacity", `${0.32 + level * 0.55}`);
    irisStage.style.transform = `scale(${1 + level * 0.16})`;
    irisMeterFrame = requestAnimationFrame(draw);
  }
  draw();
}

// Each frame is a full vision request against a tight free-tier token budget.
// This reads a mood; it is not a video feed.
const VISION_INTERVAL_MS = 9000;
const VISION_FRAME_WIDTH = 320;

function setIrisFeeling(feeling) {
  const face = IRIS_FACES[feeling] || IRIS_FACES.warm;
  irisFace.setAttribute("data-feeling", feeling);
  irisMouth.setAttribute("d", face.mouth);
  irisBrowL.setAttribute("d", face.brow[0]);
  irisBrowR.setAttribute("d", face.brow[1]);
  irisFeeling.textContent = `feeling ${feeling}`;
}

function setIrisStatus(status = "") {
  irisFeeling.textContent = status || `feeling ${irisFace.getAttribute("data-feeling") || "warm"}`;
  irisFeeling.classList.toggle("is-active", Boolean(status));
}

function showError(message) {
  companionError.textContent = message;
  companionError.classList.remove("hidden");
}

function scrollThread() {
  companionThread.scrollTop = companionThread.scrollHeight;
}

function dismissOpening() {
  companionOpening?.remove();
}

function addBubble(text, who) {
  dismissOpening();
  if (who === "user") {
    const bubble = document.createElement("div");
    bubble.className = "bubble bubble-user";
    bubble.textContent = text;
    companionThread.appendChild(bubble);
    scrollThread();
    return bubble;
  }

  // Iris's messages carry their own actions, so they need a wrapper row.
  const row = document.createElement("div");
  row.className = "bubble-row";
  const bubble = document.createElement("div");
  bubble.className = "bubble bubble-iris";
  bubble.textContent = text;

  const tools = document.createElement("div");
  tools.className = "bubble-tools";
  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "bubble-tool";
  copy.textContent = "copy";
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(bubble.textContent);
      copy.textContent = "copied";
      setTimeout(() => { copy.textContent = "copy"; }, 1400);
    } catch {
      // Clipboard unavailable (insecure context) -- nothing useful to say.
    }
  });
  const speak = document.createElement("button");
  speak.type = "button";
  speak.className = "bubble-tool";
  speak.textContent = "speak";
  speak.addEventListener("click", () => speakAsIris(bubble.textContent));

  tools.append(copy, speak);
  row.append(bubble, tools);
  companionThread.appendChild(row);
  scrollThread();
  return bubble;
}

function addTypingBubble() {
  dismissOpening();
  const bubble = document.createElement("div");
  bubble.className = "bubble bubble-iris bubble-typing";
  bubble.innerHTML = "<span></span><span></span><span></span>";
  companionThread.appendChild(bubble);
  scrollThread();
  return bubble;
}

// ─── Voice out ──────────────────────────────────────────────────────────────
function speakAsIris(text) {
  if (!("speechSynthesis" in window) || !text) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "en-US";
  utterance.rate = 1.03;
  utterance.pitch = 1.08;
  // The mouth animates only while audio is actually playing, so the face and
  // the voice can't drift out of sync.
  utterance.addEventListener("start", () => {
    irisStage.classList.add("is-speaking");
    setIrisStatus("speaking with you");
  });
  utterance.addEventListener("end", () => {
    irisStage.classList.remove("is-speaking");
    setIrisStatus();
  });
  utterance.addEventListener("error", () => {
    irisStage.classList.remove("is-speaking");
    setIrisStatus();
  });
  window.speechSynthesis.speak(utterance);
}

function syncVoiceButton() {
  btnIrisVoice.setAttribute("aria-pressed", String(irisSpeaks));
  btnIrisVoice.title = irisSpeaks ? "Iris reads replies aloud (on)" : "Iris reads replies aloud (off)";
}
btnIrisVoice.addEventListener("click", () => {
  irisSpeaks = !irisSpeaks;
  localStorage.setItem("rosetta-iris-voice", irisSpeaks ? "1" : "0");
  if (!irisSpeaks) {
    window.speechSynthesis?.cancel();
    irisStage.classList.remove("is-speaking");
  }
  syncVoiceButton();
});
if (!("speechSynthesis" in window)) btnIrisVoice.classList.add("hidden");
syncVoiceButton();

// ─── Voice in ───────────────────────────────────────────────────────────────
/**
 * Live dictation.
 *
 * The previous version recorded the whole utterance, waited for you to press
 * stop, uploaded it, and only then showed any text -- so nothing appeared on
 * screen until seconds after you finished a sentence. That is the lag.
 *
 * `SpeechRecognition` streams interim results while you are still speaking, so
 * words land in ~200-400ms. Whisper is kept as the fallback for browsers that
 * don't implement it (Firefox), because the round trip is still better than no
 * dictation at all.
 *
 * A second, raw stream feeds the analyser that drives the orb. It has to be
 * separate because SpeechRecognition never exposes its own audio -- and it is
 * started *after* recognition, never awaited before it, since blocking the
 * recogniser on a getUserMedia handshake is exactly what used to swallow the
 * first words of a sentence.
 */
const Recognizer = window.SpeechRecognition || window.webkitSpeechRecognition;
const voiceBar = el("voice-bar");
const voiceHeard = el("voice-heard");
const voiceWave = el("voice-wave");

// Bars for the waveform, each with a fixed phase multiplier.
[0.55, 0.9, 0.7, 1, 0.65, 0.85, 0.5].forEach((weight) => {
  const bar = document.createElement("i");
  bar.style.setProperty("--bar", String(weight));
  voiceWave.appendChild(bar);
});

let dictation = null;
let dictating = false;
let dictationFinal = "";
let orbStream = null;
let orbContext = null;
let orbFrame = null;
let orbLevel = 0;

function setVoiceBar(open) {
  voiceBar.classList.toggle("hidden", !open);
  voiceBar.setAttribute("aria-hidden", String(!open));
  btnIrisMic.classList.toggle("is-recording", open);
  btnIrisMic.setAttribute("aria-pressed", String(open));
  irisStage.classList.toggle("is-listening", open);
  setIrisStatus(open ? "listening to you" : "");
}

function stopOrb() {
  if (orbFrame) cancelAnimationFrame(orbFrame);
  orbFrame = null;
  orbStream?.getTracks().forEach((t) => t.stop());
  orbStream = null;
  // Closing matters: browsers cap concurrent AudioContexts at a handful, and
  // leaking one per dictation kills the meter a few uses into a session.
  orbContext?.close().catch(() => {});
  orbContext = null;
  orbLevel = 0;
  voiceBar.style.setProperty("--level", "0");
  irisStage.style.setProperty("--iris-ring-opacity", "0.32");
  irisStage.style.transform = "scale(1)";
}

async function startOrb() {
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  if (!AudioContext || !navigator.mediaDevices?.getUserMedia) return;
  orbStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  if (!dictating) {  // stopped while permission was pending
    orbStream.getTracks().forEach((t) => t.stop());
    orbStream = null;
    return;
  }
  orbContext = new AudioContext();
  const analyser = orbContext.createAnalyser();
  analyser.fftSize = 256;
  // Some smoothing in the analyser, the rest below -- raw RMS jitters hard
  // enough to make the orb look broken rather than alive.
  analyser.smoothingTimeConstant = 0.6;
  orbContext.createMediaStreamSource(orbStream).connect(analyser);
  const samples = new Uint8Array(analyser.fftSize);

  const draw = () => {
    analyser.getByteTimeDomainData(samples);
    let energy = 0;
    for (const value of samples) {
      const normalized = (value - 128) / 128;
      energy += normalized * normalized;
    }
    const target = Math.min(1, Math.sqrt(energy / samples.length) * 6.5);
    // Asymmetric easing: snap up on attack so the orb feels responsive to a
    // sudden word, fall away slowly so it breathes instead of flickering.
    const ease = target > orbLevel ? 0.45 : 0.12;
    orbLevel += (target - orbLevel) * ease;
    voiceBar.style.setProperty("--level", orbLevel.toFixed(3));
    irisStage.style.setProperty("--iris-ring-opacity", `${0.32 + orbLevel * 0.55}`);
    irisStage.style.transform = `scale(${1 + orbLevel * 0.16})`;
    orbFrame = requestAnimationFrame(draw);
  };
  draw();
}

function finishDictation(text) {
  const clean = (text || "").trim();
  if (clean) {
    companionInput.value = clean;
    companionInput.focus();
  }
}

function stopDictation() {
  dictating = false;
  setVoiceBar(false);
  stopOrb();
  try {
    dictation?.stop();
  } catch {
    // Already stopped; nothing to do.
  }
  if (irisRecorder && irisRecorder.state === "recording") irisRecorder.stop();
}

function startLiveDictation() {
  dictationFinal = "";
  dictation = new Recognizer();
  dictation.continuous = true;
  dictation.interimResults = true;
  dictation.lang = navigator.language || "en-US";

  dictation.addEventListener("result", (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const chunk = event.results[i][0].transcript;
      if (event.results[i].isFinal) dictationFinal += chunk;
      else interim += chunk;
    }
    const shown = (dictationFinal + interim).trim();
    voiceHeard.textContent = shown || "Listening…";
    voiceHeard.classList.toggle("is-waiting", !shown);
    // Mirrored into the composer as it arrives, so stopping mid-sentence
    // still leaves you with everything heard so far.
    companionInput.value = shown;
  });

  dictation.addEventListener("error", (event) => {
    if (event.error === "not-allowed") showError("Microphone permission was denied.");
    else if (event.error !== "aborted" && event.error !== "no-speech") {
      showError(`Dictation stopped: ${event.error}.`);
    }
    stopDictation();
  });

  dictation.addEventListener("end", () => {
    if (!dictating) {
      finishDictation(dictationFinal);
      return;
    }
    // The recogniser closes itself after a pause; reopen so a natural break
    // mid-sentence doesn't silently end dictation.
    try {
      dictation.start();
    } catch {
      stopDictation();
      finishDictation(dictationFinal);
    }
  });

  dictation.start();
}

// Fallback for browsers with no SpeechRecognition: record, then transcribe.
async function startWhisperDictation() {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    showError("Voice input isn't supported in this browser.");
    stopDictation();
    return;
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  irisChunks = [];
  irisRecorder = new MediaRecorder(stream);
  irisRecorder.addEventListener("dataavailable", (e) => {
    if (e.data.size) irisChunks.push(e.data);
  });
  irisRecorder.addEventListener("stop", async () => {
    stream.getTracks().forEach((t) => t.stop());
    const blob = new Blob(irisChunks, { type: "audio/webm" });
    if (!blob.size) return;
    const form = new FormData();
    form.append("audio", blob, "speech.webm");
    voiceHeard.textContent = "Transcribing…";
    irisStage.classList.add("is-transcribing");
    setIrisStatus("understanding your voice");
    try {
      const res = await fetch("/api/transcribe", { method: "POST", body: form });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.text) finishDictation(data.text);
      else if (!res.ok) showError(data.error || "Could not transcribe that.");
    } catch {
      showError("Network error while transcribing.");
    } finally {
      irisStage.classList.remove("is-transcribing");
      setIrisStatus();
    }
  });
  irisRecorder.start();
}

async function toggleDictation() {
  if (dictating) {
    stopDictation();
    return;
  }
  companionError.classList.add("hidden");
  dictating = true;
  voiceHeard.textContent = "Listening…";
  voiceHeard.classList.add("is-waiting");
  setVoiceBar(true);

  try {
    if (Recognizer) startLiveDictation();
    else await startWhisperDictation();
  } catch (error) {
    dictating = false;
    setVoiceBar(false);
    showError(error?.name === "NotAllowedError"
      ? "Microphone permission was denied."
      : "The microphone could not start.");
    return;
  }
  // Never awaited before the recogniser is running: the orb is decoration and
  // must not delay a single word of what you say.
  startOrb().catch(() => {});
}
btnIrisMic.addEventListener("click", toggleDictation);

// ─── Conversation ───────────────────────────────────────────────────────────
async function sendToIris(text) {
  if (companionBusy) return;
  companionBusy = true;
  btnSendCompanion.disabled = true;
  companionError.classList.add("hidden");

  addBubble(text, "user");
  const typing = addTypingBubble();
  irisStage.classList.add("is-thinking");
  setIrisStatus("thinking about that");

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, history: companionHistory, expression: lastExpression }),
    });
    const data = await res.json().catch(() => ({}));
    typing.remove();

    if (!res.ok) {
      showError(data.error || `Iris couldn't reply (${res.status}).`);
      return;
    }

    addBubble(data.reply, "iris");
    setIrisFeeling(data.feeling || "warm");
    if (irisSpeaks) speakAsIris(data.reply);

    companionHistory.push({ role: "user", content: text }, { role: "assistant", content: data.reply });
    // Trimmed here as well as server-side: sending a transcript that grows
    // without bound wastes tokens on every single turn.
    while (companionHistory.length > 24) companionHistory.shift();
  } catch {
    typing.remove();
    showError("Network error — could not reach Iris.");
  } finally {
    irisStage.classList.remove("is-thinking");
    if (!irisStage.classList.contains("is-speaking")) setIrisStatus();
    companionBusy = false;
    btnSendCompanion.disabled = false;
    companionInput.focus();
  }
}

companionForm.addEventListener("submit", (evt) => {
  evt.preventDefault();
  const text = companionInput.value.trim();
  if (!text) return;
  companionInput.value = "";
  sendToIris(text);
});

// Starter chips are delegated because the opening is removed on first message.
companionThread.addEventListener("click", (evt) => {
  const chip = evt.target.closest(".starter-chip");
  if (chip) sendToIris(chip.dataset.say);
});

btnIrisClear.addEventListener("click", () => {
  companionHistory.length = 0;
  window.speechSynthesis?.cancel();
  irisStage.classList.remove("is-speaking");
  companionThread.innerHTML = "";
  companionThread.appendChild(companionOpening.cloneNode(true));
  setIrisFeeling("warm");
  companionError.classList.add("hidden");
});

// ─── Camera ─────────────────────────────────────────────────────────────────
function setMoodChip(reading) {
  if (!reading || !reading.face_present) {
    moodChip.textContent = "no face in frame";
    moodChip.classList.add("is-uncertain");
    moodChip.classList.remove("hidden");
    return;
  }
  const pct = Math.round((reading.confidence || 0) * 100);
  // Always shown as a guess with its confidence: a facial expression is not
  // the same thing as what someone feels.
  moodChip.textContent = `looks ${reading.expression} · ${pct}%`;
  moodChip.classList.toggle("is-uncertain", (reading.confidence || 0) < 0.45);
  moodChip.classList.remove("hidden");
}

function flashScan() {
  visionScan.classList.remove("hidden");
  visionScan.style.animation = "none";
  void visionScan.offsetWidth; // restart the sweep
  visionScan.style.animation = "";
}

function stopVision() {
  clearTimeout(visionTimer);
  visionTimer = null;
  visionStream?.getTracks().forEach((track) => track.stop());
  visionStream = null;
  companionVideo.srcObject = null;
  companionVideo.classList.remove("is-live");
  visionStage.classList.remove("is-live");
  visionLive.classList.add("hidden");
  visionScan.classList.add("hidden");
  moodChip.classList.add("hidden");
  lastExpression = null;
  companionVisionNote.textContent =
    "Off by default. When on, a small snapshot goes to the AI provider every few seconds — never recorded, never stored.";
}

async function captureExpression() {
  if (!visionStream || companionVideo.videoWidth === 0) return;
  flashScan();

  const scale = VISION_FRAME_WIDTH / companionVideo.videoWidth;
  companionCanvas.width = VISION_FRAME_WIDTH;
  companionCanvas.height = Math.round(companionVideo.videoHeight * scale);
  companionCanvas.getContext("2d")
    .drawImage(companionVideo, 0, 0, companionCanvas.width, companionCanvas.height);

  const blob = await new Promise((resolve) => companionCanvas.toBlob(resolve, "image/jpeg", 0.7));
  if (!blob) return;

  const form = new FormData();
  form.append("image", blob, "frame.jpg");
  try {
    const res = await fetch("/api/expression", { method: "POST", body: form });
    const data = await res.json().catch(() => ({}));
    if (res.status === 429) {
      // Backing off matters: every frame is a full vision call, and hammering
      // a rate-limited endpoint only keeps it rate-limited.
      companionVisionNote.textContent = "Reading paused briefly — the AI provider is rate limiting.";
      return;
    }
    if (!res.ok) return;
    lastExpression = data;
    setMoodChip(data);
  } catch {
    // A dropped frame isn't worth surfacing; the next tick tries again.
  }
}

function scheduleVision() {
  clearTimeout(visionTimer);
  if (!visionStream) return;
  visionTimer = setTimeout(async () => {
    await captureExpression();
    scheduleVision();
  }, VISION_INTERVAL_MS);
}

async function startVision() {
  try {
    visionStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 640 } },
      audio: false,
    });
    // The box may have been unticked while permission was pending.
    if (!companionSee.checked) {
      visionStream.getTracks().forEach((t) => t.stop());
      visionStream = null;
      return;
    }
    companionVideo.srcObject = visionStream;
    companionVideo.classList.add("is-live");
    visionStage.classList.add("is-live");
    visionLive.classList.remove("hidden");
    await companionVideo.play();
    companionVisionNote.textContent =
      "Reading your expression every few seconds. Snapshots are sent to the AI provider and discarded.";
    await captureExpression();
    scheduleVision();
  } catch (error) {
    companionSee.checked = false;
    stopVision();
    showError(error?.name === "NotAllowedError"
      ? "Camera permission was denied. Allow it in your browser's site settings."
      : "The camera could not be started.");
  }
}

companionSee.addEventListener("change", () => {
  companionError.classList.add("hidden");
  if (companionSee.checked) startVision();
  else stopVision();
});

// ─── Open / close ───────────────────────────────────────────────────────────
function openCompanion() {
  closeTools({ restoreFocus: false });
  companionPanel.classList.remove("hidden");
  companionPanel.classList.remove("is-opening");
  void companionPanel.offsetWidth;
  companionPanel.classList.add("is-opening");
  setTimeout(() => companionPanel.classList.remove("is-opening"), 900);
  btnCompanion.setAttribute("aria-expanded", "true");
  syncModalBackdrop();
  companionInput.focus();
}

function closeCompanion() {
  // Everything that holds hardware or makes noise gets released here.
  companionSee.checked = false;
  stopVision();
  window.speechSynthesis?.cancel();
  irisStage.classList.remove("is-speaking");
  stopDictation();
  companionPanel.classList.add("hidden");
  btnCompanion.setAttribute("aria-expanded", "false");
  syncModalBackdrop();
  btnTools.focus();
}

btnCompanion.addEventListener("click", openCompanion);
btnCloseCompanion.addEventListener("click", closeCompanion);

// The floating launcher: Iris, one click from anywhere.
const irisFab = el("iris-fab");
irisFab.addEventListener("click", openCompanion);
if (!localStorage.getItem("rosetta-iris-seen")) {
  irisFab.classList.add("is-new");
  irisFab.addEventListener("click", () => {
    localStorage.setItem("rosetta-iris-seen", "1");
    irisFab.classList.remove("is-new");
  }, { once: true });
}

setIrisFeeling("warm");
