"""Prepare an immutable, private build context for the staging broker."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import uuid
from pathlib import Path, PurePosixPath

from apps.mobile_staging_broker.artifacts import APPROVAL_PATH, artifact_hashes
from apps.mobile_staging_broker.broker import BrokerFailure
from tools.mobile_staging_contract import StagingContractError, load_approval

EXPECTED_PROJECT = "ntubtob-mobile-staging"
EXPECTED_REGION = "asia-east1"
EXPECTED_SERVICE = "mobile-api-staging"
EXPECTED_DATABASE_IDENTITY_SHA256 = (
    "5458aab22f538d601725365e26a01d6d585f0e7d07dc32451cd6309d61a40d7c"
)
PACKAGER_CONTRACT = "task135-v1"
MAX_APPROVAL_BYTES = 32768
TOOL_ROOT = Path(__file__).resolve().parents[1]
APPROVED_OUTPUT_ROOT = Path("E:/codex-evidence/task-135")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
ARCHIVE_PATHS = (
    "alembic.ini",
    "apps/mobile_staging_broker",
    "migrations/env.py",
    "migrations/script.py.mako",
    "migrations/versions",
    "shared_lib/shared_module",
    "tools/__init__.py",
    "tools/mobile_staging_contract.py",
    "tools/mobile_staging_data.py",
    "tools/mobile_staging_seed.py",
    "tools/setup_portal_data_legacy.py",
)


class BrokerRolloutError(RuntimeError):
    """Bounded, non-sensitive rollout packaging failure."""


def _run_git(source: Path, arguments: list[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", "-c", f"safe.directory={source.as_posix()}", "-C", str(source)]
            + arguments,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        raise BrokerRolloutError("SOURCE_UNAVAILABLE") from None
    if completed.returncode != 0:
        raise BrokerRolloutError("SOURCE_UNAVAILABLE")
    return completed.stdout


def _is_reparse(path: Path) -> bool:
    try:
        stat = path.lstat()
    except OSError:
        raise BrokerRolloutError("PATH_INVALID") from None
    return path.is_symlink() or bool(getattr(stat, "st_file_attributes", 0) & 0x400)


def _assert_path_chain_no_reparse(path: Path) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists() or current.is_symlink():
            if _is_reparse(current):
                raise BrokerRolloutError("PATH_INVALID")
        else:
            break


def _same_file_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_size == right.st_size
    )


def _read_approval_bytes(approval_path: Path) -> bytes:
    try:
        with approval_path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            named_before = os.stat(approval_path, follow_symlinks=False)
            if (
                opened.st_nlink != 1
                or not stat.S_ISREG(opened.st_mode)
                or getattr(opened, "st_file_attributes", 0) & 0x400
                or not _same_file_identity(opened, named_before)
            ):
                raise BrokerRolloutError("APPROVAL_INVALID")
            value = handle.read(MAX_APPROVAL_BYTES + 1)
            named_after = os.stat(approval_path, follow_symlinks=False)
            if not _same_file_identity(opened, named_after):
                raise BrokerRolloutError("APPROVAL_INVALID")
    except OSError:
        raise BrokerRolloutError("APPROVAL_INVALID") from None
    if not value or len(value) > MAX_APPROVAL_BYTES or b"\x00" in value:
        raise BrokerRolloutError("APPROVAL_INVALID")
    try:
        value.decode("utf-8")
    except UnicodeDecodeError:
        raise BrokerRolloutError("APPROVAL_INVALID") from None
    return value.replace(b"\r\n", b"\n")


def _validate_inputs(
    source: Path, approval_path: Path, output: Path, commit: str
) -> bytes:
    if not SHA_PATTERN.fullmatch(commit or ""):
        raise BrokerRolloutError("COMMIT_INVALID")
    _assert_path_chain_no_reparse(source)
    _assert_path_chain_no_reparse(approval_path)
    _assert_path_chain_no_reparse(output.parent)
    if not source.is_dir() or _is_reparse(source):
        raise BrokerRolloutError("SOURCE_INVALID")
    if not approval_path.is_file() or _is_reparse(approval_path):
        raise BrokerRolloutError("APPROVAL_INVALID")
    if output.exists() or not output.parent.is_dir() or _is_reparse(output.parent):
        raise BrokerRolloutError("OUTPUT_INVALID")
    if _run_git(source, ["rev-parse", "HEAD"]).strip() != commit:
        raise BrokerRolloutError("COMMIT_DRIFT")
    if _run_git(source, ["status", "--porcelain=v1", "--untracked-files=all"]):
        raise BrokerRolloutError("SOURCE_DIRTY")
    if _run_git(source, ["cat-file", "-t", commit]).strip() != "commit":
        raise BrokerRolloutError("COMMIT_INVALID")
    return _read_approval_bytes(approval_path)


def _extract_archive(archive_path: Path, context: Path) -> None:
    try:
        with tarfile.open(archive_path, "r") as archive:
            for member in archive.getmembers():
                relative = PurePosixPath(member.name)
                if (
                    relative.is_absolute()
                    or ".." in relative.parts
                    or member.issym()
                    or member.islnk()
                    or not (member.isdir() or member.isfile())
                ):
                    raise BrokerRolloutError("ARCHIVE_INVALID")
                destination = context.joinpath(*relative.parts)
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                source_file = archive.extractfile(member)
                if source_file is None:
                    raise BrokerRolloutError("ARCHIVE_INVALID")
                with source_file, destination.open("xb") as target:
                    shutil.copyfileobj(source_file, target)
    except (OSError, tarfile.TarError):
        raise BrokerRolloutError("ARCHIVE_INVALID") from None


def prepare_broker_rollout(
    *, source: Path, approval_path: Path, output: Path, commit: str
) -> dict[str, str]:
    try:
        _assert_path_chain_no_reparse(source)
        _assert_path_chain_no_reparse(approval_path)
        _assert_path_chain_no_reparse(output.parent)
        source = source.resolve(strict=True)
        approval_path = approval_path.resolve(strict=True)
        output_parent = output.parent.resolve(strict=True)
    except OSError:
        raise BrokerRolloutError("PATH_INVALID") from None
    output = output_parent / output.name
    approval_bytes = _validate_inputs(source, approval_path, output, commit)
    partial = output.with_name(f".{output.name}.partial-{uuid.uuid4().hex}")
    archive_path = partial / "source.tar"
    context = partial / "context"
    try:
        partial.mkdir(mode=0o700)
        context.mkdir()
        try:
            completed = subprocess.run(
                [
                    "git",
                    "-c",
                    f"safe.directory={source.as_posix()}",
                    "-C",
                    str(source),
                    "archive",
                    "--format=tar",
                    f"--output={archive_path}",
                    commit,
                    "--",
                    *ARCHIVE_PATHS,
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            raise BrokerRolloutError("ARCHIVE_UNAVAILABLE") from None
        if completed.returncode != 0 or not archive_path.is_file():
            raise BrokerRolloutError("ARCHIVE_UNAVAILABLE")
        _extract_archive(archive_path, context)
        archive_path.unlink()
        context_approval = context / APPROVAL_PATH
        if not context_approval.is_file() or _is_reparse(context_approval):
            raise BrokerRolloutError("CONTEXT_INVALID")
        context_approval.unlink()
        context_approval.write_bytes(approval_bytes)
        try:
            approval = load_approval(context_approval)
        except StagingContractError:
            raise BrokerRolloutError("APPROVAL_INVALID") from None
        if (
            approval["approval_phase"] != "candidate"
            or approval["project"] != EXPECTED_PROJECT
            or approval["region"] != EXPECTED_REGION
            or approval["service"] != EXPECTED_SERVICE
            or approval["database_identity_sha256"]
            != EXPECTED_DATABASE_IDENTITY_SHA256
        ):
            raise BrokerRolloutError("APPROVAL_DRIFT")
        try:
            hashes = artifact_hashes(context)
        except BrokerFailure:
            raise BrokerRolloutError("HASH_INVALID") from None
        state = {
            "schema_version": 1,
            "packager_contract": PACKAGER_CONTRACT,
            "source_commit": commit,
            "project": approval["project"],
            "region": approval["region"],
            "database_identity_sha256": approval["database_identity_sha256"],
            **hashes,
            "classification": "PASS",
            "result": "prepared",
            "context_lifecycle": "private_until_deploy_cleanup",
            "retention_owner": "main-work",
        }
        (partial / "state.json").write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        partial.replace(output)
        return state
    except BrokerRolloutError:
        raise
    except (OSError, ValueError):
        raise BrokerRolloutError("PACKAGING_FAILED") from None
    finally:
        if partial.exists():
            try:
                shutil.rmtree(partial)
            except OSError:
                raise BrokerRolloutError("PRIVATE_CLEANUP_REQUIRED") from None
            if partial.exists():
                raise BrokerRolloutError("PRIVATE_CLEANUP_REQUIRED")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        _assert_path_chain_no_reparse(APPROVED_OUTPUT_ROOT)
        _assert_path_chain_no_reparse(args.output.parent)
        requested_output = args.output.absolute()
        try:
            requested_output.relative_to(APPROVED_OUTPUT_ROOT)
        except ValueError:
            raise BrokerRolloutError("OUTPUT_INVALID")
        try:
            requested_source = args.source.resolve(strict=True)
        except OSError:
            raise BrokerRolloutError("SOURCE_INVALID") from None
        if requested_source != TOOL_ROOT:
            raise BrokerRolloutError("SOURCE_INVALID")
        state = prepare_broker_rollout(
            source=requested_source,
            approval_path=args.approval,
            output=requested_output,
            commit=args.commit,
        )
        envelope = {"classification": "PASS", "details": state}
        exit_code = 0
    except (BrokerRolloutError, BrokerFailure, OSError) as error:
        if isinstance(error, BrokerRolloutError):
            reason = error.args[0]
        elif isinstance(error, BrokerFailure):
            reason = "HASH_INVALID"
        else:
            reason = "FAILED"
        envelope = {
            "classification": "FAILED",
            "details": {"result": "stopped", "reason_code": reason},
        }
        exit_code = 2
    print(json.dumps(envelope, sort_keys=True, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
