"""Central, repository-local role and capability policy for Web Portal."""

from dataclasses import dataclass


ROLE_MEMBER = "member"
ROLE_OFFICER = "officer"
ROLE_ADMIN = "admin"
ROLES = frozenset({ROLE_MEMBER, ROLE_OFFICER, ROLE_ADMIN})

VIEW_MEMBER_PORTAL = "view_member_portal"
REPLY_OWN_ATTENDANCE = "reply_own_attendance"
MANAGE_EVENTS = "manage_events"
VIEW_TEAM_ATTENDANCE = "view_team_attendance"
MANAGE_GAME_DAY = "manage_game_day"
PREPARE_NOTIFICATIONS = "prepare_notifications"
SEND_NOTIFICATIONS = "send_notifications"
MANAGE_MEMBERS = "manage_members"
APPROVE_ACCOUNTS = "approve_accounts"
ASSIGN_ROLES = "assign_roles"
VIEW_AUDIT_LOG = "view_audit_log"

MEMBER_CAPABILITIES = frozenset(
    {VIEW_MEMBER_PORTAL, REPLY_OWN_ATTENDANCE}
)
OFFICER_CAPABILITIES = MEMBER_CAPABILITIES | frozenset(
    {
        MANAGE_EVENTS,
        VIEW_TEAM_ATTENDANCE,
        MANAGE_GAME_DAY,
        PREPARE_NOTIFICATIONS,
    }
)
ADMIN_CAPABILITIES = OFFICER_CAPABILITIES | frozenset(
    {
        SEND_NOTIFICATIONS,
        MANAGE_MEMBERS,
        APPROVE_ACCOUNTS,
        ASSIGN_ROLES,
        VIEW_AUDIT_LOG,
    }
)
ROLE_CAPABILITIES = {
    ROLE_MEMBER: MEMBER_CAPABILITIES,
    ROLE_OFFICER: OFFICER_CAPABILITIES,
    ROLE_ADMIN: ADMIN_CAPABILITIES,
}


@dataclass(frozen=True)
class Principal:
    role: str
    member_id: object = None


def has_capability(principal, capability):
    """Deny unknown/malformed roles and capabilities by default."""
    if not isinstance(principal, Principal):
        return False
    capabilities = ROLE_CAPABILITIES.get(principal.role)
    return capabilities is not None and capability in capabilities


def resolve_production_principal(session_values, admin_member_ids):
    """Resolve only member/admin in production; officer has no source yet."""
    user_id = session_values.get("user_id")
    member_id = session_values.get("member_id")
    if not isinstance(user_id, str) or not user_id.strip():
        return None
    if (
        not isinstance(member_id, int)
        or isinstance(member_id, bool)
        or member_id <= 0
    ):
        return None
    role = ROLE_ADMIN if member_id in admin_member_ids else ROLE_MEMBER
    return Principal(role=role, member_id=member_id)


def resolve_demo_principal(session_values):
    if session_values.get("demo_authenticated") is not True:
        return None
    member = session_values.get("demo_member")
    if not isinstance(member, dict):
        return None
    role = member.get("demo_role")
    if role not in ROLES:
        return None
    return Principal(role=role, member_id=member.get("id"))
