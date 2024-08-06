import functions_framework
from datetime import datetime, timedelta, timezone
from shared_module.models.games import Game
from shared_module.games_crawler_client import CrawlerClient
import shared_module.line_notify as line_notify
import shared_module.settings as settings

import envs


@functions_framework.http
def main(request):    
    team_name = settings.current_team
    now = datetime.now(timezone.utc)
    end_time = now + timedelta(days=30)
    games_after = game_crawl(team_name, now, end_time)
    if games_after is None:
        line_notify.notify_alarm_log("賽程更新失敗 -- 爬蟲撈不到比賽")
        return ''
    games_before_update = Game.search_between(now, end_time)
    if games_before_update is None:
        line_notify.notify_alarm_log("賽程更新失敗 -- 搜不到資料表中的比賽")
        return ''    

    # 找到需要新增的比賽
    games_to_add = [game for game in games_after if game not in games_before_update]
    # 找到需要取消的比賽
    games_to_cancel = [game for game in games_before_update if game not in games_after]
    # 因為 Game 有實作 __eq__ 方法，所以可以用in來判斷
    
    is_successful = True
    for game_to_add in games_to_add:
        Game.add_game(game_to_add)
        line_notify.notify_successful_log(f"賽程更新 -- 已成功添加新比賽\n{game_to_add.generate_short_summary_for_team()}")

    for game_to_cancel in games_to_cancel:
        if game_to_cancel.start_datetime < now:
            continue        
        Game.update_cancellation_time(game_to_cancel.id, now)
        line_notify.notify_successful_log(f"賽程更新 -- 已成功取消這場比賽\n{game_to_cancel.generate_short_summary_for_team()}")

    if is_successful:
        line_notify.notify_successful_log("賽程更新 -- 已成功完成此次games資料表的更新")
    return ''

def game_crawl(team_name: str, start_time: datetime, end_time: datetime) -> list[Game]:
    games_crawler_client = CrawlerClient(envs.game_crawl_api)
    games = games_crawler_client.get_games()
    game_list = [Game.from_dict(data) for data in games]
    try:
        games = [game for game in game_list if game.home_team == team_name or game.away_team == team_name]
        games = [game for game in game_list if game.start_datetime >= start_time and game.start_datetime <= end_time]
        return games
    
    except Exception as e:
        line_notify.notify_alarm_log(repr(e))

    return None
