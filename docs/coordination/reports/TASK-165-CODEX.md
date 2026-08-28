# TASK-165 Codex report

## Delivery delta

- Production Event-management entry and all `/manage/events` routes now authorize through `get_current_principal()` and `MANAGE_EVENTS` instead of persisted raw access levels.
- Allowlisted administrators retain access even with persisted `basic`; non-allowlisted persisted `officer`／`admin` users are denied in production. Local fictional preview remains persisted-role based.
- Active lifecycle and exact session Person／identity matching remain fail closed before Event service access.
- The management hub derives Event visibility from the same request capability and no longer hard-codes it.
- The global Portal navigation now uses the canonical request principal's capability plus active lifecycle state; unauthenticated/error rendering does not force repository access.
- `PostgresTeamPortalRepository` now has immutable Event-manager Member allowlist input and an explicit persisted-role preview mode. Production Web composition passes the runtime allowlist with preview fallback disabled; the repository repeats the authorization check before every Event operation.

## Verification

- Regression-first result before implementation: 5 expected failures across production allowlist precedence and management-hub visibility.
- Focused Web authorization/composition regressions: 6 passed; adjacent unauthenticated context regression passed.
- `py -3.10 -m unittest tests/portal_data/test_repository_contract.py -q`: 20 passed; 23 PostgreSQL cases skipped because no isolated local URL is configured. The four new PostgreSQL contract cases are present but require hosted PostgreSQL evidence.
- `py -3.10 -m unittest tests.test_admin_security -q`: 128 passed.
- `py -3.10 -m unittest discover -s tests -q` from `apps/web_portal`: 227 passed.
- Python compile covers the two production modules and direct tests; selected same-version Black API and `git diff --check` pass.
- Selected per-file Black checks, `git diff --check`, exact scope and self-review: passed.

## Remaining gates

- Independent Auth／Identity and Data／Auth reviews accepted after the Web-global-navigation and real repository-guard findings were corrected.
- Hosted PostgreSQL／Web CI, PR and deployment remain Main／Owner gates.
- No database, cloud/runtime, Secret, IAM, provider, notification or production mutation is authorized.
