"""Verify docs/PLAN.md traceability: every FR / FR-UI row exists once and every referenced test exists.

Usage:  python scripts/check_traceability.py
Exit code 1 if any requirement row or referenced test is missing.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def collected_tests() -> set[tuple[str, str]]:
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
                         capture_output=True, text=True, cwd=ROOT).stdout
    found = set()
    for line in out.splitlines():
        if "::" in line:
            path, name = line.split("::", 1)
            found.add((path.replace("\\", "/").removeprefix("tests/"), name.split("[")[0]))
    return found


def main() -> int:
    plan = (ROOT / "docs" / "PLAN.md").read_text(encoding="utf-8")
    rows = [line for line in plan.splitlines() if re.match(r"^\| FR-", line)]
    ids = [line.split("|")[1].strip() for line in rows]
    expected = [f"FR-{i:03d}" for i in range(1, 123)] + [f"FR-UI-{i:03d}" for i in range(1, 129)]
    problems = [f"missing row {x}" for x in expected if x not in ids]
    problems += [f"duplicate row {x}" for x in set(ids) if ids.count(x) > 1]
    tests = collected_tests()
    for line in rows:
        cells = [c.strip() for c in line.split("|")]
        fid, refs, status = cells[1], cells[6], cells[8]
        current = None
        for piece in re.split(r"[;,]\s*", refs):
            match = re.match(r"(?:(\S+\.py))?::(\w+)", piece.strip())
            if not match:
                problems.append(f"{fid}: unparseable test reference {piece!r}")
                continue
            current = match.group(1) or current
            if (current, match.group(2)) not in tests:
                problems.append(f"{fid}: test not found {current}::{match.group(2)}")
        if status != "Implemented + Tested":
            problems.append(f"{fid}: status is {status!r}")
    print(f"{len(rows)} requirement rows, {len(tests)} collected tests, {len(problems)} problem(s)")
    for problem in problems:
        print(" -", problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
