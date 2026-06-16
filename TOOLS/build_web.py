"""Build and serve the web (desktop/landscape) version of the game.

Usage:
    python TOOLS/build_web.py              # build + serve on port 8000
    python TOOLS/build_web.py --port 9000  # custom port
    python TOOLS/build_web.py --build-only # build without serving
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


def main():
    parser = argparse.ArgumentParser(description="Build and serve web version")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    # Stage to a path with no spaces or parentheses under the home dir --
    # pygbag 0.9.3 breaks on paths like a Google Drive folder named
    # "My Drive (you@example.com)".
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    staging = Path.home() / f"game_web_{stamp}"

    print("=" * 50)
    print("  Building web version")
    print("=" * 50)

    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    print("Copying code, config, and assets...")
    shutil.copy2(project_root / "main.py", staging / "main.py")
    if (project_root / "pygbag.ini").exists():
        shutil.copy2(project_root / "pygbag.ini", staging / "pygbag.ini")
    shutil.copytree(project_root / "src", staging / "src",
                     ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(project_root / "config", staging / "config")
    shutil.copytree(project_root / "assets", staging / "assets",
                     ignore=shutil.ignore_patterns("__pycache__"))

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

    # Replace pygbag's default index.html (gray background, no branding)
    # with our hand-crafted black-background desktop template. We only
    # need to substitute the bundle name and a fresh BUILD_VERSION.
    print("Installing desktop index.html from WEB_BUILD/index_desktop.html...")
    template_src = project_root / "WEB_BUILD" / "index_desktop.html"
    index_html = build_web / "index.html"
    if not template_src.exists():
        print(f"  WARNING: {template_src} not found -- index.html left as pygbag's default")
    elif index_html.exists():
        template_html = template_src.read_text(encoding="utf-8")
        # Detect the bundle name baked into the template and replace with
        # the name pygbag chose for this build (same as the staging dir name).
        m = re.search(r'bundle = "([^"]+)"', template_html)
        old_bundle = m.group(1) if m else None
        new_bundle = staging.name
        if old_bundle and old_bundle != new_bundle:
            template_html = template_html.replace(old_bundle, new_bundle)
        # Fresh BUILD_VERSION so browsers drop stale caches on redeploy.
        build_stamp = datetime.datetime.now().strftime("%Y%m%d%H%M")
        template_html = re.sub(
            r'var BUILD_VERSION = "[^"]*"',
            f'var BUILD_VERSION = "{build_stamp}"',
            template_html)
        index_html.write_text(template_html, encoding="utf-8")
        print(f"  Bundle: {new_bundle}  BUILD_VERSION: {build_stamp}")

    # Drop a custom favicon.png into WEB_BUILD/ to override pygbag's default
    # (remember to add "!WEB_BUILD/favicon.png" to .gitignore if you do).
    custom_favicon = project_root / "WEB_BUILD" / "favicon.png"
    if custom_favicon.exists():
        shutil.copy2(custom_favicon, build_web / "favicon.png")
        print(f"  Replaced favicon with {custom_favicon}")

    total_size = sum(f.stat().st_size for f in build_web.rglob("*") if f.is_file())
    print(f"  Total web build: {total_size / 1024 / 1024:.1f} MB")

    # pygbag loads the .tar.gz at runtime (not the .apk) -- dropping it
    # breaks the deployment with a 404, so we include everything.
    zip_dst = project_root / "WEB_BUILD" / "game_web.zip"
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
