"""Run pinned Python quality tools one file at a time with bounded execution."""

from __future__ import annotations

import argparse
import importlib.metadata
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TOOL_VERSIONS = {"isort": "5.13.2", "black": "24.4.2"}
TOOL_ORDER = ("isort", "black")
SHA_PATTERN = re.compile(r"[0-9a-fA-F]{40}")
MAX_SELECTED_FILES = 4096
MAX_GIT_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_TIMEOUT_SECONDS = 120
GIT_TIMEOUT_SECONDS = 20


class QualitySelectionError(ValueError):
    """The requested quality scope was ambiguous or unsafe."""


@dataclass(frozen=True)
class QualityFailure:
    kind: str
    tool: str
    path: str = ""


def _valid_sha(value: str) -> bool:
    return bool(SHA_PATTERN.fullmatch(value)) and value != "0" * 40


def _normalize_explicit_path(root: Path, raw_path: str) -> str:
    if (
        not isinstance(raw_path, str)
        or not raw_path
        or not raw_path.isprintable()
        or any(character in raw_path for character in ("\0", "\n", "\r"))
    ):
        raise QualitySelectionError("selected path is unsafe")
    value = raw_path.replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    if not value or value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise QualitySelectionError("selected path is unsafe")
    parts = PurePosixPath(value).parts
    if any(part in ("", ".", "..") for part in parts):
        raise QualitySelectionError("selected path is unsafe")
    normalized = "/".join(parts)
    if normalized != value:
        raise QualitySelectionError("selected path is unsafe")
    if not normalized.endswith(".py"):
        raise QualitySelectionError("selected path is not a Python file")
    root_resolved = root.resolve()
    candidate = (root_resolved / normalized).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        raise QualitySelectionError("selected path escapes the repository") from None
    if not candidate.is_file():
        raise QualitySelectionError("selected Python file is missing")
    return normalized


def select_explicit_paths(root: Path, paths: Iterable[str]) -> tuple[str, ...]:
    selected = sorted({_normalize_explicit_path(root, path) for path in paths})
    if not selected:
        raise QualitySelectionError("no Python files were selected")
    if len(selected) > MAX_SELECTED_FILES:
        raise QualitySelectionError("too many Python files were selected")
    return tuple(selected)


def _git_paths(
    root: Path,
    command: list[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> tuple[str, ...]:
    try:
        completed = runner(
            command,
            cwd=root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=GIT_TIMEOUT_SECONDS,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise QualitySelectionError("Git path selection failed") from None
    if completed.returncode != 0 or not isinstance(completed.stdout, bytes):
        raise QualitySelectionError("Git path selection failed")
    if len(completed.stdout) > MAX_GIT_OUTPUT_BYTES:
        raise QualitySelectionError("Git path selection was oversized")
    raw_paths = [os.fsdecode(item) for item in completed.stdout.split(b"\0") if item]
    python_paths = [path for path in raw_paths if path.endswith(".py")]
    if len(python_paths) > MAX_SELECTED_FILES:
        raise QualitySelectionError("too many Python files were selected")
    if not python_paths:
        return ()
    return select_explicit_paths(root, python_paths)


def select_changed_python_paths(
    root: Path,
    base: str,
    head: str,
    *,
    merge_base: bool = False,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> tuple[str, ...]:
    if not _valid_sha(base) or not _valid_sha(head):
        raise QualitySelectionError("Git range must use exact nonzero commit SHAs")
    command = [
        "git",
        "diff",
        "--name-only",
        "-z",
        "--diff-filter=ACMRTUXB",
        "--no-renames",
    ]
    if merge_base:
        command.append("--merge-base")
    return _git_paths(root, [*command, base, head], runner=runner)


def select_tracked_python_paths(
    root: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> tuple[str, ...]:
    return _git_paths(
        root,
        ["git", "ls-files", "-z", "--", "*.py"],
        runner=runner,
    )


def _tool_command(
    tool: str, mode: str, path: str, config: Path, executable: str
) -> list[str]:
    command = [executable, "-I", "-m", tool]
    if tool == "isort":
        command.extend(["--settings-path", str(config), "--quiet"])
        if mode == "check":
            command.append("--check-only")
    else:
        command.extend(["--config", str(config), "--quiet"])
        if mode == "check":
            command.append("--check")
    command.extend(["--", path])
    return command


def run_quality(
    root: Path,
    paths: Sequence[str],
    *,
    mode: str,
    timeout_seconds: int = 20,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    version_lookup: Callable[[str], str] = importlib.metadata.version,
    executable: str = sys.executable,
) -> tuple[QualityFailure, ...]:
    if mode not in ("check", "format"):
        raise ValueError("quality mode is invalid")
    if not 1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS:
        raise ValueError("quality timeout is out of bounds")
    selected = select_explicit_paths(root, paths)
    config = root / "pyproject.toml"
    if not config.is_file():
        raise QualitySelectionError("quality configuration is missing")

    failures = []
    for tool in TOOL_ORDER:
        expected = EXPECTED_TOOL_VERSIONS[tool]
        try:
            observed = version_lookup(tool)
        except importlib.metadata.PackageNotFoundError:
            failures.append(QualityFailure("missing tool", tool))
            continue
        if observed != expected:
            failures.append(QualityFailure("wrong tool version", tool))
    if failures:
        return tuple(failures)

    for path in selected:
        for tool in TOOL_ORDER:
            command = _tool_command(tool, mode, path, config, executable)
            try:
                completed = runner(
                    command,
                    cwd=root,
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout_seconds,
                    shell=False,
                )
            except subprocess.TimeoutExpired:
                failures.append(QualityFailure("timeout", tool, path))
                continue
            except OSError:
                failures.append(QualityFailure("subprocess failure", tool, path))
                continue
            if completed.returncode:
                kind = (
                    "formatting required"
                    if mode == "check" and completed.returncode == 1
                    else "subprocess failure"
                )
                failures.append(QualityFailure(kind, tool, path))
    return tuple(failures)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("check", "format"))
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--paths", nargs="+")
    source.add_argument("--git-diff", nargs=2, metavar=("BASE", "HEAD"))
    source.add_argument("--all", action="store_true")
    parser.add_argument("--merge-base", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=20)
    args = parser.parse_args(argv)
    if args.merge_base and not args.git_diff:
        parser.error("--merge-base requires --git-diff")
    try:
        if args.paths:
            paths = select_explicit_paths(ROOT, args.paths)
        elif args.git_diff:
            paths = select_changed_python_paths(
                ROOT, *args.git_diff, merge_base=args.merge_base
            )
        else:
            paths = select_tracked_python_paths(ROOT)
        if not paths:
            print("no changed Python files selected")
            return 0
        failures = run_quality(
            ROOT, paths, mode=args.mode, timeout_seconds=args.timeout_seconds
        )
    except (QualitySelectionError, ValueError) as error:
        print(f"quality selection failed: {error}", file=sys.stderr)
        return 2
    if failures:
        for failure in failures:
            location = f": {failure.path}" if failure.path else ""
            print(
                f"quality failed: {failure.kind}: {failure.tool}{location}",
                file=sys.stderr,
            )
        return 1
    print(f"quality {args.mode} passed for {len(paths)} Python file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
