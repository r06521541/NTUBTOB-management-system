# Web Portal route access matrix

Status: accepted foundation for TASK-041. This document describes repository
behavior; it does not grant a production role or change database state.

## Production roles

Production resolves an authenticated, linked session to `member`. A positive
Member ID in the complete and valid `WEB_PORTAL_ADMIN_MEMBER_IDS` allowlist
resolves to `admin`. Production has no source for `officer`, so nobody can
receive that role until a separately approved persistence design exists.

The approved persistence direction introduces Person as the authorization
principal, with `basic`, `officer`, and `admin` access levels and independent
pending/active/disabled/inactive/blocked status. Member is a permanent alumni
roster record; team/guest/affiliate/staff are independent, multi-value
qualifications. It is not yet implemented. Unknown identities, access levels,
statuses, and qualifications fail closed.

| Route group | Anonymous | Basic | Officer | Admin | Enforced capability |
| --- | --- | --- | --- | --- | --- |
| `/account` | Login redirect | Allow | Future role | Allow + management entry | `view_member_portal`; entry uses `manage_members` |
| `POST /logout` | Login redirect | Allow with logout CSRF | Future role | Allow with logout CSRF | `view_member_portal` + dedicated CSRF |
| `/attendance` | Login redirect | Allow | Future role | Allow | `view_member_portal` |
| `/game-roster/<id>` | Login redirect | Allow | Future role | Allow | `view_member_portal` |
| `/match-member` | Login redirect | 403 | Future role | Allow | `manage_members` |
| `/match-member/match` | Login redirect | 403 | Future role | Allow | `manage_members` + CSRF |
| `/match-member/ignore` | Login redirect | 403 | Future role | Allow | `manage_members` + CSRF |

Public home, login and published schedule routes retain their existing access.
This task does not broaden or redesign them.

Future production officer Event routes are not present today. When implemented,
their UI and every read/mutation route must independently require the matching
capability; an officer navigation link is never an authorization boundary.

The account page reloads the Member by session `member_id` for each request and
shows only the confirmed Member name, LINE login method, and policy-derived
Portal role. Logout is POST-only and clears the full Portal session only after
constant-time validation of a dedicated token that is not shared with Member
matching. It does not call LINE or another external service.

The table labels the approved future access level as Basic. Current code still
names this policy role `member`; a compatibility adapter/rename is required and
has not been implemented.

## Capability inheritance

| Capability | Basic | Officer | Admin |
| --- | --- | --- | --- |
| `view_member_portal`, `reply_own_attendance` | Yes | Yes | Yes |
| `manage_events`, `view_team_attendance`, `manage_game_day`, `prepare_notifications` | No | Yes | Yes |
| `send_notifications`, `manage_members`, `approve_accounts`, `assign_roles`, `view_audit_log` | No | No | Yes |

The policy denies unknown roles and capabilities. UI visibility is convenience
only; protected routes enforce the same policy before reading management data
or mutating session state.

Event eligibility and roster/statistics membership are not inferred from this
table. They use published `event_invitees` snapshots and explicit
`team_player`/`guest_player` qualifications. An officer/admin without a player
qualification does not appear as a player merely because of access level.

## Offline demo

The double-gated local demo login currently previews `member`, `officer`,
or `admin`. Officer and admin can reach the fictional officer workspace and
session-only Event Builder because both have `manage_events`; member receives
403 and does not see its navigation. Future fixture wording should rename the
demo `member` access role to `basic` while separately assigning player
qualifications. These demo roles never resolve a production principal and never
read a database.
