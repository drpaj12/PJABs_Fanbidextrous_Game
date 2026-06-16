"""Build and serve the portrait-mobile web version.

Sibling to TOOLS/build_web.py, patched for portrait:
  - stages to a separate ~/game_web_mobile_<stamp>/ dir so a desktop
    build running in parallel doesn't collide with it
  - installs WEB_BUILD/index_mobile.html instead of index_desktop.html
  - outputs WEB_BUILD/game_web_mobile.zip

600x900 is just a sensible portrait default -- if your game needs a
different aspect ratio, change MOBILE_W/MOBILE_H below and the matching
fb_width/fb_height/fb_ar values in WEB_BUILD/index_mobile.html together.

Usage:
    python TOOLS/build_web_mobile.py              # build + serve on 8000
    python TOOLS/build_web_mobile.py --port 9000  # custom port
    python TOOLS/build_web_mobile.py --build-only # build without serving
"""

import argparse
import datetime
import http.server
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


MOBILE_W, MOBILE_H = 600, 900
MOBILE_AR = round(MOBILE_W / MOBILE_H, 4)  # 0.6667


def _copy_project_tree(project_root: Path, staging: Path) -> None:
    """Copy code + config + assets into `staging`, identical subset to
    the desktop build. Kept verbatim so a desktop vs mobile diff reads
    cleanly as "same inputs, different patches."""
    shutil.copy2(project_root / "main.py", staging / "main.py")
    if (project_root / "pygbag.ini").exists():
        shutil.copy2(project_root / "pygbag.ini", staging / "pygbag.ini")
    shutil.copytree(project_root / "src", staging / "src",
                     ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(project_root / "config", staging / "config")
    shutil.copytree(project_root / "assets", staging / "assets",
                     ignore=shutil.ignore_patterns("__pycache__"))


def _install_index_html(index_html: Path, template_src: Path, bundle_name: str) -> None:
    """Replace pygbag's generated index.html with our hand-crafted mobile
    template, substituting the bundle name and a fresh BUILD_VERSION."""
    template_html = template_src.read_text(encoding="utf-8")
    m = re.search(r'bundle = "([^"]+)"', template_html)
    old_bundle = m.group(1) if m else None
    if old_bundle and old_bundle != bundle_name:
        template_html = template_html.replace(old_bundle, bundle_name)
    build_stamp = datetime.datetime.now().strftime("%Y%m%d%H%M")
    template_html = re.sub(
        r'var BUILD_VERSION = "[^"]*"',
        f'var BUILD_VERSION = "{build_stamp}"',
        template_html)
    index_html.write_text(template_html, encoding="utf-8")
    print(f"  Bundle: {bundle_name}  BUILD_VERSION: {build_stamp}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and serve the portrait-mobile web version")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    staging = Path.home() / f"game_web_mobile_{stamp}"

    print("=" * 50)
    print("  Building MOBILE (portrait) web version")
    print(f"  Design: {MOBILE_W} x {MOBILE_H}  (ar = {MOBILE_AR})")
    print("=" * 50)

    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    print("Copying code, config, and assets...")
    _copy_project_tree(project_root, staging)

    staging_size = sum(f.stat().st_size for f in staging.rglob("*") if f.is_file())
    print(f"Staging size: {staging_size / 1024 / 1024:.1f} MB")

    print("\nRunning pygbag build...")
    pygbag_exe = Path(sys.executable).parent / "pygbag.exe"
    if not pygbag_exe.exists():
        pygbag_exe = Path(sys.executable).parent / "pygbag"

    result = subprocess.run(
        [str(pygbag_exe), "--build", str(staging)],
        capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"pygbag build error:\n{result.stderr}")

    build_web = staging / "build" / "web"
    if not build_web.exists():
        print("ERROR: build/web directory not created")
        return

    print("Installing mobile index.html from WEB_BUILD/index_mobile.html...")
    index_html = build_web / "index.html"
    template_src = project_root / "WEB_BUILD" / "index_mobile.html"
    if not template_src.exists():
        print(f"  WARNING: {template_src} not found -- index.html left as pygbag's default")
    elif index_html.exists():
        _install_index_html(index_html, template_src, staging.name)

    custom_favicon = project_root / "WEB_BUILD" / "favicon.png"
    if custom_favicon.exists():
        shutil.copy2(custom_favicon, build_web / "favicon.png")
        print(f"  Replaced favicon with {custom_favicon}")

    total_size = sum(f.stat().st_size for f in build_web.rglob("*") if f.is_file())
    print(f"  Total web build: {total_size / 1024 / 1024:.1f} MB")

    zip_dst = project_root / "WEB_BUILD" / "game_web_mobile.zip"
    zip_dst.parent.mkdir(parents=True, exist_ok=True)
    if zip_dst.exists():
        zip_dst.unlink()
    with zipfile.ZipFile(zip_dst, "w", zipfile.ZIP_STORED) as z:
        for f in build_web.iterdir():
            if f.is_file():
                z.write(f, arcname=f.name)
    print(f"  Zip: {zip_dst} ({zip_dst.stat().st_size / 1024 / 1024:.1f} MB)")

    if args.build_only:
        print(f"\nBuild complete: {build_web}")
        return

    print(f"\nServing on http://localhost:{args.port}")
    print("Open this URL in your browser. Press Ctrl+C to stop.\n")
    os.chdir(str(build_web))
    handler = http.server.SimpleHTTPRequestHandler
    server = http.server.HTTPServer(("", args.port), handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
