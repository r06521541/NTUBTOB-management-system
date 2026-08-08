# Web Portal local demo

## Brand UI and local visual review

The Portal uses `static/brand.css` as the shared source for its visual tokens.
Deep navy is the primary brand color, cool gray is the page and border system,
and muted warm gold is reserved for small highlights and focus states. Red is
reserved for danger, cancellation, decline, and error states. Green is reserved
for the official LINE action and explicit success or attendance states.

For a local visual review, start the offline demo with the command below and
check the dashboard, schedule, game detail, profile, pending, officer, and event
builder pages at about 375px and at desktop width. Also review `/`,
`/redirect-to-login`, and the recovery page through their existing offline route
tests. The shared Member navigation keeps Home, attendance, and account actions
available on narrow screens without changing any route or authorization rule.

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

The local login offers member, officer, and administrator previews. Their
navigation and protected demo routes use the same capability policy described
in `docs/planning/WEB_PORTAL_ACCESS_MATRIX.md`; all demo identities and changes
remain fictional and session-only.

## LINE Login callback continuity

LINE Login uses a short-lived, server-signed OAuth state bound to a nonce in the
browser session that started login. The state expires after 10 minutes and
contains only that random nonce and a validated local return path. Invalid,
expired, modified, or cross-session state is rejected before LINE or database
access. Return targets must be unambiguous absolute paths within this Web
Portal; external, scheme-relative, encoded-separator, backslash, and control
character inputs fall back to the attendance page.

This transaction binding prevents login CSRF/session swapping, but it also
means a callback opened in a genuinely different browser cookie store cannot
safely establish a session. A normal authorization request remains eligible for
LINE auto-login, including the smoother LINE in-app-browser experience. If the
callback cannot prove continuity with the initiating browser session, the error
page returns to the same-site login guidance page while preserving only the
validated local return path. It never reuses the failed authorization code,
state, or nonce. Unknown login modes, ambiguous return targets, and external
return URLs fail closed. No User-Agent detection or transferable cross-browser
state is used.

The LINE Developers callback URL remains
`https://web-portal-7uz453jt3a-de.a.run.app/line/callback`. This repository's
offline tests mock all LINE HTTP calls; they do not prove the callback URL or
credentials configured in LINE Developers and production are correct.

The login entry page deliberately waits for a user action instead of
automatically redirecting. On mobile, the supported path is to open the Portal
inside LINE and choose **在 LINE 中登入**. An external mobile browser may hand
off to the LINE app and return in a different cookie context, so that path is
best-effort rather than guaranteed. A QR code is not a workable fallback on the
same phone.

On desktop, **使用電腦瀏覽器登入** starts a separate fresh transaction with
auto-login disabled, allowing LINE to present its supported account or QR-code
flow. The underlying `mode=browser` route remains available, but the UI does not
present it as a reliable mobile recovery path. No User-Agent detection, custom
scheme, or external script is used. Android external-browser behavior remains
unverified; stable support for mobile browsers outside LINE would require a
separately designed authentication provider such as Google or Apple.

### Team Operations prototype

After entering the demo, the fictional team workspace includes:

- dashboard staffing warnings, reply deadlines, announcements, and quick actions;
- schedule status/venue filters, timeline/month views, richer attendance details,
  and an offline `.ics` export;
- a Game Day center with a proposed lineup, pre-game checklist, equipment claims,
  and carpool selection;
- a personal season summary and an officer workspace with notification previews;
- a multi-event prototype for trips, meals, practices, meetings and composite
  itineraries, with an officer-only builder and two-level attendance replies.

Attendance notes, arrival timing, position preference, checklist progress,
equipment claims, and carpool choices live only in the signed demo browser
session. Transport supports only fictional meeting points and validates the
self-arrival, needs-a-ride, and offers-seats flows. Notification preferences are
also session-only toggles. Use **重設 Demo 資料** on the profile page to clear
them. These controls do not write to a database or call LINE, maps, calendar,
weather, or any other
external service. The Game Day lineup, officer metrics, notifications, member
approval, and season statistics are product prototypes rather than operational
features.

The Event Builder supports three templates plus a blank Event, up to five Events
and twelve Activities per Event. It distinguishes a repository-local, read-only
league fixture from manually entered games. Drafts are officer-only; publishing,
cancelling, sorting, attendance replies and all builder edits remain in the demo
session. Publishing never sends LINE or another notification. Formal roles,
second-person approval, league synchronization, deduplication, and database
persistence remain undecided production work.

### Web Portal session cookie migration

The Web Portal uses the dedicated `ntubtob_web_session_v2` host-only cookie
with `HttpOnly`, `SameSite=Lax`, and `Path=/`. Production and every mode other
than the explicitly double-gated offline demo also require `Secure`. The local
demo is the only mode that permits the cookie over HTTP.

When a browser still sends Flask's legacy `session` cookie, the Web Portal
expires that exact host-scoped, root-path cookie without inspecting or logging
its value. An invalid or stale LINE callback remains rejected before LINE or
database access. Its error page clears only temporary OAuth transaction state,
preserves an existing authenticated member session, and lets the user start a
completely new login transaction. It never retries the old authorization code
or OAuth state.

Authenticated production sessions store only the opaque LINE `user_id` and
the linked numeric `member_id`. They do not store a serialized Member record or
LINE display name. Existing signed sessions are minimized on their next request
without a global logout; only those two legacy fields are removed, while OAuth
transaction, CSRF, return-path, and offline-demo state remain intact. The
attendance page loads the current Member by `member_id` for each request. If
that Member no longer exists, the Web Portal removes the authenticated identity
and stops before game or attendance queries.

A successful LINE callback emits one bounded operational diagnostic:
`line_login_callback destination=<category>`. The category is one of
`attendance`, `account`, `roster`, or `default`; it is derived from an
allowlist and never contains the return URL or query string. Do not expand this
log to include authorization codes, OAuth state or nonce values, cookies, LINE
profile data, Member identifiers, display names, or credentials. The signed
OAuth state remains the authority for the actual redirect destination.

## Role and capability policy

Role-to-capability mapping is centralized in `role_policy.py`. Production can
currently resolve only a linked `member` or an allowlisted `admin`; it cannot
produce an `officer`. Unknown roles, malformed identities, unknown
capabilities, and an invalid admin allowlist fail closed. This is an
authorization foundation, not role persistence: no schema, model, migration,
or production role assignment is included. See
`docs/planning/WEB_PORTAL_ACCESS_MATRIX.md` for the current route matrix.

## Production member account and logout

Authenticated linked members can open `/account` to see the current Member
name, LINE as the authentication method, and the Portal authorization label.
The Member record is loaded by `member_id` on every account request and is
never copied into the signed cookie. An allowlisted administrator sees the
system-administrator label and a policy-backed link to Member matching; regular
members do not see that link and remain denied by the server-side guard.

Account, attendance, and roster pages share a small local mobile navigation.
`POST /logout` requires its own session-bound CSRF token, separate from Member
matching. A valid logout clears the entire Web Portal session, including
temporary OAuth, administrative CSRF, and demo keys. Invalid or missing CSRF
does not alter the session, and GET cannot trigger logout. This action signs
out only this Portal session; it does not revoke or sign out the LINE account.

## Attendance performance diagnostic

A successful production `/attendance` response emits at most one bounded timing
event with integer millisecond values for `member_lookup`, `games_query`,
`attendance_analysis`, `render`, and `total`. The event contains no request path,
query, cookie, OAuth value, identity, game or member data, database setting,
credential, or exception text. Clock and logging failures are best-effort and do
not change the response. Every value is clamped to `0..300000` milliseconds to
bound malformed clock jumps; this diagnostic clamp is not a request timeout and
does not change runtime cancellation behavior. Offline demo routes do not emit
this diagnostic.

These application-stage timings do not include time spent before the Flask
handler starts, so they cannot prove or exclude a Cloud Run cold start by
themselves. Owner approval is required before reading production logs or changing
minimum instances, startup CPU, database pooling, queries, indexes, or caching.

## Member matching administration

The production member matching routes require both an authenticated LINE Login
session and a Member ID listed in `WEB_PORTAL_ADMIN_MEMBER_IDS`. The setting is
a comma-separated list of positive integer Member IDs, for example `7,12`.
Missing, empty, malformed, or duplicate values deny access to everyone; do not
place names, LINE user IDs, or credentials in this setting.

The member matching page creates a session CSRF token, and both matching actions
require that token. Unauthorized requests are rejected before management data is
queried or changed. Run the offline route and demo tests from the repository root:

Legacy Member matching and ignore writes are additionally frozen unless
`WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED` is exactly `true`. Missing, empty,
case-variant, or unknown values fail closed. The default is `false`; while
disabled, administrators can inspect pending rows but the page displays a
maintenance notice and disables its controls. The guard alone does not enable
Person/identity synchronization. When the separate Phase C flag is also enabled,
approved lifecycle mutations intentionally update the legacy projection and
Phase C identity records in one transaction. Neither production flag may be
enabled without a separately approved rollout.

The Phase C Person/identity read and attendance bridge has a separate exact
opt-in, `PORTAL_DATA_PHASE_C_ENABLED=true`. It defaults off. When enabled, LINE
Login persists `person_id` and `auth_identity_id`, every protected request
refreshes identity, Person, Member, and qualification state from PostgreSQL,
and an invalid principal fails closed without legacy-session fallback. Admin
mutations additionally require the existing maintenance flag and Member-ID
allowlist. Do not enable either production flag until the Phase C migration and
pre/post evidence have been separately approved and completed.

The shared runtime state machine also makes the otherwise invalid
`PORTAL_DATA_PHASE_C_ENABLED=false` plus
`WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED=true` combination effectively disable
maintenance. Cross-service activation and rollback must follow
`docs/operations/data/PORTAL_DATA_PHASE_C_APPLICATION_ROLLOUT.md`; a mixed flag
vector is not an accepted normal-traffic state.

The production game roster is team-private. `/game-roster/<game_id>` requires a
valid LINE Login session linked to a positive integer Member ID; anonymous or
malformed sessions are redirected to login before roster data is queried. This
is a membership boundary only. Visibility differences between members, officers,
and administrators remain deferred to the proposed RBAC work.

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
