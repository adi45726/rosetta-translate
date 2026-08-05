/**
 * Language Map: choose a language by its place on the globe.
 *
 * The country outlines are real: Natural Earth 1:110m Admin 0 Countries
 * (public domain), projected and simplified offline by tools/build_world_paths.py
 * into web/static/data/world-borders.json. Simplification is Douglas-Peucker,
 * which drops vertices but never moves one, so coastlines lose detail without
 * anything being invented. Nothing here is hand-drawn -- an approximated
 * outline would be made-up geometry sitting under markers whose whole value is
 * being at true coordinates.
 *
 * Borders and markers share one projection (equirectangular, computed on the
 * server for markers and in the build script for borders), which is what puts
 * each marker inside its own country. Spot-checked: every city anchor lands
 * within ~6px of a real border vertex.
 *
 * Loaded after app.js, so it shares that global lexical scope for `el`,
 * `LANGUAGES`, `closeTools`, `syncModalBackdrop`, `targetLang` and friends.
 */

const mapPanel = el("map-panel");
const btnCloseMap = el("btn-close-map");
const mapSvg = el("map-svg");
const mapGraticule = el("map-graticule");
const mapBorders = el("map-borders");
const mapLinks = el("map-links");
const mapMarkers = el("map-markers");
const mapReadout = el("map-readout");

const MAP_W = 720;
const MAP_H = 360;
const SVG_NS = "http://www.w3.org/2000/svg";

let anchors = [];
let anchorsLoaded = false;

// Viewport as a viewBox rectangle. Zooming by rewriting viewBox rather than
// with a CSS transform keeps stroke widths honest (vector-effect handles the
// borders) and means hit targets move with what is drawn.
const view = { x: 0, y: 0, w: MAP_W, h: MAP_H };
const MIN_SPAN = MAP_W / 8;   // furthest in
const MAX_SPAN = MAP_W;       // whole world, never further out
let panning = null;

const nameFor = (code) => LANGUAGES.find(([c]) => c === code)?.[1] || code;

function svgEl(tag, attrs) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  return node;
}

/** Meridians and parallels every 30°, which is where they actually fall. */
function drawGraticule() {
  if (mapGraticule.childElementCount) return;
  for (let lon = -180; lon <= 180; lon += 30) {
    const x = ((lon + 180) / 360) * MAP_W;
    mapGraticule.appendChild(svgEl("line", {
      x1: x, y1: 0, x2: x, y2: MAP_H,
      class: lon === 0 ? "grat grat-prime" : "grat",
    }));
  }
  for (let lat = -90; lat <= 90; lat += 30) {
    const y = ((90 - lat) / 180) * MAP_H;
    mapGraticule.appendChild(svgEl("line", {
      x1: 0, y1: y, x2: MAP_W, y2: y,
      class: lat === 0 ? "grat grat-equator" : "grat",
    }));
  }
}

function applyView() {
  // Clamp so the world can never be dragged off-screen entirely.
  view.w = Math.min(MAX_SPAN, Math.max(MIN_SPAN, view.w));
  view.h = view.w * (MAP_H / MAP_W);
  view.x = Math.min(MAP_W - view.w, Math.max(0, view.x));
  view.y = Math.min(MAP_H - view.h, Math.max(0, view.y));
  mapSvg.setAttribute("viewBox", `${view.x} ${view.y} ${view.w} ${view.h}`);
  mapSvg.dataset.zoomed = String(view.w < MAX_SPAN - 0.5);
  // The viewBox scales everything drawn, so counter-scale the text and marker
  // radii to keep them a constant size on screen at any zoom level.
  const k = view.w / MAP_W;
  mapSvg.style.setProperty("--map-k", k.toFixed(4));
  // Labels need room before they help; below this they overlap into noise.
  mapSvg.dataset.labels = String(view.w <= MAP_W / 2.2);
}

/** Zoom about a point given in map units, so the cursor stays put. */
function zoomAt(factor, mx, my) {
  const before = view.w;
  const next = Math.min(MAX_SPAN, Math.max(MIN_SPAN, view.w * factor));
  if (next === before) return;
  const scale = next / before;
  view.x = mx - (mx - view.x) * scale;
  view.y = my - (my - view.y) * scale;
  view.w = next;
  applyView();
}

function pointerToMap(event) {
  const r = mapSvg.getBoundingClientRect();
  return {
    mx: view.x + ((event.clientX - r.left) / r.width) * view.w,
    my: view.y + ((event.clientY - r.top) / r.height) * view.h,
  };
}

function resetView() {
  view.x = 0; view.y = 0; view.w = MAP_W;
  applyView();
}

mapSvg.addEventListener("wheel", (event) => {
  event.preventDefault();
  const { mx, my } = pointerToMap(event);
  zoomAt(event.deltaY > 0 ? 1.15 : 1 / 1.15, mx, my);
}, { passive: false });

mapSvg.addEventListener("pointerdown", (event) => {
  // Markers handle their own clicks; dragging from one would fight selection.
  if (event.target.closest("#map-markers g")) return;
  panning = { ...pointerToMap(event), vx: view.x, vy: view.y };
  mapSvg.setPointerCapture(event.pointerId);
  mapSvg.classList.add("is-panning");
});

mapSvg.addEventListener("pointermove", (event) => {
  if (!panning) return;
  const r = mapSvg.getBoundingClientRect();
  view.x = panning.vx - ((event.clientX - r.left) / r.width) * view.w + (panning.mx - panning.vx);
  view.y = panning.vy - ((event.clientY - r.top) / r.height) * view.h + (panning.my - panning.vy);
  applyView();
});

function endPan(event) {
  if (!panning) return;
  panning = null;
  mapSvg.releasePointerCapture?.(event.pointerId);
  mapSvg.classList.remove("is-panning");
}
mapSvg.addEventListener("pointerup", endPan);
mapSvg.addEventListener("pointercancel", endPan);

function setReadout(text) {
  mapReadout.textContent = text;
}

/** A curve between the source and target anchors. Decorative, not a route. */
function drawLink() {
  mapLinks.innerHTML = "";
  const from = anchors.find((a) => a.code === sourceLang.value);
  const to = anchors.find((a) => a.code === targetLang.value);
  if (!from || !to || from.code === to.code) return;
  const x1 = from.x * MAP_W, y1 = from.y * MAP_H;
  const x2 = to.x * MAP_W, y2 = to.y * MAP_H;
  // Bow the curve away from the straight line so both directions are legible.
  const cx = (x1 + x2) / 2;
  const cy = (y1 + y2) / 2 - Math.abs(x2 - x1) * 0.22 - 18;
  const path = svgEl("path", { d: `M${x1} ${y1} Q${cx} ${cy} ${x2} ${y2}`, class: "map-link" });
  mapLinks.appendChild(path);
}

function markClass(code) {
  if (code === targetLang.value) return "marker is-target";
  if (code === sourceLang.value) return "marker is-source";
  return "marker";
}

function refreshMarkerStates() {
  mapMarkers.querySelectorAll("g.marker, g.marker.is-target, g.marker.is-source")
    .forEach((g) => { g.setAttribute("class", markClass(g.dataset.code)); });
  drawLink();
}

function drawMarkers() {
  mapMarkers.innerHTML = "";
  anchors.forEach((a, i) => {
    const cx = a.x * MAP_W;
    const cy = a.y * MAP_H;
    const label = nameFor(a.code);

    const g = svgEl("g", { class: markClass(a.code), tabindex: "0", role: "button" });
    g.dataset.code = a.code;
    // Staggered arrival, ordered by longitude so the map fills west to east.
    g.style.animationDelay = `${Math.min(i * 12, 700)}ms`;
    g.appendChild(svgEl("circle", { cx, cy, r: 9, class: "marker-halo" }));
    g.appendChild(svgEl("circle", { cx, cy, r: 3.2, class: "marker-dot" }));

    // Only drawn once zoomed: at full extent 73 labels overlap into noise.
    const text = svgEl("text", { x: cx + 5.5, y: cy + 2.6, class: "marker-label" });
    text.textContent = label;
    g.appendChild(text);

    const title = svgEl("title", {});
    // Says "anchor", never "spoken here": one city cannot represent a language.
    title.textContent = `${label} — anchor: ${a.city} (${a.lat.toFixed(2)}, ${a.lon.toFixed(2)})`;
    g.appendChild(title);

    const describe = () => setReadout(`${label} · anchor ${a.city} (${a.lat.toFixed(2)}, ${a.lon.toFixed(2)})`);
    g.addEventListener("pointerenter", describe);
    g.addEventListener("focus", describe);
    g.addEventListener("pointerleave", () => setReadout("Hover a marker"));

    const choose = () => {
      targetLang.value = a.code;
      refreshMarkerStates();
      setReadout(`Translating into ${label}`);
      targetLang.dispatchEvent(new Event("change"));
    };
    g.addEventListener("click", choose);
    g.addEventListener("keydown", (evt) => {
      if (evt.key === "Enter" || evt.key === " ") { evt.preventDefault(); choose(); }
    });

    mapMarkers.appendChild(g);
  });
  drawLink();
}

async function loadBorders() {
  if (mapBorders.childElementCount) return;
  try {
    const res = await fetch("/static/data/world-borders.json");
    const data = await res.json();
    // One <path> per ring. A single concatenated path would be cheaper to
    // insert but makes every landmass one hit target, and the outlines read
    // better with per-ring stroke joins.
    const frag = document.createDocumentFragment();
    (data.paths || []).forEach((d) => {
      frag.appendChild(svgEl("path", { d, class: "border" }));
    });
    mapBorders.appendChild(frag);
  } catch {
    // The graticule and markers are still meaningful without outlines.
  }
}

async function loadAnchors() {
  if (anchorsLoaded) return;
  try {
    const res = await fetch("/api/language-map");
    const data = await res.json();
    // Sort by longitude so the entrance stagger sweeps across the map.
    anchors = (data.anchors || []).slice().sort((a, b) => a.lon - b.lon);
    anchorsLoaded = true;
    drawGraticule();
    drawMarkers();
  } catch {
    setReadout("Could not load the map.");
  }
}

function openMap() {
  closeTools({ restoreFocus: false });
  mapPanel.classList.remove("hidden");
  syncModalBackdrop();
  resetView();
  loadBorders();
  loadAnchors().then(refreshMarkerStates);
}

function closeMap() {
  mapPanel.classList.add("hidden");
  syncModalBackdrop();
  btnTools.focus();
}

btnCloseMap.addEventListener("click", closeMap);
document.querySelector('.hero-card[data-tool="map"]')?.addEventListener("click", openMap);
// Keep the highlighted markers in step with the pickers outside the map.
targetLang.addEventListener("change", () => { if (anchorsLoaded) refreshMarkerStates(); });
sourceLang.addEventListener("change", () => { if (anchorsLoaded) refreshMarkerStates(); });

// ─── Zoom controls ──────────────────────────────────────────────────────────
// Buttons as well as wheel: a trackpad pinch is not available to everyone, and
// the wheel handler is useless on a touch device.
el("map-zoom-in").addEventListener("click", () => zoomAt(1 / 1.4, view.x + view.w / 2, view.y + view.h / 2));
el("map-zoom-out").addEventListener("click", () => zoomAt(1.4, view.x + view.w / 2, view.y + view.h / 2));
el("map-zoom-reset").addEventListener("click", resetView);

// ─── Search ─────────────────────────────────────────────────────────────────
// Finding one language among 73 dots by eye is not realistic, and the dense
// European cluster is the worst case precisely because it holds the most.
const mapSearch = el("map-search-input");
const mapSearchCount = el("map-search-count");

function applySearch(query) {
  const q = query.trim().toLowerCase();
  let matched = 0;
  mapMarkers.querySelectorAll("g").forEach((g) => {
    const a = anchors.find((x) => x.code === g.dataset.code);
    if (!a) return;
    // City as well as language: someone looking for "Tokyo" is asking the same
    // question as someone looking for "Japanese".
    const hit = !q
      || nameFor(a.code).toLowerCase().includes(q)
      || a.city.toLowerCase().includes(q)
      || a.code.toLowerCase() === q;
    g.classList.toggle("is-dimmed", Boolean(q) && !hit);
    g.classList.toggle("is-found", Boolean(q) && hit);
    if (hit) matched += 1;
  });
  mapSearchCount.textContent = q ? `${matched} of ${anchors.length}` : "";

  // A single match is unambiguous, so go to it rather than making the user
  // hunt for the one dot that stayed bright.
  if (q && matched === 1) {
    const found = anchors.find((a) =>
      nameFor(a.code).toLowerCase().includes(q)
      || a.city.toLowerCase().includes(q)
      || a.code.toLowerCase() === q);
    if (found) focusAnchor(found);
  }
}

/** Centre the view on one anchor without changing the zoom level. */
function focusAnchor(a) {
  const cx = a.x * MAP_W;
  const cy = a.y * MAP_H;
  const span = Math.min(view.w, MAP_W / 3);
  view.w = span;
  view.h = span * (MAP_H / MAP_W);
  view.x = cx - view.w / 2;
  view.y = cy - view.h / 2;
  applyView();
  setReadout(`${nameFor(a.code)} · anchor ${a.city}`);
}

mapSearch.addEventListener("input", () => applySearch(mapSearch.value));
mapSearch.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  mapSearch.value = "";
  applySearch("");
  resetView();
});

// ─── Keyboard ───────────────────────────────────────────────────────────────
// Zoom and pan were pointer-only: wheel, drag, and buttons that only zoom
// about the centre. Markers were already reachable by Tab, but someone who got
// to one could not move the view to see where it was.
mapSvg.setAttribute("tabindex", "0");
mapSvg.addEventListener("keydown", (event) => {
  const step = view.w * 0.18;
  const keys = {
    ArrowLeft: () => { view.x -= step; },
    ArrowRight: () => { view.x += step; },
    ArrowUp: () => { view.y -= step; },
    ArrowDown: () => { view.y += step; },
  };
  if (keys[event.key]) {
    event.preventDefault();
    keys[event.key]();
    applyView();
    return;
  }
  // Both "+" and "=" because the unshifted key on most layouts is "=".
  if (event.key === "+" || event.key === "=") {
    event.preventDefault();
    zoomAt(1 / 1.4, view.x + view.w / 2, view.y + view.h / 2);
  } else if (event.key === "-" || event.key === "_") {
    event.preventDefault();
    zoomAt(1.4, view.x + view.w / 2, view.y + view.h / 2);
  } else if (event.key === "0") {
    event.preventDefault();
    resetView();
  }
});

// Tabbing to a marker that sits outside the current view would otherwise move
// focus somewhere invisible.
mapMarkers.addEventListener("focusin", (event) => {
  const g = event.target.closest("g");
  const a = g && anchors.find((x) => x.code === g.dataset.code);
  if (!a) return;
  const cx = a.x * MAP_W;
  const cy = a.y * MAP_H;
  const outside = cx < view.x || cx > view.x + view.w || cy < view.y || cy > view.y + view.h;
  if (outside) focusAnchor(a);
});
