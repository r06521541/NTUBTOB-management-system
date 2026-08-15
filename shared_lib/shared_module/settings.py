from datetime import timedelta, timezone

current_team = '臺大'
current_team_aliases = frozenset({current_team, '台大', 'NTUBTOB'})
local_timezone = timezone(timedelta(hours=8))  # 台北時間（UTC+08:00）


def is_current_team(team_name: str) -> bool:
    return (
        team_name.strip() in current_team_aliases
        if isinstance(team_name, str)
        else False
    )
