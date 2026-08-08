from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "docs" / "operations" / "sql" / "portal-data-0003-to-0004.sql"
CHECKSUM = ARTIFACT.with_suffix(".sql.sha256")
LOCAL_URL = (
    "postgresql+psycopg2://portal_local:local-only-password@"
    "127.0.0.1:55432/ntubtob_portal_local"
)
HEADER = """-- GENERATED FILE: do not edit by hand.
-- Source: Alembic 0003_legacy_bigint_activity_game -> 0004_phase_c_identity_lifecycle.
-- LOCAL REHEARSAL/REVIEW ONLY. PRODUCTION EXECUTION REQUIRES SEPARATE OWNER APPROVAL.

"""


class PhaseCMigrationError(RuntimeError):
    pass


def render_sql() -> str:
    output = io.StringIO()
    config = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    config.set_main_option("sqlalchemy.url", LOCAL_URL)
    previous = os.environ.get("PORTAL_DATA_DATABASE_URL")
    os.environ["PORTAL_DATA_DATABASE_URL"] = LOCAL_URL
    try:
        command.upgrade(
            config,
            "0003_legacy_bigint_activity_game:0004_phase_c_identity_lifecycle",
            sql=True,
        )
    finally:
        if previous is None:
            os.environ.pop("PORTAL_DATA_DATABASE_URL", None)
        else:
            os.environ["PORTAL_DATA_DATABASE_URL"] = previous
    rendered = "\n".join(
        line.rstrip() for line in output.getvalue().replace("\r\n", "\n").splitlines()
    ).strip()
    rendered = rendered.replace(
        "BEGIN;",
        "BEGIN;\n\nSET LOCAL lock_timeout = '5s';\n"
        "SET LOCAL statement_timeout = '60s';",
        1,
    )
    return HEADER + rendered + "\n"


def checksum_for(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def verify_sql(sql: str, checksum: str | None = None) -> None:
    errors = []
    upper = sql.upper()
    if not sql.startswith(HEADER):
        errors.append("approval boundary header missing")
    if "\r" in sql or sql.startswith("\ufeff"):
        errors.append("artifact must be BOM-free UTF-8 with LF line endings")
    if upper.count("BEGIN;") != 1 or upper.count("COMMIT;") != 1:
        errors.append("one atomic transaction is required")
    if not upper.rstrip().endswith("COMMIT;"):
        errors.append("migration must end with COMMIT")
    if "SET LOCAL LOCK_TIMEOUT = '5S';" not in upper:
        errors.append("lock timeout missing")
    if "SET LOCAL STATEMENT_TIMEOUT = '60S';" not in upper:
        errors.append("statement timeout missing")
    required = (
        "ADD COLUMN FORMAL_NAME",
        "ADD COLUMN ADMIN_NOTE",
        "CREATE TABLE NTUBTOB.IDENTITY_REVIEW_THREADS",
        "CREATE TABLE NTUBTOB.IDENTITY_REVIEW_MESSAGES",
        "ADD COLUMN PERSON_ID BIGINT NULL",
        "PHASE C ATTENDANCE BACKFILL HAS UNRESOLVED PERSON ROWS",
        "ENABLE ROW LEVEL SECURITY",
        "0004_PHASE_C_IDENTITY_LIFECYCLE",
    )
    for marker in required:
        if marker not in upper:
            errors.append(f"required migration marker missing: {marker}")
    for forbidden in (
        r"\b(?:GRANT|REVOKE|CREATE\s+POLICY|FORCE\s+ROW\s+LEVEL\s+SECURITY)\b",
        r"postgres(?:ql)?://",
        r"supabase",
        r"password\s*=",
        r"\{\{[^}]+\}\}|<[^>]*(?:PLACEHOLDER|REPLACE|VALUE)[^>]*>",
    ):
        if re.search(forbidden, sql, flags=re.IGNORECASE):
            errors.append(f"forbidden migration content: {forbidden}")
    if checksum is not None and checksum_for(sql) != checksum:
        errors.append("checksum mismatch")
    if sql != render_sql():
        errors.append("artifact differs from deterministic migration output")
    if errors:
        raise PhaseCMigrationError("; ".join(errors))


def write_artifact() -> None:
    sql = render_sql()
    verify_sql(sql)
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(sql, encoding="utf-8", newline="\n")
    CHECKSUM.write_text(f"{checksum_for(sql)}  {ARTIFACT.name}\n", encoding="ascii")


def verify_artifact() -> None:
    raw = ARTIFACT.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise PhaseCMigrationError("artifact encoding or line ending is not canonical")
    try:
        sql = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PhaseCMigrationError("artifact is not UTF-8") from exc
    checksum, separator, filename = (
        CHECKSUM.read_text(encoding="ascii").strip().partition("  ")
    )
    if not separator or filename != ARTIFACT.name:
        raise PhaseCMigrationError("invalid checksum sidecar")
    config = Config(str(ROOT / "alembic.ini"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if heads != ["0004_phase_c_identity_lifecycle"]:
        raise PhaseCMigrationError(f"unexpected Alembic heads: {heads}")
    verify_sql(sql, checksum)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("render", "verify"))
    args = parser.parse_args()
    if args.action == "render":
        write_artifact()
        print(f"rendered {ARTIFACT.relative_to(ROOT)}")
    else:
        verify_artifact()
        print("Phase C migration artifact verified")


if __name__ == "__main__":
    main()
