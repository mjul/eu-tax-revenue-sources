"""Format and lint staged Python files with the project's ruff.

Run from PowerShell, cmd, or any other shell:

    uv run python .githooks/pre_commit.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(result.stdout.strip())


def staged_python_files(root: Path) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "diff",
            "--cached",
            "--name-only",
            "--diff-filter=ACMR",
            "-z",
            "--",
            "*.py",
            "*.pyi",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [name for name in result.stdout.decode().split("\0") if name]


def main() -> int:
    root = repo_root()
    files = staged_python_files(root)
    if not files:
        return 0

    check = subprocess.run(
        ["uv", "run", "ruff", "check", "--fix", "--", *files],
        cwd=root,
        check=False,
    )
    formatted = subprocess.run(
        ["uv", "run", "ruff", "format", "--", *files],
        cwd=root,
        check=False,
    )
    subprocess.run(["git", "add", "--", *files], cwd=root, check=True)
    if check.returncode != 0:
        return check.returncode
    return formatted.returncode


if __name__ == "__main__":
    sys.exit(main())
