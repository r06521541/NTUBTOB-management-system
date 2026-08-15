"""Pure read projections for the schema-neutral Game command center."""

from __future__ import annotations

from datetime import timedelta

GAME_SCOPES = frozenset({"future", "recent", "past", "cancelled"})
GAME_REPLY_TYPES = (1, 3, 4, 2, 5)
LINEUP_REPLY_TYPES = frozenset(GAME_REPLY_TYPES)
LINEUP_QUALIFICATIONS = frozenset({"team_player", "guest_player"})


def bounded_game_role(person, admin_member_ids, local_preview=False):
    """Resolve only the temporary Game-route authority defined by DEC-089."""
    if person is None or getattr(person, "status", None) != "active":
        return None
    access_level = getattr(person, "access_level", None)
    if access_level not in {"basic", "officer", "admin"}:
        return None
    member_id = getattr(person, "member_id", None)
    if (
        isinstance(member_id, int)
        and not isinstance(member_id, bool)
        and member_id in admin_member_ids
    ):
        return "admin"
    if access_level == "officer":
        return "officer"
    if local_preview and access_level == "admin":
        return "admin"
    return None


def load_bounded_games(game_model, now):
    """Read invited Games from the existing legacy caller without mutation."""
    start = now - timedelta(days=365)
    end = now + timedelta(days=365)
    rows = []
    for cancelled, announced in ((False, False), (True, False), (True, True)):
        rows.extend(
            game_model.search_games(
                start,
                end,
                has_invited=True,
                has_cancelled=cancelled,
                has_cancellation_announced=announced,
            )
        )
    unique = {game.id: game for game in rows}
    return tuple(
        sorted(unique.values(), key=lambda game: game.start_datetime, reverse=True)[
            :250
        ]
    )


def game_scope(game, now):
    if game.cancellation_time is not None:
        return "cancelled"
    if game.start_datetime >= now:
        return "future"
    if game.start_datetime >= now - timedelta(days=30):
        return "recent"
    return "past"


def attendance_projection(summary):
    counts = {reply: 0 for reply in GAME_REPLY_TYPES}
    names = {reply: [] for reply in GAME_REPLY_TYPES}
    qualifications = {"team_player": 0, "guest_player": 0}
    candidates = []
    seen = set()
    for item in summary.participants:
        reply = item.get("reply")
        qualification = item.get("qualification")
        person_id = item.get("person_id")
        name = item.get("name")
        if (
            reply not in counts
            or qualification not in LINEUP_QUALIFICATIONS
            or not isinstance(person_id, int)
            or isinstance(person_id, bool)
            or not isinstance(name, str)
            or not name.strip()
            or person_id in seen
        ):
            continue
        seen.add(person_id)
        counts[reply] += 1
        names[reply].append(name)
        qualifications[qualification] += 1
        if reply in LINEUP_REPLY_TYPES:
            member_id = item.get("member_id")
            member_number = item.get("member_number")
            candidates.append(
                {
                    "id": f"person-{person_id}",
                    "person_id": person_id,
                    "member_id": (
                        member_id
                        if isinstance(member_id, int)
                        and not isinstance(member_id, bool)
                        and member_id > 0
                        else None
                    ),
                    "member_number": (
                        member_number
                        if isinstance(member_number, int)
                        and not isinstance(member_number, bool)
                        and 0 <= member_number <= 999
                        else None
                    ),
                    "name": name.strip(),
                    "qualification": qualification,
                    "reply": reply,
                }
            )
    team_total = max(0, int(summary.team_player_total))
    team_replied = max(0, min(team_total, int(summary.team_player_replied)))
    return {
        "counts": counts,
        "names": names,
        "qualifications": qualifications,
        "team_player_total": team_total,
        "team_player_replied": team_replied,
        "team_player_unresolved": team_total - team_replied,
        "candidates": tuple(candidates),
    }


def insight_projection(games, attendance_by_game, now):
    future_7 = 0
    future_30 = 0
    cancelled = 0
    recorded = []
    for game in games:
        if game.cancellation_time is not None:
            cancelled += 1
        elif now <= game.start_datetime <= now + timedelta(days=7):
            future_7 += 1
        if (
            game.cancellation_time is None
            and now <= game.start_datetime <= now + timedelta(days=30)
        ):
            future_30 += 1
        snapshot = attendance_by_game.get(game.id)
        if snapshot is not None:
            recorded.append(
                {
                    "game": game,
                    "recorded_replies": sum(snapshot["counts"].values()),
                    "team_player_unresolved": snapshot["team_player_unresolved"],
                }
            )
    recorded.sort(key=lambda item: item["game"].start_datetime, reverse=True)
    return {
        "future_7": future_7,
        "future_30": future_30,
        "cancelled": cancelled,
        "recorded": tuple(recorded[:12]),
    }
