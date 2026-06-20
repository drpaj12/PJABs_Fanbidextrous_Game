# TOOLS/package_deploy.py
"""Package the live deploy zip from WEB_BUILD/PREDICTOR.

The zip wraps everything under a top-level PREDICTOR/ folder, so it extracts to a
PREDICTOR directory ready to drop into drpeterjamieson.com/PROJECTS/. It includes ALL of
the PREDICTOR tree -- the web client (index.html, *.apk, *.tar.gz, favicon.png) AND the
server side (PHP_SCRIPTS/: feed_cache.php, soccer_api.php, .htaccess, apifootball_key.txt,
game_rooms/).

The relay base_url baked into the build points at .../PROJECTS/PREDICTOR/PHP_SCRIPTS, so
the extracted folder MUST stay named PREDICTOR or the live feed URLs will not resolve.

Run after a web build + mirror:  .venv/Scripts/python TOOLS/package_deploy.py
"""
import os
import zipfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "WEB_BUILD" / "PREDICTOR"          # the folder to package
_FOLDER = "PREDICTOR"                              # top-level name inside the zip
_OUT = _ROOT / "WEB_BUILD" / "PREDICTOR_deploy.zip"


def main() -> None:
    if not _SRC.is_dir():
        raise SystemExit(f"FAIL: {_SRC} not found -- run the web build + mirror first")

    if _OUT.exists():
        _OUT.unlink()

    written: list[str] = []
    with zipfile.ZipFile(_OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(_SRC):
            for name in files:
                full = Path(root) / name
                # arcname is PREDICTOR/<path-relative-to-_SRC>
                arc = Path(_FOLDER) / full.relative_to(_SRC)
                z.write(full, arc.as_posix())
                written.append(arc.as_posix())

    written.sort()
    print(f"OK: wrote {_OUT}")
    print(f"  files: {len(written)}  size: {round(_OUT.stat().st_size / 1024)} KB")
    print(f"  extracts to: {_FOLDER}/")
    for w in written:
        print(f"    {w}")

    # Sanity: the PHP relay must be in the package.
    php = [w for w in written if w.endswith("feed_cache.php")]
    key = [w for w in written if w.endswith("apifootball_key.txt")]
    print(f"  PHP relay present : {bool(php)}")
    print(f"  API key present   : {bool(key)}")


if __name__ == "__main__":
    main()
