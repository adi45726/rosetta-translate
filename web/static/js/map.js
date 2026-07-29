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
