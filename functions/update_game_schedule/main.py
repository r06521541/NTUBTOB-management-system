import functions_framework
from datetime import datetime, timedelta, timezone
from shared_module.games import Game

import envs
import apis


@functions_framework.http
def main(request):    
    team_name = envs.team_name
    now = datetime.now(timezone.utc)
    end_time = now + timedelta(days=30)
    games_after = apis.game_crawl(team_name, now, end_time)
    if games_after is None:
        apis.notify_alarm("賽程更新失敗 -- 爬蟲撈不到比賽")
        return ''
    games_before_update = Game.search_between(now, end_time)
    if games_before_update is None:
        apis.notify_alarm("賽程更新失敗 -- 搜不到資料表中的比賽")
        return ''    

    # 找到需要新增的比賽
    games_to_add = [game for game in games_after if game not in games_before_update]
    # 找到需要取消的比賽
    games_to_cancel = [game for game in games_before_update if game not in games_after]
    # 因為 Game 有實作 __eq__ 方法，所以可以用in來判斷
    
    is_successful = True
    for game_to_add in games_to_add:
        Game.add_game(game_to_add.to_dict())

    for game_to_cancel in games_to_cancel:
        if game_to_cancel.start_datetime < now:
            continue        
        Game.update_cancellation_time(game_to_cancel, now)

    if is_successful:
        apis.notify_successful("賽程更新 -- 已成功將賽程更新到games資料表")
    return ''

