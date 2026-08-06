# Web Portal route access matrix

Status: accepted foundation for TASK-041. This document describes repository
behavior; it does not grant a production role or change database state.

## Production roles

Production resolves an authenticated, linked session to `member`. A positive
Member ID in the complete and valid `WEB_PORTAL_ADMIN_MEMBER_IDS` allowlist
resolves to `admin`. Production has no source for `officer`, so nobody can
receive that role until a separately approved persistence design exists.

| Route group | Anonymous | Member | Officer | Admin | Enforced capability |
| --- | --- | --- | --- | --- | --- |
| `/attendance` | Login redirect | Allow | Future role | Allow | `view_member_portal` |
| `/game-roster/<id>` | Login redirect | Allow | Future role | Allow | `view_member_portal` |
| `/match-member` | Login redirect | 403 | Future role | Allow | `manage_members` |
| `/match-member/match` | Login redirect | 403 | Future role | Allow | `manage_members` + CSRF |
| `/match-member/ignore` | Login redirect | 403 | Future role | Allow | `manage_members` + CSRF |

Public home, login and published schedule routes retain their existing access.
This task does not broaden or redesign them.

## Capability inheritance

| Capability | Member | Officer | Admin |
| --- | --- | --- | --- |
| `view_member_portal`, `reply_own_attendance` | Yes | Yes | Yes |
| `manage_events`, `view_team_attendance`, `manage_game_day`, `prepare_notifications` | No | Yes | Yes |
| `send_notifications`, `manage_members`, `approve_accounts`, `assign_roles`, `view_audit_log` | No | No | Yes |

The policy denies unknown roles and capabilities. UI visibility is convenience
only; protected routes enforce the same policy before reading management data
or mutating session state.

## Offline demo

The double-gated local demo login can explicitly preview `member`, `officer`,
or `admin`. Officer and admin can reach the fictional officer workspace and
session-only Event Builder because both have `manage_events`; member receives
403 and does not see its navigation. These demo roles never resolve a
production principal and never read a database.
