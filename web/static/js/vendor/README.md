# Vendored dependencies

- `three.module.min.js` and `three.core.min.js` — [three.js](https://threejs.org)
  v0.185.1, MIT licensed.
  Vendored locally (not loaded from a CDN) so the deployed app has no runtime
  dependency on a third-party host. Used by `../liquid-bg.js` for the WebGL
  ripple background; the ripple shader itself is original code written for
  this project, not part of three.js.
