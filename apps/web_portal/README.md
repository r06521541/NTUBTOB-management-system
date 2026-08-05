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
