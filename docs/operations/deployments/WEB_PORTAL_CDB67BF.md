# Web Portal production deployment — cdb67bf

- Date: 2026-08-06 (Asia/Taipei)
- Task: TASK-027
- Result: successful; rollback not required
- Operator account: `yces3108@gmail.com`
- Project / region: `ntubtob-schedule-405614` / `asia-east1`
- Service: `web-portal`
- Approved source and image tag: `cdb67bf007ec67d882c6e974143a4d527f1528cd`
- Successful Cloud Build: `7f155fb7-2288-416a-83a7-d77a95eee7e9`
- Superseded revision: `web-portal-00026-rtc`
- New revision: `web-portal-00027-fwf`
- Image digest: `sha256:730e0757411ca23e65c1b73b2ff31c8cf10aa1ca4698d290d1d3032aaaec8669`
- Traffic: 100% to `web-portal-00027-fwf`
- Service URL: `https://web-portal-7uz453jt3a-de.a.run.app`

## Safety boundary verification

- Runtime identity remained `556891917512-compute@developer.gserviceaccount.com`.
- Public invocation remained enabled through `allUsers` / `roles/run.invoker`.
- `DSN_PASSWORD` remained Secret-backed by `supabase-database-password:latest`.
- `LINE_LOGIN_CHANNEL_SECRET` is Secret-backed by `web-portal-line-login-channel-secret:1`.
- `SECRET_KEY` is Secret-backed by `web-portal-session-secret-key:1`.
- `WEB_PORTAL_ADMIN_MEMBER_IDS` is present as Owner-configured plain runtime configuration; its value was not read or printed.
- Production demo gates are absent; unauthenticated `GET /demo/` returned 404.
- Temporary `apps/web_portal/.env.yaml` was absent after deployment.
- No Secret payload, production database route, notification, LINE callback, IAM, Scheduler, schema, or data mutation was performed.

## Verification evidence

- Local Web Portal suite: 45 tests passed; 2 Unix-only Make/shell execution tests skipped on Windows.
- `compileall`: passed.
- `git diff --check`: passed before deployment.
- Cloud Run revision Ready: true.
- Unauthenticated `GET /`: HTTP 200 (one request).
- Unauthenticated `GET /demo/`: HTTP 404 (one request).

An initial build `f7d2cfec-e65e-4b8a-a386-2419224c1000` failed at input validation before image build or deployment because PowerShell split the substitutions argument. The corrected submission passed the substitutions as one argument. No rollback was required because the failed build did not create a revision or change traffic.

## Not verified

- LINE Login and callback/token exchange.
- Authenticated attendance, roster, member matching, or admin behavior.
- Production database connectivity or data correctness.
- Existing browser sessions are expected to be invalidated by the new Flask session key.

Rollback remains available by routing 100% traffic to `web-portal-00026-rtc` under the conditions defined in TASK-027.
