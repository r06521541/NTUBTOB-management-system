"""Fictional, repository-local data for the development Web Portal demo."""

from copy import deepcopy


DEMO_MEMBER = {
    "id": "demo-member-01",
    "name": "示範球員 小林",
    "number": "18",
    "position": "內野手",
    "email": "demo.player@example.invalid",
}

DEMO_GAMES = [
    {
        "id": "demo-game-01",
        "date": "8 月 9 日（日）",
        "time": "09:00–11:30",
        "location": "示範河濱棒球場 A",
        "opponent": "晨光示範隊",
        "home_away": "主場・先守",
        "status": "pending",
        "responded": {
            "attending": ["示範隊員 阿哲", "示範隊員 小安", "示範隊員 大雄"],
            "declined": ["示範隊員 小宇"],
            "tentative": ["示範隊員 阿凱"],
        },
        "unanswered": ["示範隊員 小美", "示範隊員 阿正"],
    },
    {
        "id": "demo-game-02",
        "date": "8 月 16 日（日）",
        "time": "14:00–16:30",
        "location": "示範市民球場",
        "opponent": "海風原型隊",
        "home_away": "客場・先攻",
        "status": "attending",
        "responded": {
            "attending": ["示範隊員 阿哲", "示範隊員 小美", "示範隊員 阿正"],
            "declined": [],
            "tentative": ["示範隊員 小安"],
        },
        "unanswered": ["示範隊員 大雄"],
    },
    {
        "id": "demo-game-03",
        "date": "8 月 23 日（日）",
        "time": "10:30–13:00",
        "location": "示範大學棒球場",
        "opponent": "山丘測試隊",
        "home_away": "主場・先守",
        "status": "declined",
        "responded": {
            "attending": ["示範隊員 阿凱"],
            "declined": ["示範隊員 小宇"],
            "tentative": [],
        },
        "unanswered": ["示範隊員 小美", "示範隊員 大雄"],
    },
]


def get_demo_member():
    return deepcopy(DEMO_MEMBER)


def get_demo_games():
    return deepcopy(DEMO_GAMES)
