# Web Portal production deployment — 5e85ea9

- Date: 2026-08-06 (Asia/Taipei)
- Task: TASK-040
- Result: successful; rollback not required
- Operator account: `yces3108@gmail.com`
- Project / region: `ntubtob-schedule-405614` / `asia-east1`
- Service: `web-portal`
- Approved and deployed commit: `5e85ea98634921d2d6ba4aa42c0f063ad5ba53ed`
- PR: #48 (squash merged)
- Hosted Python 3.10 CI run: `31069150451`, job `92513245008` — passed
- Cloud Build: `76dfce0c-d853-474e-a9ec-8a910a0b4637`
- Previous revision / rollback target: `web-portal-00035-mcl`
- New revision: `web-portal-00036-2p2`
- Image digest: `sha256:755e964c913e05f369271a1cbd666b91c64b267bcd3c5b44158ac81396eca9fc`
- Traffic: 100% to `web-portal-00036-2p2`
- Service URL: `https://web-portal-7uz453jt3a-de.a.run.app`

## Verification

- Preflight confirmed a clean exact-commit deployment source.
- Runtime identity remained `556891917512-compute@developer.gserviceaccount.com`.
- Existing Secret references remained `supabase-database-password`, `web-portal-line-login-channel-secret`, and `web-portal-session-secret-key`; no payload was read.
- New revision reported Ready and received 100% traffic.
- `GET /` returned 200.
- `GET /demo/` returned 404.
- `GET /redirect-to-login?next=/future-games` returned 200 and contained the mobile LINE guidance, desktop browser login label, and same-phone QR warning.
- The login guidance page did not contain the former mobile browser fallback wording, meta refresh, or `window.location` redirect.
- No login action was clicked; no LINE API, production DB, notification, admin action, Secret/IAM/LINE Console/schema/data change occurred.

## Rollback

Rollback was not required. If a later confirmed regression requires code rollback, the approved deployment-time target was the Ready revision `web-portal-00035-mcl`; any future traffic change requires a new explicit authorization.
