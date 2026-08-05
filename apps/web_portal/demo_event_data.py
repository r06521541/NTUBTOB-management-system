"""Fictional event fixtures used only by the development demo."""

from copy import deepcopy


LEAGUE_GAME = {
    "league_id": "DEMO-LEAGUE-2026-0815",
    "title": "聯盟示範賽 vs 星河虛構隊",
    "date": "2026-08-15",
    "start": "09:00",
    "end": "11:30",
    "location": "示範聯盟球場",
    "opponent": "星河虛構隊",
    "venue": "away",
}


SEED_EVENTS = [
    {
        "id": "event-demo-trip",
        "title": "台中示範移地週末",
        "type": "trip",
        "start_date": "2026-08-14",
        "end_date": "2026-08-16",
        "location": "台中虛構園區",
        "description": "兩夜移地行程，所有地點與隊名皆為虛構資料。",
        "status": "published",
        "creator": "示範幹部 小林",
        "activities": [
            {"id": "activity-demo-t1", "type": "transport", "title": "集合與出發", "date": "2026-08-14", "start": "18:30", "end": "19:00", "location": "示範大學正門", "description": "搭乘虛構接駁車。", "source": None},
            {"id": "activity-demo-t2", "type": "lodging", "title": "入住示範旅館", "date": "2026-08-14", "start": "20:30", "end": "21:00", "location": "Demo Stay Hotel.invalid", "description": "不收集證件或房型資料。", "source": None},
            {"id": "activity-demo-t3", "type": "game", "title": LEAGUE_GAME["title"], "date": LEAGUE_GAME["date"], "start": LEAGUE_GAME["start"], "end": LEAGUE_GAME["end"], "location": LEAGUE_GAME["location"], "description": "聯盟匯入 fixture，欄位唯讀。", "source": "league_imported", "league_id": LEAGUE_GAME["league_id"], "opponent": LEAGUE_GAME["opponent"], "venue": LEAGUE_GAME["venue"]},
            {"id": "activity-demo-t4", "type": "game", "title": "友誼賽 vs 木星測試隊", "date": "2026-08-15", "start": "14:30", "end": "17:00", "location": "虛構河濱 B 場", "description": "幹部手動建立。", "source": "manual", "opponent": "木星測試隊", "venue": "home"},
            {"id": "activity-demo-t5", "type": "meal", "title": "全隊晚餐", "date": "2026-08-15", "start": "18:30", "end": "20:00", "location": "示範餐廳.invalid", "description": "不含付款或飲食個資。", "source": None},
            {"id": "activity-demo-t6", "type": "game", "title": "OB交流賽 vs 時光虛構隊", "date": "2026-08-16", "start": "10:00", "end": "12:30", "location": "示範市民球場", "description": "幹部手動建立。", "source": "manual", "opponent": "時光虛構隊", "venue": "away"},
        ],
    },
    {
        "id": "event-demo-meal", "title": "八月球隊聚餐", "type": "meal", "start_date": "2026-08-22", "end_date": "2026-08-22", "location": "示範餐廳.invalid", "description": "單純聚餐 Event 原型。", "status": "published", "creator": "示範幹部 小林",
        "activities": [{"id": "activity-demo-m1", "type": "meal", "title": "球隊聚餐", "date": "2026-08-22", "start": "18:00", "end": "20:00", "location": "示範餐廳.invalid", "description": "虛構訂位。", "source": None}],
    },
    {
        "id": "event-demo-draft", "title": "OB交流賽草稿", "type": "game_day", "start_date": "2026-09-05", "end_date": "2026-09-05", "location": "待確認示範球場", "description": "只有幹部工作台可見。", "status": "draft", "creator": "示範幹部 小林",
        "activities": [{"id": "activity-demo-d1", "type": "game", "title": "OB交流賽", "date": "2026-09-05", "start": "09:00", "end": "11:30", "location": "待確認示範球場", "description": "手動比賽草稿。", "source": "manual", "opponent": "校友虛構隊", "venue": "home"}],
    },
]


def get_seed_events():
    return deepcopy(SEED_EVENTS)


def get_league_game():
    return deepcopy(LEAGUE_GAME)
