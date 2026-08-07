from __future__ import annotations

import argparse
import os
import secrets
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from tools.portal_data_logical_backup import (
    DOCKER_IMAGE_ID,
    DockerInspectionRunner,
    _paths,
    verify_evidence,
)

ACKNOWLEDGEMENT = "TASK-057-EPHEMERAL-LOCAL-RESTORE"
CONTAINER_PREFIX = "ntubtob-task057-"
DATABASE_NAME = "task057_rehearsal"
DATABASE_USER = "postgres"
LEGACY_TABLES = (
    "attendance_reply_types",
    "ballparks",
    "cancellations",
    "discord_webhooks",
    "game_attendance_replies",
    "games",
    "line_groups",
    "line_notify_tokens",
    "line_users",
    "members",
)
EXPECTED_FOREIGN_KEYS = (
    ("cancellations", "game_id", "games", "id"),
    ("game_attendance_replies", "game_id", "games", "id"),
    ("game_attendance_replies", "member_id", "members", "id"),
    (
        "game_attendance_replies",
        "reply",
        "attendance_reply_types",
        "id",
    ),
    ("game_attendance_replies", "user_id", "line_users", "id"),
    ("line_users", "member_id", "members", "id"),
)

# table, column, information_schema data_type, UDT, nullable, default category,
# identity, generated. This is the deidentified TASK-049 catalog contract.
VARCHAR = "character varying"
TIMESTAMPTZ = "timestamp with time zone"


def _column(
    table: str,
    column: str,
    data_type: str,
    udt_name: str,
    nullable: str,
    default_kind: str = "none",
    identity: str = "NO",
) -> tuple[str, ...]:
    return (
        table,
        column,
        data_type,
        udt_name,
        nullable,
        default_kind,
        identity,
        "NEVER",
    )


EXPECTED_COLUMNS = (
    _column("attendance_reply_types", "description", VARCHAR, "varchar", "NO"),
    _column(
        "attendance_reply_types", "id", "bigint", "int8", "NO", identity="YES"
    ),
    _column("ballparks", "city_name", VARCHAR, "varchar", "YES"),
    _column("ballparks", "city_weather_code", VARCHAR, "varchar", "YES"),
    _column("ballparks", "district_name", VARCHAR, "varchar", "YES"),
    _column("ballparks", "id", "bigint", "int8", "NO", identity="YES"),
    _column("ballparks", "name", VARCHAR, "varchar", "NO"),
    _column("cancellations", "announced", "boolean", "bool", "YES"),
    _column(
        "cancellations", "cancellation_time", TIMESTAMPTZ, "timestamptz", "NO"
    ),
    _column("cancellations", "game_id", "bigint", "int8", "NO"),
    _column("cancellations", "id", "bigint", "int8", "NO", identity="YES"),
    _column("discord_webhooks", "created_at", TIMESTAMPTZ, "timestamptz", "YES"),
    _column("discord_webhooks", "description", VARCHAR, "varchar", "YES"),
    _column("discord_webhooks", "id", "bigint", "int8", "NO", identity="YES"),
    _column("discord_webhooks", "webhook_identifier", VARCHAR, "varchar", "NO"),
    _column("game_attendance_replies", "game_id", "bigint", "int8", "NO"),
    _column(
        "game_attendance_replies", "id", "bigint", "int8", "NO", identity="YES"
    ),
    _column("game_attendance_replies", "member_id", "bigint", "int8", "YES"),
    _column("game_attendance_replies", "reply", "smallint", "int2", "NO"),
    _column(
        "game_attendance_replies",
        "updated_at",
        TIMESTAMPTZ,
        "timestamptz",
        "NO",
        "now",
    ),
    _column("game_attendance_replies", "user_id", "bigint", "int8", "YES"),
    _column("games", "away_team", VARCHAR, "varchar", "YES"),
    _column(
        "games",
        "cancellation_announcement_time",
        TIMESTAMPTZ,
        "timestamptz",
        "YES",
    ),
    _column("games", "cancellation_time", TIMESTAMPTZ, "timestamptz", "YES"),
    _column("games", "duration", "smallint", "int2", "YES"),
    _column("games", "home_team", VARCHAR, "varchar", "YES"),
    _column("games", "id", "bigint", "int8", "NO", identity="YES"),
    _column("games", "invitation_time", TIMESTAMPTZ, "timestamptz", "YES"),
    _column("games", "location", VARCHAR, "varchar", "YES"),
    _column("games", "season", "smallint", "int2", "YES"),
    _column("games", "start_datetime", TIMESTAMPTZ, "timestamptz", "YES"),
    _column("games", "year", "smallint", "int2", "YES"),
    _column(
        "line_groups", "created_at", TIMESTAMPTZ, "timestamptz", "NO", "now"
    ),
    _column("line_groups", "description", VARCHAR, "varchar", "YES"),
    _column("line_groups", "id", "bigint", "int8", "NO", identity="YES"),
    _column(
        "line_groups",
        "is_broadcast_enabled",
        "boolean",
        "bool",
        "NO",
        "false",
    ),
    _column("line_groups", "line_group_id", VARCHAR, "varchar", "YES"),
    _column("line_notify_tokens", "description", VARCHAR, "varchar", "YES"),
    _column(
        "line_notify_tokens", "id", "bigint", "int8", "NO", identity="YES"
    ),
    _column("line_notify_tokens", "token", VARCHAR, "varchar", "NO"),
    _column("line_users", "has_replied", "boolean", "bool", "NO", "false"),
    _column("line_users", "id", "bigint", "int8", "NO", identity="YES"),
    _column("line_users", "ignored", "boolean", "bool", "NO", "false"),
    _column("line_users", "line_user_id", VARCHAR, "varchar", "NO"),
    _column("line_users", "member_id", "bigint", "int8", "YES"),
    _column("line_users", "nickname", VARCHAR, "varchar", "NO"),
    _column(
        "line_users",
        "submit_time",
        TIMESTAMPTZ,
        "timestamptz",
        "YES",
        "timezone_cct",
    ),
    _column("members", "enroll_year", "smallint", "int2", "YES"),
    _column("members", "id", "bigint", "int8", "NO", identity="YES"),
    _column("members", "major", VARCHAR, "varchar", "YES"),
    _column("members", "name", VARCHAR, "varchar", "NO"),
    _column("members", "number", "smallint", "int2", "YES"),
    _column("members", "positions", VARCHAR, "varchar", "YES"),
)
RESULT_KEYS = (
    "schema",
    "tables",
    "columns",
    "primary_keys",
    "foreign_keys",
    "constraints_validated",
    "primary_indexes",
    "check_constraints",
    "custom_triggers",
    "rls_flags",
    "policy_presence",
    "identity_sequences",
    "row_scan",
)


class RestoreRehearsalError(RuntimeError):
    pass


@dataclass(frozen=True)
class RehearsalResult:
    artifact_verified_before: bool
    restore_completed: bool
    catalog_contract_verified: bool
    artifact_verified_after: bool
    cleanup_completed: bool


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _values(rows: Sequence[Sequence[str]]) -> str:
    return ",\n".join(
        "(" + ", ".join(_sql_literal(value) for value in row) + ")"
        for row in rows
    )


def _catalog_sql() -> str:
    table_values = _values(tuple((table,) for table in LEGACY_TABLES))
    column_values = _values(EXPECTED_COLUMNS)
    foreign_key_values = _values(EXPECTED_FOREIGN_KEYS)
    row_scan = " AND ".join(
        f"(SELECT count(*) FROM ntubtob.{table}) >= 0" for table in LEGACY_TABLES
    )
    return f"""
WITH expected_tables(table_name) AS (VALUES
{table_values}
),
expected_columns(table_name, column_name, data_type, udt_name, is_nullable,
                 default_kind, is_identity, is_generated) AS (VALUES
{column_values}
),
actual_columns AS (
  SELECT table_name, column_name, data_type, udt_name, is_nullable,
         CASE
           WHEN column_default IS NULL THEN 'none'
           WHEN column_default = 'now()' THEN 'now'
           WHEN column_default = 'false' THEN 'false'
           WHEN column_default LIKE '%AT TIME ZONE ''CCT''%' THEN 'timezone_cct'
           ELSE 'unexpected'
         END AS default_kind,
         is_identity, is_generated
  FROM information_schema.columns
  WHERE table_schema = 'ntubtob'
),
expected_foreign_keys(table_name, column_name, target_table, target_column) AS (VALUES
{foreign_key_values}
),
actual_foreign_keys AS (
  SELECT source.relname, source_column.attname, target.relname,
         target_column.attname
  FROM pg_constraint constraint_row
  JOIN pg_class source ON source.oid = constraint_row.conrelid
  JOIN pg_namespace source_schema ON source_schema.oid = source.relnamespace
  JOIN pg_class target ON target.oid = constraint_row.confrelid
  JOIN LATERAL unnest(constraint_row.conkey) WITH ORDINALITY source_key(attnum, position)
    ON true
  JOIN LATERAL unnest(constraint_row.confkey) WITH ORDINALITY target_key(attnum, position)
    ON target_key.position = source_key.position
  JOIN pg_attribute source_column
    ON source_column.attrelid = source.oid AND source_column.attnum = source_key.attnum
  JOIN pg_attribute target_column
    ON target_column.attrelid = target.oid AND target_column.attnum = target_key.attnum
  WHERE source_schema.nspname = 'ntubtob' AND constraint_row.contype = 'f'
),
results(result_key, passed) AS (
  SELECT 'schema', EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'ntubtob')
  UNION ALL
  SELECT 'tables', NOT EXISTS (
    (SELECT table_name FROM expected_tables
     EXCEPT SELECT tablename FROM pg_tables WHERE schemaname = 'ntubtob')
    UNION ALL
    (SELECT tablename FROM pg_tables WHERE schemaname = 'ntubtob'
     EXCEPT SELECT table_name FROM expected_tables)
  )
  UNION ALL
  SELECT 'columns', NOT EXISTS (
    (SELECT * FROM expected_columns EXCEPT SELECT * FROM actual_columns)
    UNION ALL
    (SELECT * FROM actual_columns EXCEPT SELECT * FROM expected_columns)
  )
  UNION ALL
  SELECT 'primary_keys',
    (SELECT count(*) = 10 FROM pg_constraint constraint_row
     JOIN pg_class relation ON relation.oid = constraint_row.conrelid
     JOIN pg_namespace namespace_row ON namespace_row.oid = relation.relnamespace
     WHERE namespace_row.nspname = 'ntubtob' AND constraint_row.contype = 'p'
       AND array_length(constraint_row.conkey, 1) = 1
       AND (SELECT attname FROM pg_attribute
            WHERE attrelid = relation.oid AND attnum = constraint_row.conkey[1]) = 'id')
  UNION ALL
  SELECT 'foreign_keys', NOT EXISTS (
    (SELECT * FROM expected_foreign_keys EXCEPT SELECT * FROM actual_foreign_keys)
    UNION ALL
    (SELECT * FROM actual_foreign_keys EXCEPT SELECT * FROM expected_foreign_keys)
  )
  UNION ALL
  SELECT 'constraints_validated', NOT EXISTS (
    SELECT 1 FROM pg_constraint constraint_row
    JOIN pg_namespace namespace_row ON namespace_row.oid = constraint_row.connamespace
    WHERE namespace_row.nspname = 'ntubtob' AND NOT constraint_row.convalidated
  )
  UNION ALL
  SELECT 'primary_indexes',
    (SELECT count(*) = 10 FROM pg_index index_row
     JOIN pg_class relation ON relation.oid = index_row.indrelid
     JOIN pg_namespace namespace_row ON namespace_row.oid = relation.relnamespace
     WHERE namespace_row.nspname = 'ntubtob'
       AND index_row.indisprimary AND index_row.indisvalid)
  UNION ALL
  SELECT 'check_constraints', NOT EXISTS (
    SELECT 1 FROM pg_constraint constraint_row
    JOIN pg_namespace namespace_row ON namespace_row.oid = constraint_row.connamespace
    WHERE namespace_row.nspname = 'ntubtob' AND constraint_row.contype = 'c'
  )
  UNION ALL
  SELECT 'custom_triggers', NOT EXISTS (
    SELECT 1 FROM pg_trigger trigger_row
    JOIN pg_class relation ON relation.oid = trigger_row.tgrelid
    JOIN pg_namespace namespace_row ON namespace_row.oid = relation.relnamespace
    WHERE namespace_row.nspname = 'ntubtob' AND NOT trigger_row.tgisinternal
  )
  UNION ALL
  SELECT 'rls_flags',
    (SELECT count(*) = 10 AND bool_and(relation.relrowsecurity)
            AND NOT bool_or(relation.relforcerowsecurity)
     FROM pg_class relation
     JOIN pg_namespace namespace_row ON namespace_row.oid = relation.relnamespace
     WHERE namespace_row.nspname = 'ntubtob' AND relation.relkind = 'r')
  UNION ALL
  SELECT 'policy_presence', NOT EXISTS (
    SELECT 1 FROM pg_policy policy_row
    JOIN pg_class relation ON relation.oid = policy_row.polrelid
    JOIN pg_namespace namespace_row ON namespace_row.oid = relation.relnamespace
    WHERE namespace_row.nspname = 'ntubtob'
  )
  UNION ALL
  SELECT 'identity_sequences',
    (SELECT count(*) = 10 FROM information_schema.columns
     WHERE table_schema = 'ntubtob' AND column_name = 'id'
       AND data_type = 'bigint' AND is_identity = 'YES')
  UNION ALL
  SELECT 'row_scan', {row_scan}
)
SELECT result_key || '=' || CASE WHEN passed THEN 't' ELSE 'f' END
FROM results ORDER BY result_key;
""".strip()


CATALOG_SQL = _catalog_sql()


def preflight_artifacts(
    archive: Path, manifest: Path, checksum: Path
) -> tuple[Path, Path, Path]:
    archive, manifest, checksum = _paths(
        archive, manifest, checksum, creating=False
    )
    if archive.parent != manifest.parent or archive.parent != checksum.parent:
        raise RestoreRehearsalError("artifact sidecars must be adjacent")
    if archive.parent == Path.home().absolute():
        raise RestoreRehearsalError("the home directory cannot be mounted")
    if "," in os.fspath(archive.parent):
        raise RestoreRehearsalError("the archive mount path is invalid")
    return archive, manifest, checksum


def _safe_process_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR"}
    }


class DockerRestoreRehearsal:
    def __init__(
        self,
        archive: Path,
        manifest: Path,
        checksum: Path,
        *,
        run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        sleep: Callable[[float], None] = time.sleep,
        name_factory: Callable[[], str] | None = None,
        readiness_attempts: int = 30,
    ):
        self.archive, self.manifest, self.checksum = preflight_artifacts(
            archive, manifest, checksum
        )
        self.run = run
        self.sleep = sleep
        self.name_factory = name_factory or (
            lambda: CONTAINER_PREFIX + secrets.token_hex(6)
        )
        self.readiness_attempts = readiness_attempts
        self.docker = shutil.which("docker")
        if not self.docker:
            raise RestoreRehearsalError("Docker is unavailable")

    def _invoke(
        self, arguments: Sequence[str], *, timeout: int
    ) -> subprocess.CompletedProcess[str]:
        try:
            return self.run(
                [self.docker, *arguments],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=_safe_process_environment(),
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RestoreRehearsalError("Docker operation timed out") from error
        except OSError as error:
            raise RestoreRehearsalError("Docker operation could not start") from error

    def _require_zero(self, arguments: Sequence[str], *, timeout: int) -> str:
        completed = self._invoke(arguments, timeout=timeout)
        if completed.returncode != 0:
            raise RestoreRehearsalError("isolated Docker operation failed")
        return completed.stdout

    def _verify_artifact(self) -> None:
        verify_evidence(
            self.archive,
            self.manifest,
            self.checksum,
            run=DockerInspectionRunner(self.archive),
        )

    def _container_name(self) -> str:
        name = self.name_factory()
        suffix = name.removeprefix(CONTAINER_PREFIX)
        if not name.startswith(CONTAINER_PREFIX) or not suffix or not all(
            character in "0123456789abcdef" for character in suffix
        ):
            raise RestoreRehearsalError("task-owned container name is invalid")
        return name

    def _start(self, name: str) -> None:
        parent = os.fspath(self.archive.parent)
        self._require_zero(
            (
                "run",
                "--detach",
                "--pull",
                "never",
                "--name",
                name,
                "--label",
                "com.ntubtob.task=TASK-057",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--user",
                "postgres",
                "--tmpfs",
                "/var/lib/postgresql/data:rw,noexec,nosuid,size=256m,mode=1777",
                "--tmpfs",
                "/var/run/postgresql:rw,noexec,nosuid,size=16m,mode=1777",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=64m,mode=1777",
                "--mount",
                f"type=bind,source={parent},target=/backup,readonly",
                "--env",
                f"POSTGRES_DB={DATABASE_NAME}",
                "--env",
                f"POSTGRES_USER={DATABASE_USER}",
                "--env",
                "POSTGRES_HOST_AUTH_METHOD=trust",
                "--env",
                "PGDATA=/var/lib/postgresql/data/pgdata",
                DOCKER_IMAGE_ID,
            ),
            timeout=30,
        )

    def _wait_until_ready(self, name: str) -> None:
        for attempt in range(self.readiness_attempts):
            completed = self._invoke(
                (
                    "exec",
                    name,
                    "pg_isready",
                    "--dbname",
                    DATABASE_NAME,
                    "--username",
                    DATABASE_USER,
                ),
                timeout=3,
            )
            if completed.returncode == 0:
                return
            if attempt + 1 < self.readiness_attempts:
                self.sleep(0.25)
        raise RestoreRehearsalError("isolated database did not become ready")

    def _restore(self, name: str) -> None:
        self._require_zero(
            (
                "exec",
                name,
                "pg_restore",
                "--exit-on-error",
                "--single-transaction",
                "--no-owner",
                "--no-privileges",
                "--dbname",
                DATABASE_NAME,
                f"/backup/{self.archive.name}",
            ),
            timeout=60,
        )

    def _verify_catalog(self, name: str) -> None:
        output = self._require_zero(
            (
                "exec",
                name,
                "psql",
                "--no-psqlrc",
                "--set",
                "ON_ERROR_STOP=1",
                "--tuples-only",
                "--no-align",
                "--dbname",
                DATABASE_NAME,
                "--username",
                DATABASE_USER,
                "--command",
                CATALOG_SQL,
            ),
            timeout=30,
        )
        expected = {f"{key}=t" for key in RESULT_KEYS}
        actual = {line.strip() for line in output.splitlines() if line.strip()}
        if actual != expected:
            raise RestoreRehearsalError("restored catalog contract did not match")

    def _cleanup(self, name: str) -> bool:
        try:
            self._invoke(("rm", "--force", name), timeout=15)
            remaining = self._invoke(
                (
                    "ps",
                    "--all",
                    "--filter",
                    f"name=^{name}$",
                    "--format",
                    "{{.Names}}",
                ),
                timeout=5,
            )
        except RestoreRehearsalError:
            return False
        return remaining.returncode == 0 and not remaining.stdout.strip()

    def execute(self, acknowledgement: str) -> RehearsalResult:
        if acknowledgement != ACKNOWLEDGEMENT:
            raise RestoreRehearsalError("explicit execute acknowledgement is required")
        self._verify_artifact()
        name = self._container_name()
        inspected = self._invoke(("container", "inspect", name), timeout=5)
        if inspected.returncode == 0:
            raise RestoreRehearsalError("task-owned container name already exists")

        may_need_cleanup = False
        primary_error: BaseException | None = None
        try:
            may_need_cleanup = True
            self._start(name)
            self._wait_until_ready(name)
            self._restore(name)
            self._verify_catalog(name)
            self._verify_artifact()
        except BaseException as error:
            primary_error = error
        cleanup_ok = True
        if may_need_cleanup:
            cleanup_ok = self._cleanup(name)
        if not cleanup_ok:
            if primary_error is not None:
                raise RestoreRehearsalError(
                    "rehearsal failed and task-owned cleanup failed"
                ) from primary_error
            raise RestoreRehearsalError("task-owned cleanup failed")
        if primary_error is not None:
            if isinstance(primary_error, RestoreRehearsalError):
                raise primary_error
            raise RestoreRehearsalError("isolated rehearsal failed") from primary_error
        return RehearsalResult(True, True, True, True, True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preflight or run the fail-closed isolated restore rehearsal."
    )
    parser.add_argument("action", choices=("preflight", "execute"))
    parser.add_argument("archive", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("checksum", type=Path)
    parser.add_argument("--acknowledge", default="")
    args = parser.parse_args()
    if args.action == "preflight":
        if args.acknowledge:
            raise RestoreRehearsalError(
                "preflight does not accept execute acknowledgement"
            )
        preflight_artifacts(args.archive, args.manifest, args.checksum)
        print("isolated restore artifact paths preflighted; Docker was not started")
        return
    result = DockerRestoreRehearsal(
        args.archive, args.manifest, args.checksum
    ).execute(args.acknowledge)
    if not all(result.__dict__.values()):
        raise RestoreRehearsalError("isolated rehearsal did not complete")
    print("isolated restore rehearsal passed and task-owned resources were removed")


if __name__ == "__main__":
    main()
