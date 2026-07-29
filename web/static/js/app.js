const LANGUAGES = JSON.parse(document.getElementById("languages-data").textContent);
const CONFIG = JSON.parse(document.getElementById("app-config").textContent);

const el = (id) => document.getElementById(id);
const sourceLang = el("source-lang");
const targetLang = el("target-lang");
const sourceText = el("source-text");
const targetText = el("target-text");
const skeleton = el("skeleton");
const charCount = el("char-count");
const detectedPill = el("detected-pill");
const statusPill = el("status-pill");
const errorBanner = el("error-banner");
const romanizationLine = el("romanization");
const noteLine = el("translator-note");
const btnCopy = el("btn-copy");
const btnSpeak = el("btn-speak");
const btnSwap = el("btn-swap");
const btnClear = el("btn-clear");
const themeToggle = el("theme-toggle");
const alternatesRow = el("alternates-row");
const btnHistory = el("btn-history");
const historyPanel = el("history-panel");
const historyList = el("history-list");
const btnClearHistory = el("btn-clear-history");
const engineBadge = el("engine-badge");
const arrowTemplate = el("arrow-template");
const btnCaptions = el("btn-captions");
const captionPanel = el("caption-panel");
const btnCloseCaptions = el("btn-close-captions");
const captionDisplay = el("caption-display");
const captionStatus = el("caption-status");
const btnStartCaptions = el("btn-start-captions");
const btnUseCaption = el("btn-use-caption");
const btnLargeCaption = el("btn-large-caption");
const btnClearCaption = el("btn-clear-caption");
const captionLanguage = el("caption-language");
const micMeterFill = el("mic-meter-fill");
const micLevelLabel = el("mic-level-label");
const btnWriting = el("btn-writing");
const writingPanel = el("writing-panel");
const btnCloseWriting = el("btn-close-writing");
const writingInput = el("writing-input");
const writingMode = el("writing-mode");
const writingTone = el("writing-tone");
const writingAudience = el("writing-audience");
const preserveTerms = el("preserve-terms");
const btnRunWriting = el("btn-run-writing");
const btnWritingFromSource = el("btn-writing-from-source");
const btnCopyWriting = el("btn-copy-writing");
const writingError = el("writing-error");
const writingResult = el("writing-result");
const writingOutput = el("writing-output");
const btnVoiceInput = el("btn-voice-input");
const voiceStatus = el("voice-status");
const btnTools = el("btn-tools");
const toolsPanel = el("tools-panel");
const btnCloseTools = el("btn-close-tools");
const modalBackdrop = el("modal-backdrop");
const btnToolVoice = el("btn-tool-voice");
const btnCamera = el("btn-camera");
const cameraPanel = el("camera-panel");
const btnCloseCamera = el("btn-close-camera");
const cameraVideo = el("camera-video");
const cameraImagePreview = el("camera-image-preview");
const cameraCanvas = el("camera-canvas");
const cameraRegions = el("camera-regions");
const cameraMessage = el("camera-message");
const cameraStatus = el("camera-status");
const btnScanCamera = el("btn-scan-camera");
const btnFlipCamera = el("btn-flip-camera");
const cameraAutoScan = el("camera-auto-scan");
const cameraFileInput = el("camera-file-input");
const cameraDropZone = el("camera-drop-zone");
const btnUseCameraText = el("btn-use-camera-text");
const btnCopyCameraText = el("btn-copy-camera-text");
const voiceModePanel = el("voice-mode-panel");
const btnCloseVoiceMode = el("btn-close-voice-mode");
const voiceOrb = el("voice-orb");
const voiceModeStatus = el("voice-mode-status");
const voiceModeTimer = el("voice-mode-timer");
const voiceModeSource = el("voice-mode-source");
const voiceModeTarget = el("voice-mode-target");
const voiceModeTargetLang = el("voice-mode-target-lang");
const btnClearVoiceMode = el("btn-clear-voice-mode");
const btnCopyVoiceMode = el("btn-copy-voice-mode");

const MAX_LEN = CONFIG.maxLength;
const HISTORY_KEY = "rosetta-history";
const MAX_HISTORY = 12;
// An LLM call costs real quota, so wait longer for the typist to finish than
// the old keyless provider needed.
const DEBOUNCE_MS = CONFIG.provider === "groq" ? 600 : 350;
// Past this, per-word reveal means hundreds of spans for no visual gain.
const MAX_STAGGERED_WORDS = 60;

const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// A restrained pointer-following highlight makes the glass feel dimensional
// without tilting controls or moving the interface under the cursor.
if (!REDUCED_MOTION && window.matchMedia("(pointer: fine)").matches) {
  document.querySelectorAll(".glass-surface, .pane").forEach((surface) => {
    surface.addEventListener("pointermove", (event) => {
      const bounds = surface.getBoundingClientRect();
      surface.style.setProperty("--pointer-x", `${event.clientX - bounds.left}px`);
      surface.style.setProperty("--pointer-y", `${event.clientY - bounds.top}px`);
      surface.style.setProperty("--glass-shine", "1");
    });
    surface.addEventListener("pointerleave", () => {
      surface.style.setProperty("--glass-shine", "0");
    });
  });
}

const state = {
  lastDetected: null,
  lastTranslation: "",
  lastRequestKey: null,
  inFlight: null,
  seq: 0,
};

const writingState = { original: "", revised: "", changes: [], summary: "" };

function syncModalBackdrop() {
  const modalOpen = !writingPanel.classList.contains("hidden")
    || !captionPanel.classList.contains("hidden")
    || !cameraPanel.classList.contains("hidden")
    || !voiceModePanel.classList.contains("hidden")
    || !companionPanel.classList.contains("hidden")
    || !toolsPanel.classList.contains("hidden");
  modalBackdrop.classList.toggle("hidden", !modalOpen);
  document.body.classList.toggle("modal-open", modalOpen);
}

function closeTools({ restoreFocus = true } = {}) {
  toolsPanel.classList.add("hidden");
  btnTools.setAttribute("aria-expanded", "false");
  syncModalBackdrop();
  if (restoreFocus) btnTools.focus();
}

function openTools() {
  toolsPanel.classList.remove("hidden");
  btnTools.setAttribute("aria-expanded", "true");
  syncModalBackdrop();
  toolsPanel.querySelector(".tool-card")?.focus();
}

btnTools.addEventListener("click", () => {
  if (toolsPanel.classList.contains("hidden")) openTools();
  else closeTools();
});
btnCloseTools.addEventListener("click", () => closeTools());
modalBackdrop.addEventListener("click", () => {
  if (!writingPanel.classList.contains("hidden")) closeWriting();
  else if (!captionPanel.classList.contains("hidden")) closeCaptions();
  else if (!cameraPanel.classList.contains("hidden")) closeCamera();
  else if (!voiceModePanel.classList.contains("hidden")) closeVoiceMode();
  else if (!companionPanel.classList.contains("hidden")) closeCompanion();
  else closeTools();
});

// ─── Camera translation with visual overlays ────────────────────────────────
let cameraStream = null;
let cameraFacing = "environment";
let cameraScanTimer = null;
let cameraScanning = false;
let cameraFailures = 0;
let cameraResult = null;
let cameraPreviewUrl = null;
let lastCameraFingerprint = null;

function stopCamera() {
  clearTimeout(cameraScanTimer);
  cameraScanTimer = null;
  cameraStream?.getTracks().forEach((track) => track.stop());
  cameraStream = null;
  cameraVideo.srcObject = null;
}

function scheduleCameraScan(delay = 15000) {
  clearTimeout(cameraScanTimer);
  if (!cameraAutoScan.checked || cameraPanel.classList.contains("hidden")) return;
  cameraScanTimer = setTimeout(async () => {
    await scanCamera();
    scheduleCameraScan(15000);
  }, delay);
}

async function startCamera() {
  stopCamera();
  lastCameraFingerprint = null;
  cameraResult = null;
  btnUseCameraText.disabled = true;
  btnCopyCameraText.disabled = true;
  cameraMessage.textContent = "Starting camera…";
  cameraMessage.classList.remove("hidden");
  cameraRegions.innerHTML = "";
  cameraImagePreview.classList.add("hidden");
  cameraVideo.classList.remove("hidden");
  if (cameraPreviewUrl) URL.revokeObjectURL(cameraPreviewUrl);
  cameraPreviewUrl = null;
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: { ideal: cameraFacing },
        width: { ideal: 1920 },
        height: { ideal: 1080 },
      },
      audio: false,
    });
    cameraVideo.srcObject = cameraStream;
    await cameraVideo.play();
    cameraMessage.classList.add("hidden");
    cameraStatus.textContent = "Camera ready · hold text steady";
    cameraFailures = 0;
    scheduleCameraScan(2500);
  } catch (error) {
    cameraMessage.textContent = error?.name === "NotAllowedError"
      ? "Allow camera access in your browser settings."
      : "The camera could not be opened.";
    cameraStatus.textContent = "";
  }
}

function closeCamera() {
  stopCamera();
  cameraPanel.classList.add("hidden");
  btnCamera.setAttribute("aria-expanded", "false");
  syncModalBackdrop();
  btnTools.focus();
}

async function openCamera() {
  closeTools({ restoreFocus: false });
  cameraPanel.classList.remove("hidden");
  btnCamera.setAttribute("aria-expanded", "true");
  syncModalBackdrop();
  await startCamera();
}

function renderCameraRegions(data) {
  cameraResult = data;
  btnUseCameraText.disabled = !data.source_text;
  btnCopyCameraText.disabled = !data.translated_text;
  cameraRegions.innerHTML = "";
  const regions = data.regions?.length
    ? data.regions
    : (data.translated_text ? [{
        translation: data.translated_text, source: data.source_text,
        x: 0.07, y: 0.7, width: 0.86, height: 0.18,
      }] : []);
  regions.forEach((region) => {
    const card = document.createElement("div");
    card.className = "camera-translation";
    card.style.left = `${region.x * 100}%`;
    card.style.top = `${region.y * 100}%`;
    card.style.width = `${Math.max(20, region.width * 100)}%`;
    const translated = document.createElement("strong");
    translated.textContent = region.translation;
    card.appendChild(translated);
    if (region.source) {
      const source = document.createElement("small");
      source.textContent = region.source;
      card.appendChild(source);
    }
    cameraRegions.appendChild(card);
  });
}

async function scanCamera(imageBlob = null) {
  if (cameraScanning) return;
  if (!imageBlob && (!cameraStream || !cameraVideo.videoWidth)) return;
  cameraScanning = true;
  btnScanCamera.disabled = true;
  cameraStatus.textContent = "Scanning visible text…";
  let blob = imageBlob;
  if (imageBlob) {
    clearTimeout(cameraScanTimer);
    cameraVideo.classList.add("hidden");
    if (cameraPreviewUrl) URL.revokeObjectURL(cameraPreviewUrl);
    cameraPreviewUrl = URL.createObjectURL(imageBlob);
    cameraImagePreview.src = cameraPreviewUrl;
    cameraImagePreview.classList.remove("hidden");
  }
  if (!blob) {
    const maxWidth = 1280;
    const scale = Math.min(1, maxWidth / cameraVideo.videoWidth);
    cameraCanvas.width = Math.round(cameraVideo.videoWidth * scale);
    cameraCanvas.height = Math.round(cameraVideo.videoHeight * scale);
    cameraCanvas.getContext("2d").drawImage(cameraVideo, 0, 0, cameraCanvas.width, cameraCanvas.height);
    // Compare a tiny luminance sample to the previous frame. A stationary
    // sign should not consume another paid vision request every interval.
    const sampleCanvas = document.createElement("canvas");
    sampleCanvas.width = 16;
    sampleCanvas.height = 16;
    const sampleContext = sampleCanvas.getContext("2d", { willReadFrequently: true });
    sampleContext.drawImage(cameraCanvas, 0, 0, 16, 16);
    const pixels = sampleContext.getImageData(0, 0, 16, 16).data;
    const fingerprint = [];
    for (let index = 0; index < pixels.length; index += 16) {
      fingerprint.push(Math.round((pixels[index] + pixels[index + 1] + pixels[index + 2]) / 3));
    }
    if (lastCameraFingerprint) {
      const difference = fingerprint.reduce(
        (total, value, index) => total + Math.abs(value - lastCameraFingerprint[index]), 0
      ) / fingerprint.length;
      if (difference < 7 && cameraResult) {
        cameraStatus.textContent = "View unchanged · keeping the previous translation";
        cameraScanning = false;
        btnScanCamera.disabled = false;
        return;
      }
    }
    lastCameraFingerprint = fingerprint;
    blob = await new Promise((resolve) => cameraCanvas.toBlob(resolve, "image/jpeg", 0.82));
  }
  try {
    if (!blob) throw new Error("Could not capture the camera frame.");
    const form = new FormData();
    form.append("image", blob, imageBlob?.name || "camera-frame.jpg");
    form.append("target", targetLang.value);
    const response = await fetch("/api/camera-translate", { method: "POST", body: form });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.error || "Camera translation failed.");
      error.rateLimited = response.status === 429;
      throw error;
    }
    renderCameraRegions(data);
    cameraFailures = 0;
    cameraStatus.textContent = data.translated_text
      ? `${data.detected_language || "Language detected"} · translated`
      : "No readable text found · hold the camera closer";
  } catch (error) {
    cameraFailures += 1;
    cameraStatus.textContent = error.message;
    if (error.rateLimited) {
      cameraAutoScan.checked = false;
      clearTimeout(cameraScanTimer);
      cameraStatus.textContent = "Vision limit reached · auto scan stopped. Wait for Groq’s quota to reset, then use Scan now.";
    } else if (cameraFailures >= 3) {
      cameraAutoScan.checked = false;
      cameraStatus.textContent = `${error.message} · auto scan paused; use Scan now to retry`;
    }
  } finally {
    cameraScanning = false;
    btnScanCamera.disabled = false;
  }
}

btnCamera.addEventListener("click", openCamera);
btnCloseCamera.addEventListener("click", closeCamera);
btnScanCamera.addEventListener("click", () => scanCamera());
btnFlipCamera.addEventListener("click", async () => {
  cameraFacing = cameraFacing === "environment" ? "user" : "environment";
  await startCamera();
});
cameraAutoScan.addEventListener("change", () => scheduleCameraScan(2500));
targetLang.addEventListener("change", () => {
  lastCameraFingerprint = null;
});
cameraFileInput.addEventListener("change", () => {
  const file = cameraFileInput.files?.[0];
  if (file) scanCamera(file);
  cameraFileInput.value = "";
});
["dragenter", "dragover"].forEach((name) => {
  cameraDropZone.addEventListener(name, (event) => {
    event.preventDefault();
    cameraDropZone.classList.add("dragging");
  });
});
["dragleave", "drop"].forEach((name) => {
  cameraDropZone.addEventListener(name, (event) => {
    event.preventDefault();
    cameraDropZone.classList.remove("dragging");
  });
});
cameraDropZone.addEventListener("drop", (event) => {
  const file = [...event.dataTransfer.files].find((item) => item.type.startsWith("image/"));
  if (file) scanCamera(file);
  else cameraStatus.textContent = "Drop a JPEG, PNG or WebP image.";
});
btnUseCameraText.addEventListener("click", () => {
  if (!cameraResult?.source_text) return;
  sourceText.value = cameraResult.source_text.slice(0, MAX_LEN);
  updateCharCount();
  closeCamera();
  runTranslate({ force: true });
});
btnCopyCameraText.addEventListener("click", async () => {
  if (!cameraResult?.translated_text) return;
  await navigator.clipboard.writeText(cameraResult.translated_text);
  btnCopyCameraText.textContent = "Copied!";
  setTimeout(() => { btnCopyCameraText.textContent = "Copy translation"; }, 1400);
});

// ─── Reliable voice input (record locally, transcribe with Whisper) ─────────
let voiceRecorder = null;
let voiceStream = null;
let voiceChunks = [];
let voiceStartedAt = 0;
let voiceTimer = null;
let voiceSegmentTimer = null;
let voiceLive = false;
let voiceQueue = Promise.resolve();
let voiceAudioContext = null;
let voiceMeterFrame = null;
const VOICE_SEGMENT_MS = 4500;
const VOICE_MAX_SECONDS = 120;

function setVoiceState(name, message = "") {
  btnVoiceInput.dataset.state = name;
  voiceModePanel.dataset.state = name;
  voiceOrb.dataset.state = name;
  btnVoiceInput.setAttribute("aria-label", name === "recording" ? "Stop and transcribe recording" : "Start voice input");
  voiceOrb.setAttribute("aria-label", name === "recording" ? "Stop voice translation" : "Start voice translation");
  voiceStatus.textContent = message;
  voiceModeStatus.textContent = message || (name === "idle" ? "Tap the orb and start speaking" : "");
}

function stopVoiceTracks() {
  voiceStream?.getTracks().forEach((track) => track.stop());
  voiceStream = null;
  clearInterval(voiceTimer);
  clearTimeout(voiceSegmentTimer);
  voiceTimer = null;
  voiceSegmentTimer = null;
  if (voiceMeterFrame) cancelAnimationFrame(voiceMeterFrame);
  voiceMeterFrame = null;
  voiceAudioContext?.close();
  voiceAudioContext = null;
  btnVoiceInput.style.setProperty("--voice-level", "0");
  btnVoiceInput.style.setProperty("--voice-ring", "6px");
  btnVoiceInput.style.setProperty("--voice-opacity", "0.12");
  voiceOrb.style.setProperty("--voice-level", "0");
  voiceOrb.style.setProperty("--orb-scale", "1");
  voiceOrb.style.setProperty("--wave-scale", "1");
}

async function uploadVoiceRecording(blob) {
  if (blob.size < 500) return;
  const form = new FormData();
  const extension = blob.type.includes("mp4") ? "m4a" : "webm";
  form.append("audio", blob, `rosetta-voice.${extension}`);
  form.append("language", sourceLang.value);
  try {
    const response = await fetch("/api/transcribe", { method: "POST", body: form });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Transcription failed.");
    const addition = data.text.trim();
    if (!addition) return;
    const combined = `${sourceText.value.trim()}${sourceText.value.trim() ? " " : ""}${addition}`;
    sourceText.value = combined.slice(0, MAX_LEN);
    voiceModeSource.textContent = sourceText.value;
    updateCharCount();
    voiceStatus.textContent = voiceLive ? "Listening · translating live…" : "Voice translated";
    runTranslate({ force: true });
  } catch (error) {
    voiceStatus.textContent = error.message;
  }
}

function startVoiceMeter() {
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  if (!AudioContext || !voiceStream) return;
  voiceAudioContext = new AudioContext();
  const analyser = voiceAudioContext.createAnalyser();
  analyser.fftSize = 256;
  analyser.smoothingTimeConstant = 0.74;
  voiceAudioContext.createMediaStreamSource(voiceStream).connect(analyser);
  const values = new Uint8Array(analyser.fftSize);
  const draw = () => {
    analyser.getByteTimeDomainData(values);
    let energy = 0;
    for (const value of values) {
      const sample = (value - 128) / 128;
      energy += sample * sample;
    }
    const level = Math.min(1, Math.sqrt(energy / values.length) * 5.5);
    btnVoiceInput.style.setProperty("--voice-level", level.toFixed(3));
    btnVoiceInput.style.setProperty("--voice-ring", `${6 + level * 15}px`);
    btnVoiceInput.style.setProperty("--voice-opacity", `${0.1 + level * 0.28}`);
    voiceOrb.style.setProperty("--voice-level", level.toFixed(3));
    voiceOrb.style.setProperty("--orb-scale", `${1 + level * 0.12}`);
    voiceOrb.style.setProperty("--wave-scale", `${1 + level * 0.25}`);
    voiceMeterFrame = requestAnimationFrame(draw);
  };
  draw();
}

function finishVoiceSession() {
  voiceLive = false;
  clearTimeout(voiceSegmentTimer);
  if (voiceRecorder?.state === "recording") {
    voiceRecorder.stop();
  } else {
    stopVoiceTracks();
  }
}

function startVoiceSegment() {
  if (!voiceLive || !voiceStream) return;
  const preferredType = [
    "audio/webm;codecs=opus",
    "audio/mp4",
    "audio/webm",
  ].find((type) => MediaRecorder.isTypeSupported(type));
  voiceRecorder = new MediaRecorder(voiceStream, preferredType ? { mimeType: preferredType } : undefined);
  voiceChunks = [];
  voiceRecorder.addEventListener("dataavailable", (event) => {
    if (event.data.size) voiceChunks.push(event.data);
  });
  voiceRecorder.addEventListener("stop", () => {
    const blob = new Blob(voiceChunks, { type: voiceRecorder.mimeType || "audio/webm" });
    voiceQueue = voiceQueue.then(() => uploadVoiceRecording(blob));
    if (voiceLive) startVoiceSegment();
    else {
      stopVoiceTracks();
      voiceQueue.finally(() => {
        setVoiceState("done", "Live voice translation complete");
        window.setTimeout(() => setVoiceState("idle", ""), 1800);
      });
    }
  }, { once: true });
  voiceRecorder.start(250);
  voiceSegmentTimer = setTimeout(() => {
    if (voiceRecorder?.state === "recording") voiceRecorder.stop();
  }, VOICE_SEGMENT_MS);
}

async function startVoiceRecording() {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    setVoiceState("idle", "Voice recording is not supported in this browser.");
    return;
  }
  try {
    voiceStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: { ideal: 1 },
        sampleRate: { ideal: 48000 },
        sampleSize: { ideal: 16 },
      },
    });
    sourceLang.value = "auto";
    sourceText.value = "";
    updateCharCount();
    voiceLive = true;
    voiceQueue = Promise.resolve();
    voiceStartedAt = Date.now();
    setVoiceState("recording", "Listening · auto-detecting language…");
    startVoiceMeter();
    startVoiceSegment();
    voiceTimer = setInterval(() => {
      const seconds = Math.floor((Date.now() - voiceStartedAt) / 1000);
      voiceStatus.textContent = `Live translation · ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
      voiceModeStatus.textContent = "Listening and translating…";
      voiceModeTimer.textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")} · auto-detecting language`;
      if (seconds >= VOICE_MAX_SECONDS) finishVoiceSession();
    }, 500);
  } catch (error) {
    stopVoiceTracks();
    setVoiceState(
      "idle",
      error?.name === "NotAllowedError"
        ? "Allow microphone access in browser settings."
        : "Could not open the microphone."
    );
  }
}

btnVoiceInput.addEventListener("click", () => {
  if (voiceLive) {
    finishVoiceSession();
  } else if (btnVoiceInput.dataset.state !== "processing") {
    startVoiceRecording();
  }
});
voiceOrb.addEventListener("click", () => btnVoiceInput.click());
setVoiceState("idle");
btnToolVoice.addEventListener("click", () => {
  closeTools({ restoreFocus: false });
  voiceModePanel.classList.remove("hidden");
  syncModalBackdrop();
  voiceOrb.focus();
});

function closeVoiceMode() {
  if (voiceLive) finishVoiceSession();
  voiceModePanel.classList.add("hidden");
  syncModalBackdrop();
  btnTools.focus();
}
btnCloseVoiceMode.addEventListener("click", closeVoiceMode);
btnClearVoiceMode.addEventListener("click", () => {
  sourceText.value = "";
  voiceModeSource.textContent = "Your live transcript will appear here.";
  voiceModeTarget.textContent = "Start speaking to see the translation.";
  btnCopyVoiceMode.disabled = true;
  updateCharCount();
  resetOutput();
});
btnCopyVoiceMode.addEventListener("click", async () => {
  if (!state.lastTranslation) return;
  await navigator.clipboard.writeText(state.lastTranslation);
  btnCopyVoiceMode.textContent = "Copied!";
  setTimeout(() => { btnCopyVoiceMode.textContent = "Copy translation"; }, 1400);
});

function openWriting() {
  closeTools({ restoreFocus: false });
  writingPanel.classList.remove("hidden");
  btnWriting.setAttribute("aria-expanded", "true");
  syncModalBackdrop();
  writingInput.focus();
}
function closeWriting() {
  writingPanel.classList.add("hidden");
  btnWriting.setAttribute("aria-expanded", "false");
  syncModalBackdrop();
  btnTools.focus();
}
btnWriting.addEventListener("click", () => {
  if (writingPanel.classList.contains("hidden")) openWriting();
  else closeWriting();
});
btnCloseWriting.addEventListener("click", closeWriting);
btnWritingFromSource.addEventListener("click", () => {
  writingInput.value = sourceText.value;
  openWriting();
});

function showWritingTab(name) {
  document.querySelectorAll(".writing-tab").forEach((tab) => {
    const active = tab.dataset.tab === name;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  writingOutput.innerHTML = "";
  if (name === "changes") {
    const summary = document.createElement("p");
    summary.className = "writing-summary";
    summary.textContent = writingState.summary || "Revision completed.";
    const list = document.createElement("ul");
    writingState.changes.forEach((change) => {
      const item = document.createElement("li");
      item.textContent = change;
      list.appendChild(item);
    });
    writingOutput.append(summary, list);
  } else {
    writingOutput.textContent = name === "original" ? writingState.original : writingState.revised;
  }
}
document.querySelectorAll(".writing-tab").forEach((tab) => {
  tab.addEventListener("click", () => showWritingTab(tab.dataset.tab));
});

btnRunWriting.addEventListener("click", async () => {
  const text = writingInput.value.trim();
  writingError.classList.add("hidden");
  if (!text) {
    writingError.textContent = "Add some writing first.";
    writingError.classList.remove("hidden");
    return;
  }
  btnRunWriting.disabled = true;
  btnRunWriting.textContent = "Improving…";
  try {
    const response = await fetch("/api/write", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        mode: writingMode.value,
        tone: writingTone.value,
        audience: writingAudience.value,
        preserve_terms: preserveTerms.value,
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Writing request failed.");
    Object.assign(writingState, {
      original: text,
      revised: data.revised,
      changes: data.changes || [],
      summary: data.summary || "",
    });
    writingResult.classList.remove("hidden");
    btnCopyWriting.disabled = false;
    showWritingTab("revised");
  } catch (error) {
    writingError.textContent = error.message;
    writingError.classList.remove("hidden");
  } finally {
    btnRunWriting.disabled = false;
    btnRunWriting.textContent = "Improve writing";
  }
});
btnCopyWriting.addEventListener("click", async () => {
  if (!writingState.revised) return;
  await navigator.clipboard.writeText(writingState.revised);
  btnCopyWriting.textContent = "Copied!";
  setTimeout(() => { btnCopyWriting.textContent = "Copy result"; }, 1400);
});

// BCP-47 locale tags for speechSynthesis -- our language codes are mostly
// bare ISO 639-1, which some engines accept directly, but a real locale tag
// gets a much more reliable voice match.
const SPEECH_LOCALES = {
  en: "en-US", es: "es-ES", fr: "fr-FR", de: "de-DE", it: "it-IT", pt: "pt-PT",
  ru: "ru-RU", ja: "ja-JP", ko: "ko-KR", "zh-cn": "zh-CN", "zh-tw": "zh-TW",
  ar: "ar-SA", hi: "hi-IN", nl: "nl-NL", sv: "sv-SE", no: "nb-NO", da: "da-DK",
  fi: "fi-FI", pl: "pl-PL", tr: "tr-TR", th: "th-TH", vi: "vi-VN", id: "id-ID",
  uk: "uk-UA", el: "el-GR", he: "he-IL", cs: "cs-CZ", ro: "ro-RO", hu: "hu-HU",
  bn: "bn-IN", ta: "ta-IN", te: "te-IN", ur: "ur-PK", ms: "ms-MY", sk: "sk-SK",
};

// ─── Live captions for deaf and hard-of-hearing users ──────────────────────
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let captionsActive = false;
let shouldListen = false;
let recognitionStarting = false;
let finalCaption = "";
let micStream = null;
let micContext = null;
let micAnimationFrame = null;

// Guards the automatic session reopen below from becoming a tight loop when
// the microphone can't actually be opened.
let restartAttempts = 0;
let lastRestartAt = 0;
const MAX_RESTART_ATTEMPTS = 6;
const RESTART_WINDOW_MS = 4000;

function captionLocale(code) {
  return SPEECH_LOCALES[code] || code;
}

captionLanguage.appendChild(option(navigator.language || "en-US", `Device language (${navigator.language || "en-US"})`));
LANGUAGES.forEach(([code, name]) => {
  captionLanguage.appendChild(option(captionLocale(code), `${name} (${captionLocale(code)})`));
});

function syncCaptionLanguage() {
  if (sourceLang.value === "auto") return;
  const locale = captionLocale(sourceLang.value);
  if ([...captionLanguage.options].some((item) => item.value === locale)) {
    captionLanguage.value = locale;
  }
}
sourceLang.addEventListener("change", syncCaptionLanguage);

function stopMicMeter() {
  if (micAnimationFrame) cancelAnimationFrame(micAnimationFrame);
  micAnimationFrame = null;
  micStream?.getTracks().forEach((track) => track.stop());
  micStream = null;
  // Closing matters: a browser allows only a handful of concurrent
  // AudioContexts (Chrome caps around six). Leaking one per start/stop cycle
  // meant the meter silently stopped working a few toggles into a session,
  // and the abandoned audio graphs kept costing CPU.
  micContext?.close().catch(() => {});
  micContext = null;
  micMeterFill.style.width = "0%";
  micLevelLabel.textContent = "Off";
}

async function startMicMeter() {
  if (!navigator.mediaDevices?.getUserMedia) return;
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  if (!AudioContext) return;
  micStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });
  // The user may have hit Stop while getUserMedia was still resolving.
  if (!shouldListen) {
    micStream.getTracks().forEach((track) => track.stop());
    micStream = null;
    return;
  }
  const context = new AudioContext();
  micContext = context;
  const analyser = context.createAnalyser();
  analyser.fftSize = 512;
  analyser.smoothingTimeConstant = 0.72;
  context.createMediaStreamSource(micStream).connect(analyser);
  const samples = new Uint8Array(analyser.fftSize);

  function updateMeter() {
    analyser.getByteTimeDomainData(samples);
    let sum = 0;
    for (const sample of samples) {
      const centered = (sample - 128) / 128;
      sum += centered * centered;
    }
    const level = Math.min(100, Math.sqrt(sum / samples.length) * 360);
    micMeterFill.style.width = `${Math.max(2, level)}%`;
    micLevelLabel.textContent = level < 5 ? "Low" : level < 22 ? "Good" : "Strong";
    micAnimationFrame = requestAnimationFrame(updateMeter);
  }
  updateMeter();
}

function openCaptions() {
  closeTools({ restoreFocus: false });
  captionPanel.classList.remove("hidden");
  btnCaptions.setAttribute("aria-expanded", "true");
  syncModalBackdrop();
  btnStartCaptions.focus();
}

function stopCaptions() {
  shouldListen = false;
  recognitionStarting = false;
  stopMicMeter();
  if (recognition && captionsActive) recognition.stop();
  else setCaptionActive(false);
}

function closeCaptions() {
  stopCaptions();
  captionPanel.classList.add("hidden");
  btnCaptions.setAttribute("aria-expanded", "false");
  syncModalBackdrop();
  btnTools.focus();
}

function renderCaption(interim = "") {
  captionDisplay.innerHTML = "";
  if (!finalCaption && !interim) {
    const placeholder = document.createElement("span");
    placeholder.className = "caption-placeholder";
    placeholder.textContent = "Press “Start captions” and speech will appear here.";
    captionDisplay.appendChild(placeholder);
  } else {
    const finalText = document.createElement("span");
    finalText.className = "caption-final";
    finalText.textContent = finalCaption;
    captionDisplay.appendChild(finalText);
    if (interim) {
      const interimText = document.createElement("span");
      interimText.className = "caption-interim";
      interimText.textContent = `${finalCaption ? " " : ""}${interim}`;
      captionDisplay.appendChild(interimText);
    }
  }
  btnUseCaption.disabled = !finalCaption.trim();
}

function setCaptionActive(active) {
  captionsActive = active;
  btnStartCaptions.classList.toggle("is-listening", active);
  btnStartCaptions.lastChild.textContent = active ? " Stop captions" : " Start captions";
  captionStatus.textContent = active
    ? "Listening… speech will appear visually as it is recognized."
    : "Microphone is off. Audio is processed by your browser’s speech-recognition service.";
  document.body.classList.toggle("captions-listening", active);
}

if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;

  recognition.addEventListener("start", () => {
    recognitionStarting = false;
    setCaptionActive(true);
  });
  recognition.addEventListener("end", () => {
    recognitionStarting = false;

    if (!shouldListen) {
      setCaptionActive(false);
      return;
    }

    // Chrome closes a continuous session after silence, so this fires
    // constantly during normal use -- it does not mean the user stopped.
    //
    // Two things used to make that gap expensive. The UI was flipped to
    // "microphone is off" and then back, which flickered and read as broken;
    // and the reopen waited a flat 300ms, during which nothing was captured,
    // so the first word after any pause went missing. Now the session is
    // reopened immediately (Chrome sometimes rejects a synchronous restart,
    // hence the short retry) and the UI stays "listening" throughout.
    const now = Date.now();
    if (now - lastRestartAt > RESTART_WINDOW_MS) restartAttempts = 0;
    lastRestartAt = now;
    restartAttempts += 1;

    // A mic that fails on open would otherwise end/restart in a tight loop.
    if (restartAttempts > MAX_RESTART_ATTEMPTS) {
      shouldListen = false;
      setCaptionActive(false);
      captionStatus.textContent =
        "Captioning kept dropping out. Check the microphone selection and start again.";
      return;
    }

    const reopen = () => {
      if (!shouldListen || recognitionStarting) return;
      try {
        recognition.lang = captionLanguage.value;
        recognitionStarting = true;
        recognition.start();
      } catch {
        recognitionStarting = false;
        window.setTimeout(reopen, 120);
      }
    };
    reopen();
  });
  recognition.addEventListener("error", (event) => {
    recognitionStarting = false;
    if (event.error === "not-allowed" || event.error === "service-not-allowed") {
      shouldListen = false;
      stopMicMeter();
    }
    setCaptionActive(false);
    const messages = {
      "not-allowed": "Microphone permission was denied. Allow microphone access and try again.",
      "no-speech": "No speech was detected. Check the mic level, move closer, and speak clearly.",
      "audio-capture": "No working microphone was found. Check the browser’s microphone selection.",
      network: "Speech recognition could not reach the browser service.",
    };
    captionStatus.textContent = messages[event.error] || `Captioning stopped: ${event.error}.`;
  });
  recognition.addEventListener("result", (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const text = event.results[i][0].transcript.trim();
      if (event.results[i].isFinal) {
        finalCaption += `${finalCaption ? " " : ""}${text}`;
      } else {
        interim += `${interim ? " " : ""}${text}`;
      }
    }
    renderCaption(interim);
  });

  btnStartCaptions.addEventListener("click", async () => {
    if (captionsActive) {
      stopCaptions();
      return;
    }
    if (recognitionStarting) return;
    shouldListen = true;
    recognition.lang = captionLanguage.value;
    restartAttempts = 0;
    try {
      // Recognition starts FIRST. This used to `await startMicMeter()` before
      // starting, which serialised a whole getUserMedia + AudioContext setup
      // (a few hundred ms, sometimes over a second) ahead of any listening --
      // so the first words after pressing Start were never captured at all.
      // The meter is decoration; it must never gate the microphone.
      recognitionStarting = true;
      recognition.start();
      captionStatus.textContent = `Starting microphone for ${captionLanguage.options[captionLanguage.selectedIndex].text}…`;
    } catch (error) {
      shouldListen = false;
      recognitionStarting = false;
      stopMicMeter();
      captionStatus.textContent = error?.name === "NotAllowedError"
        ? "Microphone permission was denied. Allow it in the browser’s site settings and retry."
        : "The microphone could not start. Check that another application is not using it.";
      return;
    }
    // Attached in the background. A rejection here (permission denied for the
    // meter's own stream) must not take captioning down with it, and was
    // previously an unhandled promise rejection.
    startMicMeter().catch(() => {
      micLevelLabel.textContent = "n/a";
    });
  });
} else {
  btnStartCaptions.disabled = true;
  captionStatus.textContent = "Live captions are not supported in this browser. Try the latest Chrome or Edge.";
}

btnCaptions.addEventListener("click", () => {
  if (captionPanel.classList.contains("hidden")) openCaptions();
  else closeCaptions();
});
btnCloseCaptions.addEventListener("click", closeCaptions);
btnUseCaption.addEventListener("click", () => {
  if (!finalCaption.trim()) return;
  sourceText.value = finalCaption.slice(0, MAX_LEN);
  updateCharCount();
  runTranslate({ force: true });
  document.querySelector(".card").scrollIntoView({ behavior: REDUCED_MOTION ? "auto" : "smooth" });
});
btnLargeCaption.addEventListener("click", () => {
  const active = captionPanel.classList.toggle("large-captions");
  btnLargeCaption.setAttribute("aria-pressed", String(active));
});
btnClearCaption.addEventListener("click", () => {
  finalCaption = "";
  renderCaption();
  captionStatus.textContent = captionsActive ? "Listening…" : "Caption transcript cleared.";
});

// ─── Animated links ─────────────────────────────────────────────────────────
// Links opt into the trailing ↗ with data-arrow, rather than every external
// link getting one: the glyph reserves layout width even while invisible, so
// on a link sitting mid-sentence it opens a gap before the next comma.
document.querySelectorAll("[data-arrow]").forEach((link) => {
  if (!link.querySelector(".sk-arrow")) {
    link.appendChild(arrowTemplate.content.cloneNode(true));
  }
});

// ─── Theme ──────────────────────────────────────────────────────────────────
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  themeToggle.textContent = theme === "dark" ? "◑" : "◐";
}
const savedTheme = localStorage.getItem("rosetta-theme");
if (savedTheme) applyTheme(savedTheme);
themeToggle.addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme");
  const resolved = current || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const next = resolved === "dark" ? "light" : "dark";
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
LANGUAGES.forEach(([code, name]) => voiceModeTargetLang.appendChild(option(code, name)));

const params = new URLSearchParams(location.search);
sourceLang.value = params.get("source") && [...sourceLang.options].some((o) => o.value === params.get("source"))
  ? params.get("source")
  : "auto";
targetLang.value = params.get("target") && LANGUAGES.some(([code]) => code === params.get("target"))
  ? params.get("target")
  : (LANGUAGES.some(([code]) => code === "es") ? "es" : LANGUAGES[0][0]);
voiceModeTargetLang.value = targetLang.value;
voiceModeTargetLang.addEventListener("change", () => {
  targetLang.value = voiceModeTargetLang.value;
  if (sourceText.value.trim()) runTranslate({ force: true });
});
targetLang.addEventListener("change", () => {
  voiceModeTargetLang.value = targetLang.value;
});
if (params.get("text")) sourceText.value = params.get("text").slice(0, MAX_LEN);

// ─── Char counter ───────────────────────────────────────────────────────────
function updateCharCount() {
  const n = sourceText.value.length;
  charCount.textContent = `${n} / ${MAX_LEN}`;
  charCount.classList.toggle("over-limit", n > MAX_LEN);
  charCount.classList.toggle("near-limit", n > MAX_LEN * 0.9 && n <= MAX_LEN);
  btnClear.classList.toggle("hidden", n === 0);
}

// ─── URL state (shareable links) ────────────────────────────────────────────
function syncUrl() {
  const text = sourceText.value;
  if (!text.trim()) {
    history.replaceState(null, "", location.pathname);
    return;
  }
  const qs = new URLSearchParams({ text, source: sourceLang.value, target: targetLang.value });
  history.replaceState(null, "", `?${qs.toString()}`);
}

// ─── History (localStorage) ─────────────────────────────────────────────────
function loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveHistory(entries) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(entries.slice(0, MAX_HISTORY)));
  } catch {
    // Quota exceeded or storage disabled -- history is a convenience, not a
    // feature worth breaking a translation over.
  }
}

function addToHistory(entry) {
  const entries = loadHistory().filter(
    (e) => !(e.text === entry.text && e.source === entry.source && e.target === entry.target)
  );
  entries.unshift(entry);
  saveHistory(entries);
  renderHistory();
}

function langLabel(code) {
  if (code === "auto") return "Detect";
  const found = LANGUAGES.find(([c]) => c === code);
  return found ? found[1] : code;
}

function renderHistory() {
  const entries = loadHistory();
  historyList.innerHTML = "";
  if (!entries.length) {
    const empty = document.createElement("li");
    empty.className = "history-empty";
    empty.textContent = "No translations yet.";
    historyList.appendChild(empty);
    return;
  }
  entries.forEach((entry, i) => {
    const li = document.createElement("li");
    li.className = "history-item";
    li.style.animationDelay = `${i * 30}ms`;

    const orig = document.createElement("div");
    orig.className = "h-original";
    orig.textContent = entry.text;

    const translated = document.createElement("div");
    translated.className = "h-translated";
    translated.textContent = entry.translated_text || "";

    const meta = document.createElement("div");
    meta.className = "h-meta";
    meta.textContent = `${langLabel(entry.source)} → ${langLabel(entry.target)}`;

    li.append(orig, translated, meta);
    li.addEventListener("click", () => {
      sourceLang.value = entry.source;
      targetLang.value = entry.target;
      sourceText.value = entry.text;
      updateCharCount();
      closeHistory();
      runTranslate();
    });
    historyList.appendChild(li);
  });
}

function closeHistory() {
  historyPanel.classList.add("hidden");
  btnHistory.setAttribute("aria-expanded", "false");
}

btnHistory.addEventListener("click", () => {
  const opening = historyPanel.classList.contains("hidden");
  historyPanel.classList.toggle("hidden", !opening);
  btnHistory.setAttribute("aria-expanded", String(opening));
  if (opening) renderHistory();
});
btnClearHistory.addEventListener("click", () => {
  saveHistory([]);
  renderHistory();
});

// ─── Alternates ─────────────────────────────────────────────────────────────
function renderAlternates(alternates) {
  alternatesRow.innerHTML = "";
  if (!alternates || !alternates.length) {
    alternatesRow.classList.add("hidden");
    return;
  }
  alternates.forEach((alt, i) => {
    const chip = document.createElement("button");
    // sk-rise: the inverting bar from Skiper 40, which reads as "picking" the
    // chip rather than merely hovering it.
    chip.className = "alternate-chip sk-rise";
    chip.type = "button";
    chip.textContent = alt;
    chip.style.animationDelay = `${i * 40}ms`;
    chip.addEventListener("click", () => {
      // Swap the chosen phrasing into the output and demote the current one,
      // so the alternates list stays a complete set of the options.
      //
      // Read the label off the chip rather than using `alt` from this
      // closure: the swap rewrites the chip's text, so after one click `alt`
      // no longer matches what the chip shows. Trusting it made a second
      // click re-display the phrasing already on screen and overwrite the
      // demoted original, which was then unrecoverable without retranslating.
      const chosen = chip.textContent;
      if (!chosen || chosen === state.lastTranslation) return;
      chip.textContent = state.lastTranslation;
      setTranslationDisplay(chosen);
      state.lastTranslation = chosen;
      btnCopy.disabled = false;
      btnSpeak.disabled = false;
    });
    alternatesRow.appendChild(chip);
  });
  alternatesRow.classList.remove("hidden");
}

// ─── Rendering the translated text ──────────────────────────────────────────
/**
 * Reveal the translation a word at a time.
 *
 * The provider answers in one shot, so there's nothing to stream -- but a
 * staggered per-word fade gives the arrival the same sense of being written
 * out, without the SSE plumbing (and its buffering problems on serverless).
 * Whitespace is preserved as its own text node so line breaks survive.
 */
function setTranslationDisplay(text) {
  voiceModeTarget.textContent = text;
  btnCopyVoiceMode.disabled = false;
  targetText.classList.remove("animate-in");
  targetText.innerHTML = "";

  const parts = text.split(/(\s+)/);
  const wordCount = parts.filter((p) => p.trim()).length;

  if (REDUCED_MOTION || wordCount > MAX_STAGGERED_WORDS) {
    targetText.textContent = text;
    void targetText.offsetWidth; // force reflow so the animation can restart
    if (!REDUCED_MOTION) targetText.classList.add("animate-in");
    return;
  }

  let index = 0;
  parts.forEach((part) => {
    if (!part.trim()) {
      targetText.appendChild(document.createTextNode(part));
      return;
    }
    const span = document.createElement("span");
    span.className = "word";
    span.textContent = part;
    span.style.animationDelay = `${index * 28}ms`;
    index += 1;
    targetText.appendChild(span);
  });
}

function showHint() {
  targetText.innerHTML = "";
  const hint = document.createElement("span");
  hint.className = "hint";
  hint.textContent = "Translation will appear here.";
  targetText.appendChild(hint);
}

function setLoading(loading) {
  skeleton.classList.toggle("hidden", !loading);
  targetText.classList.toggle("loading", loading);
  targetText.setAttribute("aria-busy", String(loading));
}

function setStatus(text, kind = "") {
  statusPill.textContent = text;
  statusPill.className = kind ? `status-pill ${kind}` : "status-pill";
}

function showError(message) {
  errorBanner.textContent = message;
  errorBanner.classList.remove("hidden");
}

function resetOutput() {
  showHint();
  detectedPill.classList.add("hidden");
  romanizationLine.classList.add("hidden");
  noteLine.classList.add("hidden");
  setStatus("");
  btnCopy.disabled = true;
  btnSpeak.disabled = true;
  renderAlternates([]);
  state.lastTranslation = "";
  state.lastRequestKey = null;
}

// ─── Translate ──────────────────────────────────────────────────────────────
let debounceTimer = null;
function scheduleTranslate() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(runTranslate, DEBOUNCE_MS);
}

async function runTranslate({ force = false } = {}) {
  clearTimeout(debounceTimer);
  const text = sourceText.value;
  errorBanner.classList.add("hidden");

  if (!text.trim()) {
    state.inFlight?.abort();
    state.inFlight = null;
    setLoading(false);
    resetOutput();
    syncUrl();
    return;
  }

  const requestKey = `${sourceLang.value}|${targetLang.value}|${text}`;
  // The debounce fires on every keystroke, including ones that don't change
  // the request (arrow keys, re-selecting the same language).
  if (!force && requestKey === state.lastRequestKey) return;

  // Cancel whatever is in flight. Without this, a slow earlier request can
  // land after a fast later one and overwrite the newer translation.
  state.inFlight?.abort();
  const controller = new AbortController();
  state.inFlight = controller;
  const seq = ++state.seq;

  setLoading(true);
  setStatus("translating…");

  try {
    const res = await fetch("/api/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, source: sourceLang.value, target: targetLang.value }),
      signal: controller.signal,
    });
    const data = await res.json().catch(() => ({}));

    // A response from a superseded request is stale by definition -- drop it.
    if (seq !== state.seq) return;
    setLoading(false);

    if (!res.ok) {
      setStatus("error", "err");
      showError(data.error || `translation failed (${res.status})`);
      return;
    }

    state.lastRequestKey = requestKey;
    setTranslationDisplay(data.translated_text);
    state.lastTranslation = data.translated_text;
    btnCopy.disabled = false;
    btnSpeak.disabled = false;
    renderAlternates(data.alternates);

    if (data.romanization) {
      romanizationLine.textContent = data.romanization;
      romanizationLine.classList.remove("hidden");
    } else {
      romanizationLine.classList.add("hidden");
    }

    if (data.note) {
      noteLine.textContent = data.note;
      noteLine.classList.remove("hidden");
    } else {
      noteLine.classList.add("hidden");
    }

    if (data.detected_source) {
      state.lastDetected = data.detected_source;
      detectedPill.textContent = `Detected: ${data.detected_source_name || data.detected_source}`;
      detectedPill.title = "Click to lock this as the source language";
      detectedPill.classList.remove("hidden");
    } else {
      detectedPill.classList.add("hidden");
    }

    // The badge shows the configured engine; say so when a request actually
    // came back from the fallback instead, rather than quietly downgrading.
    const degraded = CONFIG.provider === "groq" && data.provider === "mymemory";
    engineBadge.classList.toggle("degraded", degraded);
    engineBadge.title = degraded
      ? "Groq was unavailable — this translation came from MyMemory"
      : "Active translation engine";

    if (data.cached) setStatus("cached", "ok");
    else if (degraded) setStatus("fallback", "warn");
    else setStatus("done", "ok");

    addToHistory({
      text,
      source: sourceLang.value,
      target: targetLang.value,
      translated_text: data.translated_text,
    });
    syncUrl();
  } catch (err) {
    if (err.name === "AbortError") return; // superseded on purpose
    if (seq !== state.seq) return;
    setLoading(false);
    setStatus("error", "err");
    showError("network error — could not reach the server");
  } finally {
    if (state.inFlight === controller) state.inFlight = null;
  }
}

sourceText.addEventListener("input", () => {
  updateCharCount();
  scheduleTranslate();
});
sourceLang.addEventListener("change", () => runTranslate({ force: true }));
targetLang.addEventListener("change", () => runTranslate({ force: true }));

// Clicking the detected pill promotes the guess to an explicit choice.
detectedPill.addEventListener("click", () => {
  if (!state.lastDetected) return;
  sourceLang.value = state.lastDetected;
  detectedPill.classList.add("hidden");
  runTranslate({ force: true });
});

btnClear.addEventListener("click", () => {
  sourceText.value = "";
  updateCharCount();
  runTranslate();
  sourceText.focus();
});

// ─── Swap ───────────────────────────────────────────────────────────────────
function swapLanguages() {
  // Bail before animating. Spinning the button on a swap that can't happen
  // (source is "auto" and nothing has been detected yet) reports success for
  // a no-op, which reads as the control being broken rather than not-yet-ready.
  if (sourceLang.value === "auto" && !state.lastDetected) return;

  btnSwap.classList.remove("spinning");
  void btnSwap.offsetWidth;
  btnSwap.classList.add("spinning");

  if (sourceLang.value === "auto") {
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
  runTranslate({ force: true });
}
btnSwap.addEventListener("click", swapLanguages);

// ─── Copy ───────────────────────────────────────────────────────────────────
async function copyTranslation() {
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
}
btnCopy.addEventListener("click", copyTranslation);

// ─── Speak ──────────────────────────────────────────────────────────────────
btnSpeak.addEventListener("click", () => {
  if (!state.lastTranslation || !("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel(); // stop anything already playing
  const utterance = new SpeechSynthesisUtterance(state.lastTranslation);
  utterance.lang = SPEECH_LOCALES[targetLang.value] || targetLang.value;
  window.speechSynthesis.speak(utterance);
});
if (!("speechSynthesis" in window)) {
  btnSpeak.classList.add("hidden");
}

// ─── Keyboard shortcuts ─────────────────────────────────────────────────────
document.addEventListener("keydown", (evt) => {
  const mod = evt.metaKey || evt.ctrlKey;
  const letter = (evt.key || "").toLowerCase();

  // Matched on `code` (the physical key), not `key`. Option acts as a compose
  // modifier on macOS, so Option+C arrives as "ç" and a `key`-based test never
  // fires -- the shortcut advertised on the button was dead on every Mac.
  // `key` is kept as the fallback for browsers that don't report `code`.
  if (evt.altKey && (evt.code === "KeyC" || letter === "c")) {
    evt.preventDefault();
    if (captionPanel.classList.contains("hidden")) openCaptions();
    else closeCaptions();
    return;
  }

  if (evt.key === "Escape") {
    if (!captionPanel.classList.contains("hidden")) {
      closeCaptions();
    } else if (!writingPanel.classList.contains("hidden")) {
      closeWriting();
    } else if (!cameraPanel.classList.contains("hidden")) {
      closeCamera();
    } else if (!voiceModePanel.classList.contains("hidden")) {
      closeVoiceMode();
    } else if (!companionPanel.classList.contains("hidden")) {
      closeCompanion();
    } else if (!toolsPanel.classList.contains("hidden")) {
      closeTools();
    } else if (!historyPanel.classList.contains("hidden")) {
      closeHistory();
    } else if (sourceText.value) {
      sourceText.value = "";
      updateCharCount();
      runTranslate();
    }
    return;
  }
  if (!mod) return;

  // Cmd/Ctrl don't compose characters the way Option does, so `key` is safe
  // here and stays correct on non-QWERTY layouts where `code` would not.
  if (evt.key === "Enter") {
    evt.preventDefault();
    runTranslate({ force: true });
  } else if (evt.shiftKey && letter === "s") {
    evt.preventDefault();
    swapLanguages();
  } else if (evt.shiftKey && letter === "c") {
    evt.preventDefault();
    copyTranslation();
  }
});

updateCharCount();
renderHistory();
if (sourceText.value.trim()) runTranslate();
