/**
 * Liquid ripple background: a full-viewport WebGL canvas behind the UI.
 *
 * A hand-written GLSL ripple simulation (not a copy of any third-party shader):
 * each recent mouse position spawns a decaying sine-wave ripple; the sum of
 * active ripples distorts a slowly-flowing color field and adds a highlight.
 * Falls back to no-op if WebGL is unavailable, and freezes on
 * prefers-reduced-motion (a static single frame instead of a moving one).
 */
import * as THREE from "three";

const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const MAX_RIPPLES = 8;
const RIPPLE_LIFETIME = 3.0; // seconds
const RIPPLE_THROTTLE_MS = 55;

const PALETTES = {
  dark: {
    a: new THREE.Color(0x0d1220),
    b: new THREE.Color(0x1c2b5e),
    c: new THREE.Color(0x5b3aa0),
    opacity: 0.55,
  },
  light: {
    a: new THREE.Color(0xeaf0ff),
    b: new THREE.Color(0xcfe0ff),
    c: new THREE.Color(0xe3d6ff),
    opacity: 0.6,
  },
};

// Mirror the CSS: an explicit data-theme wins, otherwise fall back to the OS
// preference. Reading only the attribute would default to dark and mismatch a
// light-mode page whose user hasn't toggled the theme yet.
function resolveTheme() {
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "light" || attr === "dark") return attr;
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

const VERTEX_SHADER = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = vec4(position.xy, 0.0, 1.0);
  }
`;

const FRAGMENT_SHADER = /* glsl */ `
  precision highp float;
  varying vec2 vUv;

  uniform float uTime;
  uniform vec2 uResolution;
  uniform vec3 uColorA;
  uniform vec3 uColorB;
  uniform vec3 uColorC;
  uniform float uOpacity;
  uniform vec2 uRippleOrigin[${MAX_RIPPLES}];
  uniform float uRippleStart[${MAX_RIPPLES}];

  float rippleContribution(vec2 uv, vec2 origin, float startTime) {
    float age = uTime - startTime;
    if (age < 0.0 || age > ${RIPPLE_LIFETIME.toFixed(1)}) return 0.0;
    float dist = distance(uv, origin);
    float wave = sin(dist * 45.0 - age * 7.0);
    float envelope = exp(-dist * 5.5) * exp(-age * 1.3);
    return wave * envelope;
  }

  void main() {
    vec2 uv = vUv;
    float aspect = uResolution.x / uResolution.y;
    vec2 aspectUv = vec2(uv.x * aspect, uv.y);

    float ripple = 0.0;
    for (int i = 0; i < ${MAX_RIPPLES}; i++) {
      vec2 origin = vec2(uRippleOrigin[i].x * aspect, uRippleOrigin[i].y);
      ripple += rippleContribution(aspectUv, origin, uRippleStart[i]);
    }

    vec2 distortedUv = uv + ripple * 0.018;

    float flow = sin((distortedUv.x + uTime * 0.045) * 2.6) * cos((distortedUv.y - uTime * 0.035) * 2.6);
    float t = 0.5 + 0.5 * flow;

    vec3 color = mix(uColorA, uColorB, t);
    float blend = 0.5 + 0.5 * sin(uTime * 0.12 + distortedUv.x * 1.8 + distortedUv.y * 1.2);
    color = mix(color, uColorC, blend * 0.55);
    color += vec3(1.0) * clamp(ripple, 0.0, 1.0) * 0.16;

    gl_FragColor = vec4(color, uOpacity);
  }
`;

function makeCanvasHost() {
  const host = document.createElement("div");
  host.id = "liquid-bg";
  host.setAttribute("aria-hidden", "true");
  document.body.prepend(host);
  return host;
}

function supportsWebGL() {
  try {
    const canvas = document.createElement("canvas");
    return !!(canvas.getContext("webgl") || canvas.getContext("experimental-webgl"));
  } catch {
    return false;
  }
}

export function initLiquidBackground() {
  if (!supportsWebGL()) return;

  const host = makeCanvasHost();
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  host.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.Camera(); // shader writes gl_Position directly; camera unused by the material

  const ripples = Array.from({ length: MAX_RIPPLES }, () => ({
    origin: new THREE.Vector2(0.5, 0.5),
    start: -9999,
  }));
  let ringIndex = 0;

  const palette = PALETTES[resolveTheme()];

  const uniforms = {
    uTime: { value: 0 },
    uResolution: { value: new THREE.Vector2(window.innerWidth, window.innerHeight) },
    uColorA: { value: palette.a.clone() },
    uColorB: { value: palette.b.clone() },
    uColorC: { value: palette.c.clone() },
    uOpacity: { value: palette.opacity },
    uRippleOrigin: { value: ripples.map((r) => r.origin) },
    uRippleStart: { value: ripples.map((r) => r.start) },
  };

  const material = new THREE.ShaderMaterial({
    vertexShader: VERTEX_SHADER,
    fragmentShader: FRAGMENT_SHADER,
    uniforms,
    transparent: true,
    depthTest: false,
    depthWrite: false,
  });

  const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material);
  scene.add(quad);

  function resize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    renderer.setSize(w, h);
    uniforms.uResolution.value.set(w, h);
  }
  resize();
  window.addEventListener("resize", resize);

  function addRipple(clientX, clientY) {
    const x = clientX / window.innerWidth;
    const y = 1 - clientY / window.innerHeight;
    const slot = ripples[ringIndex];
    slot.origin.set(x, y);
    slot.start = uniforms.uTime.value;
    // uRippleStart holds primitives, so reassigning slot.start doesn't reach
    // the uniform the way slot.origin (a shared Vector2, mutated in place) does.
    // Write the start time into the uniform array itself, or ripples never fire.
    uniforms.uRippleStart.value[ringIndex] = slot.start;
    ringIndex = (ringIndex + 1) % MAX_RIPPLES;
  }

  let lastRippleAt = 0;
  window.addEventListener("pointermove", (evt) => {
    const now = performance.now();
    if (now - lastRippleAt < RIPPLE_THROTTLE_MS) return;
    lastRippleAt = now;
    addRipple(evt.clientX, evt.clientY);
  });
  window.addEventListener("pointerdown", (evt) => addRipple(evt.clientX, evt.clientY));

  // React to theme changes regardless of who triggers them.
  const themeObserver = new MutationObserver(() => {
    const theme = document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
    const next = PALETTES[theme];
    uniforms.uColorA.value.copy(next.a);
    uniforms.uColorB.value.copy(next.b);
    uniforms.uColorC.value.copy(next.c);
    uniforms.uOpacity.value = next.opacity;
  });
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  const clock = new THREE.Clock();

  function renderFrame() {
    uniforms.uTime.value = clock.getElapsedTime();
    renderer.render(scene, camera);
  }

  if (REDUCED_MOTION) {
    renderFrame(); // one static frame, no rAF loop, no ripple listeners firing renders
    return;
  }

  function tick() {
    renderFrame();
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

initLiquidBackground();
