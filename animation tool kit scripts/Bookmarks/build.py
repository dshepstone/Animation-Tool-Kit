"""build.py — package Maya Time Bookmarks for distribution.

Creates dist/maya_time_bookmarks_v<version>.zip containing everything a
user needs to install the tool:

    maya_time_bookmarks_v0.1.0/
    ├── install.mel          ← drag onto Maya viewport to install
    ├── README.md
    └── src/
        └── time_bookmarks/  ← the Python package

Usage::

    python build.py

The version is read from pyproject.toml so there is a single source of truth.
"""

from __future__ import annotations

import re
import shutil
import sys
import zipfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.resolve()
SRC_PKG = ROOT / "src" / "time_bookmarks"
DIST_DIR = ROOT / "dist"
PYPROJECT = ROOT / "pyproject.toml"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EXCLUDE_PATTERNS = {
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".DS_Store",
    "*.egg-info",
}


def _should_exclude(path: Path) -> bool:
    for pattern in EXCLUDE_PATTERNS:
        if "*" in pattern:
            if path.match(pattern):
                return True
        elif path.name == pattern:
            return True
    return False


def _read_version() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise RuntimeError("Could not find version in pyproject.toml")
    return m.group(1)


def _add_tree(zf: zipfile.ZipFile, src: Path, arcbase: str) -> int:
    """Add an entire directory tree to *zf* under *arcbase*, returning file count."""
    count = 0
    for item in sorted(src.rglob("*")):
        if _should_exclude(item):
            continue
        if item.is_file():
            arc = arcbase + "/" + item.relative_to(src).as_posix()
            zf.write(item, arc)
            count += 1
    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build() -> None:
    version = _read_version()
    top = f"maya_time_bookmarks_v{version}"
    zip_name = f"{top}.zip"
    zip_path = DIST_DIR / zip_name

    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # Remove stale artifact.
    if zip_path.exists():
        zip_path.unlink()
        print(f"Removed old {zip_name}")

    print(f"Building {zip_name} …")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Drag-and-drop installers.
        zf.write(ROOT / "install.mel", f"{top}/install.mel")
        print("  + install.mel")
        zf.write(ROOT / "install.py", f"{top}/install.py")
        print("  + install.py")

        # Shelf button icon.
        zf.write(ROOT / "icons" / "Bookmark.png", f"{top}/icons/Bookmark.png")
        print("  + icons/Bookmark.png")

        # User-facing documentation.
        zf.write(ROOT / "README.md", f"{top}/README.md")
        print("  + README.md")

        # Python package (src/time_bookmarks/).
        n = _add_tree(zf, SRC_PKG, f"{top}/src/time_bookmarks")
        print(f"  + src/time_bookmarks/ ({n} files)")

    size_kb = zip_path.stat().st_size // 1024
    print(f"\nDone — {zip_path.relative_to(ROOT)}  ({size_kb} KB)")


if __name__ == "__main__":
    try:
        build()
    except Exception as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        sys.exit(1)
