import os
from datetime import datetime, timedelta, time
import requests
import secrets
from flask import Flask, render_template, request, redirect, session, url_for, Response, send_from_directory
from flask_caching import Cache

from shared_module.models.games import Game
from shared_module.models.members import Member
from shared_module.models.line_users import LineUser
from shared_module.models.game_attendance_replies import GameAttendanceReply
import shared_module.line_notify as line_notify
import shared_module.attendance_analyzer as attendance_analyzer
from shared_module.settings import (
    local_timezone
)
from shared_module.general_message import (
    reply_text_mapping
)

import messages
from envs import (
    login_channel_id,
    login_channel_secret,
    secret_key
)

app = Flask(__name__)
app.secret_key = secret_key  # 用於保持安全的session

# 設定 Cache 配置
cache_config = {
    "CACHE_TYPE": "SimpleCache",  # 使用本地內存
    "CACHE_DEFAULT_TIMEOUT": 600  # 預設 Cache 有效期為600秒（10分鐘）
}
app.config.from_mapping(cache_config)

# 初始化 Cache
cache = Cache(app)

LINE_REDIRECT_URI = 'https://web-portal-7uz453jt3a-de.a.run.app/line/callback'

LINE_AUTH_URL = 'https://access.line.me/oauth2/v2.1/authorize'
LINE_TOKEN_URL = 'https://api.line.me/oauth2/v2.1/token'
LINE_USER_INFO_URL = 'https://api.line.me/v2/profile'

@app.route('/')
def home():
    return render_template('home.html')
    
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/add-line-friend')
def add_line_friend():
    return render_template('add_line_friend.html')

@app.route('/redirect-to-login')
def redirect_to_login():
    # 將原始目標URL存儲在session中
    next_url = request.args.get('next')
    if next_url:
        session['next_url'] = next_url
    else:
        session['next_url'] = url_for('home')

    return render_template('redirect_page.html')
    
@app.route('/line/login')
def line_login():
    # 生成隨機的 state
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state

    login_url = f"{LINE_AUTH_URL}?response_type=code&client_id={login_channel_id}&redirect_uri={LINE_REDIRECT_URI}&state={state}&scope=profile%20openid"
    return redirect(login_url)

@app.route('/line/callback')
def line_callback():
    code = request.args.get('code')
    state = request.args.get('state')
    
    # 驗證 state 是否符合
    if state != session.pop('oauth_state', None):
        return 'Invalid state parameter', 400

    # 使用授權碼獲取access token
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': LINE_REDIRECT_URI,
        'client_id': login_channel_id,
        'client_secret': login_channel_secret,
    }
    token_res = requests.post(LINE_TOKEN_URL, data=data).json()
    access_token = token_res['access_token']

    # 使用access token獲取使用者資訊
    headers = {'Authorization': f'Bearer {access_token}'}
    user_info_res = requests.get(LINE_USER_INFO_URL, headers=headers).json()

    # 以會籍的存在與否來授權
    is_authenticated = False
    user_id = user_info_res['userId']
    user = LineUser.search_by_id(user_id)
    if user:
        member = Member.search_by_id(user.member_id)
        if member:
            is_authenticated = True

            # 儲存使用者資訊於session中
            session['user_id'] = user_id
            session['member'] = member
            session['display_name'] = user_info_res['displayName']

    if is_authenticated:
        # 從session中取出next_url並重定向
        next_url = session.get('next_url', url_for('attendance'))
        return redirect(next_url)
    else:
        # 直接切換至未獲授權頁面
        return render_template('not_authenticated.html')


@app.route('/query-attendance')
def query_attendance():
    if 'user_id' not in session:
        return redirect(url_for('redirect_to_login', next=request.url))
    return redirect(url_for('attendance'))


@app.route('/attendance')
def attendance():
    if 'member' not in session:
        return redirect(url_for('query_attendance'))
    
    #member = Member.search_by_id(146)
    member = session['member']
    now = datetime.now(local_timezone).strftime("%Y年%-m月%-d日 %H:%M:%S")

    # 查詢未來的比賽
    upcoming_games = Game.search_for_invited()
    
    games_with_attendance = []
    for game in upcoming_games:
        mapping = attendance_analyzer.get_attendance_of_game(game.id)
        games_with_attendance.append({
            'game_summary': game.generate_short_summary_for_team(),
            'attendance_mapping': mapping,
        })
    
    return render_template('attendance.html', 
                           update_time=now,
                           my_membership=member,
                           games_with_attendance=games_with_attendance,
                           reply_text_mapping=reply_text_mapping)

@app.route('/match-member')
def index():
    line_users = LineUser.search_all_unknowns()
    members = Member.search_all()
    members.insert(0, None)
    return render_template('match_member.html', line_users=line_users, members=members)

@app.route('/match-member/match', methods=['POST'])
def match_line_user():
    line_user_id = request.form['line_user_id']
    member_id = request.form['member_id']
    if member_id:
        nickname = LineUser.search_by_id(line_user_id).nickname
        member_name = Member.search_by_id(member_id).name
        LineUser.update_member_id(line_user_id, member_id)
        line_notify.notify_management_message(messages.match_user_as_member.format(nickname=nickname, member_name=member_name))
    
    return redirect(url_for('index'))

@app.route('/match-member/ignore', methods=['POST'])
def ignore_line_user():
    line_user_id = request.form['line_user_id']
    
    LineUser.update_as_ignored(line_user_id)

    return redirect(url_for('index'))


key_prefix_future_games = 'future_games'

@app.route('/future-games')
@cache.cached(timeout=3600, key_prefix=key_prefix_future_games)
def future_games():
    now = datetime.now(local_timezone)
    today_begin = datetime.combine(now, time.min, tzinfo=local_timezone)
    _30_days_later = today_begin + timedelta(days=31)
    all_games = Game.search_between(today_begin, _30_days_later)
    this_week_games, this_month_games = Game.get_games_in_this_week_and_month(all_games)

    has_offseason = False
    for game in this_week_games:
        if game.season == 3:
            has_offseason = True

    for game in this_month_games:
        if game.season == 3:
            has_offseason = True

    return render_template('future_games.html', 
                           this_week_games=this_week_games,
                           this_month_games=this_month_games,
                           has_offseason=has_offseason)

@app.route('/game-roster/<int:game_id>')
def game_roster(game_id: int):
    game = Game.search_by_id(game_id)
    attendance_mapping = attendance_analyzer.get_attendance_of_game(game.id)
    return render_template('game_roster.html', 
                           game=game,
                           players=process_replies(attendance_mapping),
                           players_not_reply_yet=process_replies_who_has_not_reply_yet(attendance_mapping))

def process_replies(attendance_mapping: dict[int, list[Member]]) -> list[str]:
    names = []

    for reply, members in attendance_mapping.items():
        for member in members:
            name = member.name

            if reply == 1:
                names.append(name)
            elif reply == 3:
                names.append(f"{name}（晚到）")
            elif reply == 4:
                names.append(f"{name}（早走）")

    return names

def process_replies_who_has_not_reply_yet(attendance_mapping: dict[int, list[Member]]) -> list[str]:
    names = []

    for reply, members in attendance_mapping.items():
        for member in members:
            if reply == 5:
                names.append(member.name)
    return names

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)