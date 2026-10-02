"""Download pinned build/runtime assets: the Tailwind standalone CLI (into bin/) and HTMX (into app/static/js/).

Usage:  python scripts/fetch_assets.py
"""

from __future__ import annotations

import platform
import stat
import sys
import urllib.request
from pathlib import Path

TAILWIND_VERSION = "v4.3.3"
HTMX_VERSION = "2.0.11"

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "bin"
JS = ROOT / "app" / "static" / "js"


def tailwind_asset() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "x64"
    if system == "windows":
        return f"tailwindcss-windows-{arch}.exe"
    if system == "darwin":
        return f"tailwindcss-macos-{arch}"
    return f"tailwindcss-linux-{arch}"


def tailwind_path() -> Path:
    return BIN / ("tailwindcss.exe" if platform.system() == "Windows" else "tailwindcss")


def download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 - fixed https URLs
        target.write_bytes(response.read())


def main() -> int:
    cli = tailwind_path()
    if not cli.exists():
        download(
            f"https://github.com/tailwindlabs/tailwindcss/releases/download/{TAILWIND_VERSION}/{tailwind_asset()}",
            cli,
        )
        cli.chmod(cli.stat().st_mode | stat.S_IEXEC)
    htmx = JS / "htmx.min.js"
    if not htmx.exists():
        download(f"https://cdn.jsdelivr.net/npm/htmx.org@{HTMX_VERSION}/dist/htmx.min.js", htmx)
    print("Assets ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
