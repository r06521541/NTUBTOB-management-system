from flask import Flask, request, jsonify, abort
from shared_module.games import Game

from flask import Flask, request, jsonify, abort, Request
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
import logging

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.errorhandler(400)
def bad_request(error):
    logger.error(f"Bad Request: {error}")
    return jsonify({'status': 'error', 'message': 'Invalid JSON format or missing required fields'}), 400

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal Server Error: {error}")
    return jsonify({'status': 'error', 'message': f'{error}'}), 500

@app.route('/add_game', methods=['POST'])
def add_game():
    try:
        # 解析 POST 請求中的比賽資訊
        request_json = request.get_json(silent=True)
        if (not Game.is_game_json_valid(request_json)):
            abort(400)

        # 寫入比賽資訊到資料庫
        Game.add_game(request_json)
        return jsonify({'status': 'success', 'message': 'Game added successfully'})

    except Exception as e:
        abort(500, description=str(e))

@app.route('/search_for_invitation', methods=['POST'])
def search_for_invitation():
    try:
        # 讀取比賽資訊，輸出
        start_time, end_time = get_start_end_time_from_json(request)
        games = Game.search_for_invitation(start_time, end_time)
        # 使用列表推導式將每個物件轉換為字典
        game_list = [game.as_dict() for game in games]
        return jsonify({'status': 'success', 'games': game_list})

    except Exception as e:
        abort(500, description=str(e))

@app.route('/search_invited', methods=['POST'])
def search_invited():
    try:
        # 讀取比賽資訊，輸出
        start_time, end_time = get_start_end_time_from_json(request)
        games = Game.search_for_invited(start_time, end_time)
        # 使用列表推導式將每個物件轉換為字典
        game_list = [game.as_dict() for game in games]
        return jsonify({'status': 'success', 'games': game_list})

    except Exception as e:
        abort(500, description=str(e))

@app.route('/search_cancelled_to_announce', methods=['POST'])
def search_cancelled_to_announce():
    try:
        # 讀取比賽資訊，輸出
        start_time, end_time = get_start_end_time_from_json(request)
        games = Game.search_cancelled_to_announce(start_time, end_time)
        # 使用列表推導式將每個物件轉換為字典
        game_list = [game.as_dict() for game in games]
        return jsonify({'status': 'success', 'games': game_list})

    except Exception as e:
        abort(500, description=str(e))

@app.route('/search_by_id', methods=['POST'])
def search_by_id():
    try:
        # 讀取比賽資訊，輸出
        games = Game.search_by_id(get_id_from_json(request))
        # 使用列表推導式將每個物件轉換為字典
        game_list = [game.as_dict() for game in games]
        return jsonify({'status': 'success', 'games': game_list})

    except Exception as e:
        abort(500, description=str(e))

@app.route('/search_by_time', methods=['POST'])
def search_by_time():
    try:
        # 讀取比賽資訊，輸出
        start_time, end_time = get_start_end_time_from_json(request)
        games = Game.search_between(start_time, end_time)
        # 使用列表推導式將每個物件轉換為字典
        game_list = [game.as_dict() for game in games]
        return jsonify({'status': 'success', 'games': game_list})

    except Exception as e:
        abort(500, description=str(e))

@app.route('/update_invitation_time', methods=['POST'])
def update_invitation_time():
    try:
        # 寫入比賽資訊到資料庫
        id, time = get_id_and_time_from_json(request)
        Game.update_invitation_time(id, time)
        return jsonify({'status': 'success', 'message': 'Update invitation time successfully'})

    except Exception as e:
        abort(500, description=str(e))

@app.route('/update_cancellation_time', methods=['POST'])
def update_cancellation_time():
    try:
        # 寫入比賽資訊到資料庫
        id, time = get_id_and_time_from_json(request)
        Game.update_cancellation_time(id, time)
        return jsonify({'status': 'success', 'message': 'Update cancellation time successfully'})

    except Exception as e:
        abort(500, description=str(e))

@app.route('/update_cancellation_announcement_time', methods=['POST'])
def update_cancellation_announcement_time():
    try:
        # 寫入比賽資訊到資料庫
        id, time = get_id_and_time_from_json(request)
        Game.update_cancellation_announcement_time(id, time)
        return jsonify({'status': 'success', 'message': 'Update cancellation announcement time successfully'})

    except Exception as e:
        abort(500, description=str(e))
        
def get_start_end_time_from_json(request: Request) -> Tuple[datetime, datetime]:
    request_json = request.get_json(silent=True)
    if (not Game.is_start_end_time_json_valid(request_json)):
        abort(400)
    start_time = Game.get_datetime(request_json['start_time'])
    end_time = Game.get_datetime(request_json['end_time'])
    return start_time, end_time

def get_id_from_json(request: Request) -> int:
    request_json = request.get_json(silent=True)
    if (not Game.is_game_id_valid(request_json)):
        abort(400)
    game_id = string_to_int(request_json['game_id'])
    return game_id

def get_id_and_time_from_json(request: Request) -> Tuple[int, datetime]:
    request_json = request.get_json(silent=True)
    if (not Game.is_update_game_time_valid(request_json)):
        abort(400)
    game_id = string_to_int(request_json['game_id'])
    time = Game.get_datetime(request_json['time'])
    return game_id, time

def string_to_int(string_value: str) -> int:
    try:
        # 尝试将字符串转换为整数
        integer_value = int(string_value)
        return integer_value
    except ValueError:
        # 如果字符串不能转换为整数，则抛出一个异常
        raise ValueError(f"Cannot convert '{string_value}' to an integer")


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
