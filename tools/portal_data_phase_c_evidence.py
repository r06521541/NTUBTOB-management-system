from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = (
    ROOT / "docs" / "operations" / "sql" / "TASK-070-phase-c-precheck.sql",
    ROOT / "docs" / "operations" / "sql" / "TASK-070-phase-c-postcheck.sql",
)


class PhaseCEvidenceError(RuntimeError):
    pass


def checksum_for(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def verify_sql(sql: str) -> None:
    upper = sql.upper()
    errors = []
    if upper.count("BEGIN TRANSACTION READ ONLY;") != 1:
        errors.append("read-only transaction missing")
    if not upper.rstrip().endswith("ROLLBACK;"):
        errors.append("artifact must end with rollback")
    if "STATEMENT_TIMEOUT" not in upper:
        errors.append("statement timeout missing")
    for forbidden in (
        r"\b(?:INSERT|UPDATE|DELETE|ALTER|DROP|CREATE|GRANT|REVOKE|CALL|COPY)\b",
        r"postgres(?:ql)?://",
        r"supabase",
        r"password",
    ):
        if re.search(forbidden, sql, re.IGNORECASE):
            errors.append(f"forbidden content: {forbidden}")
    if errors:
        raise PhaseCEvidenceError("; ".join(errors))


def write_checksums() -> None:
    for path in ARTIFACTS:
        sql = path.read_text(encoding="utf-8")
        verify_sql(sql)
        path.with_suffix(".sql.sha256").write_text(
            f"{checksum_for(sql)}  {path.name}\n", encoding="ascii"
        )


def verify_artifacts() -> None:
    for path in ARTIFACTS:
        sql = path.read_text(encoding="utf-8")
        verify_sql(sql)
        sidecar = path.with_suffix(".sql.sha256").read_text(encoding="ascii").strip()
        checksum, separator, filename = sidecar.partition("  ")
        if not separator or filename != path.name or checksum != checksum_for(sql):
            raise PhaseCEvidenceError(f"checksum mismatch: {path.name}")


if __name__ == "__main__":
    write_checksums()
    verify_artifacts()
    print("Phase C evidence artifacts verified")
