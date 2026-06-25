# Web Build Notes

This explains what `TOOLS/build_web_mobile.py` does and why. The game ships
**mobile-only** -- there is no desktop/landscape web build. Read this before
you touch the script or the `index_mobile.html` template.

## TL;DR -- to produce a new upload-ready zip

    Windows (Command Prompt):   .venv\Scripts\activate
    Windows (PowerShell):       .venv\Scripts\Activate.ps1
    Mac / Linux:                source .venv/bin/activate

    python TOOLS/build_web_mobile.py --build-only
    # -> WEB_BUILD/game_web_mobile.zip (portrait, ready to upload)

Upload the zip to your host and extract in place. The `index.html` inside
expects the `.apk` and `.tar.gz` as siblings.

---

## What the build does

1. Stages a clean copy of the project at `~/game_web_mobile_<timestamp>/` (a
   path with no spaces or parentheses -- pygbag 0.9.3 breaks on a path like a
   Google Drive folder named `My Drive (you@example.com)`).
2. Copies `main.py`, `pygbag.ini`, `src/`, `config/`, `assets/` into the
   staging dir.
3. Runs `pygbag --build <staging>`, which produces `.apk` + `.tar.gz` +
   `index.html` + `favicon.png` in `build/web/`.
4. Replaces pygbag's generated `index.html` with our hand-crafted template
   (`WEB_BUILD/index_mobile.html`) -- see "Why we replace index.html" below.
5. Zips everything in `build/web/` to `WEB_BUILD/game_web_mobile.zip`. pygbag
   actually **loads the `.tar.gz`** at runtime (tested: dropping it causes a
   404 in the browser console) -- the `.apk` is a secondary PWA/Android
   artifact. Keep both in the zip.

---

## Why we replace index.html

pygbag's raw, unpatched `index.html` is functional but has a few rough
edges out of the box:

- The page background is **not black** -- you'll see a flash of the
  browser's default background color (often gray, or whatever `<body>`
  inherits) before/around the canvas while it loads and during letterbox
  bars on a mismatched aspect ratio.
- It hardcodes a 1280x720 framebuffer and doesn't re-assert the canvas
  size on resize/orientation change, so the canvas can end up squeezed.
- It has no cache-busting, so browsers can serve a stale build after you
  redeploy.

`WEB_BUILD/index_mobile.html` is a pre-patched copy that fixes all of this:
solid black background everywhere (so no flash of color), a correct
portrait framebuffer size/aspect, a MutationObserver-based canvas-size
enforcer that keeps the canvas correct across resizes, and a
`BUILD_VERSION` cache-buster. The build script installs this over pygbag's
default automatically -- **you should never need to hand-edit the raw
generated `index.html`.**

If you ever want to see pygbag's raw, un-patched output for comparison,
run `pygbag --build <staging>` yourself and look at `build/web/index.html`
before the script overwrites it -- it is not checked into this template.

### The patches, if you need to change canvas dimensions

The template encodes the same six fixes pygbag 0.9.3 needs to render
at a resolution other than its hardcoded 1280x720 default. If you change
your game's resolution, update all of these together in the template:

| # | what | why |
|---|---|---|
| 1 | `fb_width` / `fb_height` in the `config` object | framebuffer size |
| 2 | `width="...px"` / `height="...px"` on `<canvas3d>` | matches framebuffer |
| 3 | `fb_ar` (width / height) | aspect ratio used for letterboxing |
| 4 | `gui_divider : 1` | prevents a half-size canvas |
| 5 | `force_canvas_size()` + listeners on `DOMContentLoaded` / `load` / `resize` / `orientationchange` | keeps the canvas correct across window resizes |
| 6 | service-worker unregister + `BUILD_VERSION` cache-busting block | forces the browser to pull the latest build on every deploy |

The mobile template ships at 414x896 phone-portrait (matching
`config/game_config.json`). Change `MOBILE_W`/`MOBILE_H` in
`TOOLS/build_web_mobile.py` and the matching `fb_width`/`fb_height`/`fb_ar`
in `index_mobile.html` together if your game needs different proportions.

---

## Deployment

1. Copy `WEB_BUILD/game_web_mobile.zip` to your web host.
2. Extract in place. You should see:
   ```
   index.html
   game_web_mobile_<stamp>.apk
   game_web_mobile_<stamp>.tar.gz
   favicon.png
   ```
3. Visit `https://<host>/path/to/index.html`.

(For the live PREDICTOR deploy, `TOOLS/package_deploy.py` mirrors these
mobile artifacts into `WEB_BUILD/PREDICTOR/` alongside the PHP relay and
wraps the lot as `PREDICTOR_deploy.zip` -- see the deploy notes.)

---

## Known caveats / gotchas

- pygbag rejects MP3 audio (`RuntimeError: Audio file has a common
  unsupported format`). Use OGG for any sound you want to play in the web
  build.
- Staging directory cleanup sometimes hits `PermissionError` on Windows
  because Google Drive sync holds the folder open right after a copy.
  The build script sidesteps this by using a fresh timestamp-suffixed
  staging path every run (e.g. `~/game_web_mobile_20260615_163851/`) --
  old staging dirs are harmless, they just sit under `~/` until you clean
  them up by hand.
- Want a custom browser-tab icon? Drop a `favicon.png` into `WEB_BUILD/`
  -- the build script installs it automatically if present. Remember to
  add `!WEB_BUILD/favicon.png` to `.gitignore` if you want to track it,
  since `WEB_BUILD/*` is ignored by default.
