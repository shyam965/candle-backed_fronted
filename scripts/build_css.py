"""Build app/static/css/app.css with the Tailwind standalone CLI.

Usage:  python scripts/build_css.py           # minified production build
        python scripts/build_css.py --watch   # rebuild on template changes
"""

from __future__ import annotations

import subprocess
import sys

from fetch_assets import ROOT, main as fetch, tailwind_path


def build(watch: bool) -> int:
    cli = tailwind_path()
    if not cli.exists():
        fetch()
    cmd = [str(cli), "-i", str(ROOT / "tailwind" / "input.css"), "-o", str(ROOT / "app" / "static" / "css" / "app.css")]
    cmd.append("--watch" if watch else "--minify")
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(build("--watch" in sys.argv))
