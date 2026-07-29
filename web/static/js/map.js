/**
 * Language Map: choose a language by its place on the globe.
 *
 * The backdrop is a graticule -- the real grid of meridians and parallels --
 * not a drawn coastline. That is a deliberate choice rather than a shortcut:
 * a hand-approximated world outline would be invented geometry sitting
 * underneath markers whose whole value is being at true coordinates. A
 * graticule is exact by construction, so nothing on this map is guessed.
 *
 * Marker positions come from the server already projected (equirectangular),
 * so the client does no geography of its own.
 *
 * Loaded after app.js, so it shares that global lexical scope for `el`,
 * `LANGUAGES`, `closeTools`, `syncModalBackdrop`, `targetLang` and friends.
 */

const mapPanel = el("map-panel");
const btnCloseMap = el("btn-close-map");
const mapSvg = el("map-svg");
const mapGraticule = el("map-graticule");
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
