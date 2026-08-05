# Web Portal local demo

The demo is an offline Flask/Jinja product prototype. It uses fictional data in
the browser session and does not require LINE credentials, a database, or an
external API. Both environment gates are required; the demo is off by default.

From the repository root, after installing the existing requirements, start it
in Windows PowerShell with one command:

```powershell
$env:WEB_PORTAL_ENV='development'; $env:WEB_PORTAL_DEMO_MODE='true'; python apps/web_portal/app.py
```

For POSIX shells:

```sh
WEB_PORTAL_ENV=development WEB_PORTAL_DEMO_MODE=true python apps/web_portal/app.py
```

Open <http://127.0.0.1:8080/demo/> and choose **進入虛構 Demo**. Stop the
server with `Ctrl+C`. Clear the two variables before running the application in
another mode. A missing gate, a misspelled value, or any environment other than
`development` returns 404 for every demo route.

Google and Apple sign-in, notification preferences, attendance persistence,
and administrator approval are visual prototypes only. Existing LINE routes
remain present, but selecting LINE requires the real application configuration
and is not part of the offline demo.

### Team Operations prototype

After entering the demo, the fictional team workspace includes:

- dashboard staffing warnings, reply deadlines, announcements, and quick actions;
- schedule status/venue filters, timeline/month views, richer attendance details,
  and an offline `.ics` export;
- a Game Day center with a proposed lineup, pre-game checklist, equipment claims,
  and carpool selection;
- a personal season summary and an officer workspace with notification previews.

Attendance notes, arrival timing, position preference, checklist progress,
equipment claims, and carpool choices live only in the signed demo browser
session. Transport supports only fictional meeting points and validates the
self-arrival, needs-a-ride, and offers-seats flows. Notification preferences are
also session-only toggles. Use **重設 Demo 資料** on the profile page to clear
them. These controls
do not write to a database or call LINE, maps, calendar, weather, or any other
external service. The Game Day lineup, officer metrics, notifications, member
approval, and season statistics are product prototypes rather than operational
features.

## Member matching administration

The production member matching routes require both an authenticated LINE Login
session and a Member ID listed in `WEB_PORTAL_ADMIN_MEMBER_IDS`. The setting is
a comma-separated list of positive integer Member IDs, for example `7,12`.
Missing, empty, malformed, or duplicate values deny access to everyone; do not
place names, LINE user IDs, or credentials in this setting.

The member matching page creates a session CSRF token, and both matching actions
require that token. Unauthorized requests are rejected before management data is
queried or changed. Run the offline route and demo tests from the repository root:

```sh
python -m unittest discover -s apps/web_portal/tests -v
```

## Deployment preflight

The repository deployment target filters `DSN_PASSWORD`,
`LINE_LOGIN_CHANNEL_SECRET`, and `SECRET_KEY` out of the temporary non-secret
environment file. `.dockerignore` prevents that temporary file from entering the
container image. `WEB_PORTAL_ADMIN_MEMBER_IDS` remains a non-secret runtime
setting; never commit real production values.

Deployment requires two explicit Secret Manager references and an exact
40-character Git commit SHA. The references identify Secret Manager resources
and versions; they are not Secret values:

```sh
make deploy-web-portal \
  IMAGE_TAG=<FULL_40_CHARACTER_GIT_SHA> \
  WEB_PORTAL_LINE_LOGIN_SECRET_REF=<SECRET_RESOURCE:VERSION> \
  WEB_PORTAL_SESSION_SECRET_REF=<SECRET_RESOURCE:VERSION>
```

Missing references, placeholders, or a non-commit image tag fail before build or
deployment. Do not run this command without an Owner-approved production work
package. Repository tests only verify the static deployment contract; they do
not prove that Secret resources exist, that runtime IAM can access them, or that
the image builds and runs in Cloud Run.
