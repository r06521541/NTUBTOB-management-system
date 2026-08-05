"""Fictional, repository-local data for the development Web Portal demo."""

from copy import deepcopy


DEMO_MEMBER = {
    "id": "demo-member-01",
    "name": "示範球員 小林",
    "number": "18",
    "position": "二壘手／游擊手",
    "email": "demo.player@example.invalid",
    "bats_throws": "右投右打",
    "season_games": 7,
    "attendance_rate": 86,
    "demo_role": "officer",
}

DEMO_ANNOUNCEMENTS = [
    {"title": "本週球衣：深色款", "detail": "請於集合前換裝完成。", "tag": "置頂"},
    {"title": "賽後聚餐意願調查", "detail": "週五 20:00 前回覆即可。", "tag": "隊務"},
]

DEMO_GAMES = [
    {
        "id": "demo-game-01",
        "starts_at": "20260809T090000",
        "ends_at": "20260809T113000",
        "date": "8 月 9 日（日）",
        "day": "09",
        "month": "AUG",
        "time": "09:00–11:30",
        "location": "示範河濱棒球場 A",
        "map_url": "https://maps.example.invalid/demo-ballpark-a",
        "opponent": "晨光示範隊",
        "home_away": "主場・先守",
        "venue_type": "home",
        "deadline": "8 月 7 日 20:00",
        "deadline_hours": 26,
        "status": "pending",
        "team_note": "08:20 集合，深色球衣。若下雨於 07:00 公告。",
        "responded": {
            "attending": ["示範隊員 阿哲", "示範隊員 小安", "示範隊員 大雄", "示範隊員 阿凱", "示範隊員 小宇", "示範隊員 阿南", "示範隊員 小傑"],
            "declined": ["示範隊員 小豪"],
            "tentative": ["示範隊員 小明"],
        },
        "unanswered": ["示範隊員 小美", "示範隊員 阿正"],
        "coverage": {"total": 7, "pitchers": 1, "catchers": 0, "infielders": 3, "outfielders": 3},
        "lineup": [
            ["1", "阿哲", "游擊"], ["2", "小安", "中外野"], ["3", "大雄", "三壘"],
            ["4", "阿凱", "一壘"], ["5", "小宇", "投手"], ["6", "阿南", "左外野"],
            ["7", "小傑", "右外野"], ["8", "待安排", "捕手"], ["9", "小林", "二壘"],
        ],
        "checklist": ["比賽球與球袋", "捕手護具", "急救包", "冰桶與飲水"],
    },
    {
        "id": "demo-game-02", "starts_at": "20260816T140000", "ends_at": "20260816T163000",
        "date": "8 月 16 日（日）", "day": "16", "month": "AUG", "time": "14:00–16:30",
        "location": "示範市民球場", "map_url": "https://maps.example.invalid/demo-city-field",
        "opponent": "海風原型隊", "home_away": "客場・先攻", "venue_type": "away", "deadline": "8 月 14 日 20:00",
        "deadline_hours": 194, "status": "attending", "team_note": "13:20 三壘側入口集合。",
        "responded": {"attending": ["示範隊員 阿哲", "示範隊員 小美", "示範隊員 阿正", "示範隊員 阿凱", "示範隊員 小宇", "示範隊員 阿南", "示範隊員 小傑", "示範隊員 大雄", "示範隊員 小安"], "declined": [], "tentative": ["示範隊員 小明"]},
        "unanswered": ["示範隊員 小豪"], "coverage": {"total": 9, "pitchers": 2, "catchers": 1, "infielders": 4, "outfielders": 4},
        "lineup": [], "checklist": ["比賽球與球袋", "冰桶與飲水"],
    },
    {
        "id": "demo-game-03", "starts_at": "20260823T103000", "ends_at": "20260823T130000",
        "date": "8 月 23 日（日）", "day": "23", "month": "AUG", "time": "10:30–13:00",
        "location": "示範大學棒球場", "map_url": "https://maps.example.invalid/demo-university-field",
        "opponent": "山丘測試隊", "home_away": "主場・先守", "venue_type": "home", "deadline": "8 月 21 日 20:00",
        "deadline_hours": 362, "status": "declined", "team_note": "集合資訊尚待幹部確認。",
        "responded": {"attending": ["示範隊員 阿凱"], "declined": ["示範隊員 小宇"], "tentative": []},
        "unanswered": ["示範隊員 小美", "示範隊員 大雄"], "coverage": {"total": 1, "pitchers": 0, "catchers": 0, "infielders": 1, "outfielders": 0},
        "lineup": [], "checklist": ["比賽球與球袋"],
    },
]

DEMO_TASKS = {
    "rides": [
        {"id": "ride-01", "title": "捷運示範站 2 號出口", "owner": "阿哲", "detail": "08:00 出發・尚有 2 席"},
        {"id": "ride-02", "title": "示範大學正門", "owner": "小安", "detail": "08:10 出發・尚有 1 席"},
    ],
    "gear": [
        {"id": "gear-balls", "title": "比賽球與球袋", "owner": "阿凱"},
        {"id": "gear-catcher", "title": "捕手護具", "owner": "待認領"},
        {"id": "gear-first-aid", "title": "急救包", "owner": "小美"},
        {"id": "gear-water", "title": "冰桶與飲水", "owner": "待認領"},
    ],
}


def get_demo_member():
    return deepcopy(DEMO_MEMBER)


def get_demo_games():
    return deepcopy(DEMO_GAMES)


def get_demo_announcements():
    return deepcopy(DEMO_ANNOUNCEMENTS)


def get_demo_tasks():
    return deepcopy(DEMO_TASKS)
