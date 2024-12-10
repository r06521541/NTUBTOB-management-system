from sqlalchemy import Integer, String, DateTime
from sqlalchemy import update, and_
from sqlalchemy.orm import Session, DeclarativeBase, mapped_column, Mapped, relationship
from datetime import datetime, timezone, timedelta
from typing import Optional
from dataclasses import dataclass, asdict

from .db import engine
from ..settings import (
    local_timezone,
    current_team
)
from ..general_message import (
    weekday_mapping,
    offseason_game_sign,
    normal_game_sign,
    season_mapping
)
from .base import Base

@dataclass
class Game(Base):
    __tablename__ = 'games'
    __table_args__ = {'schema': 'ntubtob'}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    year: Mapped[int] = mapped_column(Integer)
    season: Mapped[int] = mapped_column(Integer)
    start_datetime: Mapped[datetime] = mapped_column(DateTime)
    duration: Mapped[int] = mapped_column(Integer)
    location: Mapped[str] = mapped_column(String)
    home_team: Mapped[str] = mapped_column(String)
    away_team: Mapped[str] = mapped_column(String)
    invitation_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    cancellation_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    cancellation_announcement_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    attendance_replies = relationship("GameAttendanceReply", back_populates="game")

    def as_dict(self):
        result = asdict(self)
        # Convert datetime to ISO 8601 format
        for key in ['start_datetime', 'invitation_time', 'cancellation_time', 'cancellation_announcement_time']:
            if key in result and isinstance(result[key], datetime):
                result[key] = result[key].isoformat()
        return result
    
    def __eq__(self, other):
        if isinstance(other, Game):
            if self.year != other.year: 
                return False
            if self.season != other.season: 
                return False
            if self.start_datetime != other.start_datetime: 
                return False
            if self.duration != other.duration: 
                return False
            if self.location != other.location: 
                return False
            if self.home_team != other.home_team: 
                return False
            if self.away_team != other.away_team: 
                return False
            return True
        return False
    
    def get_formatted_date(self) -> str:
        start_datetime = self.start_datetime.astimezone(local_timezone)

        # 獲取星期的中文表示
        chinese_weekday = weekday_mapping[start_datetime.strftime("%A")]

        # 格式化日期和時間
        return start_datetime.strftime("%-m/%-d（%a）").replace(
            start_datetime.strftime("%a"), chinese_weekday
        )

    def get_formatted_start_time(self) -> str:
        start_datetime = self.start_datetime.astimezone(local_timezone)
        return start_datetime.strftime("%H%M")
    
    def get_formatted_start_time_with_colon(self) -> str:
        start_datetime = self.start_datetime.astimezone(local_timezone)
        return start_datetime.strftime("%H:%M")
    
    def get_formatted_end_time(self) -> str:
        start_datetime = self.start_datetime.astimezone(local_timezone)
        # 格式化日期和時間
        return (start_datetime + timedelta(minutes=self.duration)).strftime("%H%M")

    def get_is_home_team(self) -> bool:
        return current_team == self.home_team

    def get_opponent(self) -> str:
        return self.away_team if self.get_is_home_team() else self.home_team
    
    def get_game_sign(self):
        return offseason_game_sign if self.is_offseason() else normal_game_sign
    
    def is_offseason(self):
        return self.season == 3

    def generate_summary(self):
        return f"{self.year}{season_mapping[self.season]} {self.get_formatted_date()} {self.get_formatted_start_time()} - {self.get_formatted_end_time()} {self.home_team} vs {self.away_team} @{self.location}"
        
    def generate_summary_for_team(self) -> str:
        if current_team != self.home_team and current_team != self.away_team:
            return self.generate_summary()
        # 生成格式化字串
        return f"{self.get_game_sign()} {self.get_formatted_date()} {self.get_formatted_start_time()} - {self.get_formatted_end_time()} vs {self.get_opponent()} {'先守' if self.get_is_home_team() else '先攻'} @{self.location}"
    
    def generate_short_summary_for_team(self) -> str:
        return f"{self.get_formatted_date()} {self.get_formatted_start_time_with_colon()} vs {self.get_opponent()} @{self.location}"

    def generate_verbal_summary_for_team(self) -> str:        
        return f"{self.get_formatted_date()}打{self.get_opponent()}"
    
    @classmethod
    def get_datetime(cls, datetime_str: str):               
        time = datetime.fromisoformat(datetime_str)
        if time.tzinfo is None:
            # 如果沒有時區資訊，添加預設時區
            time = time.replace(tzinfo=local_timezone)
        return time

    @classmethod 
    def from_dict(cls, data_dict: dict):
        # Convert ISO 8601 format strings back to datetime objects
        for key in ['start_datetime', 'invitation_time', 'cancellation_time', 'cancellation_announcement_time']:
            if key in data_dict and isinstance(data_dict[key], str):
                data_dict[key] = Game.get_datetime(data_dict[key])
        return cls(**data_dict)

    @classmethod 
    def is_game_json_valid(cls, game_json: dict[str, str]):
        required_fields = ['year', 'season', 'start_datetime', 'duration', 'location', 'home_team', 'away_team']
        return all(field in game_json for field in required_fields)

    @classmethod 
    def add_game_by_dict(cls, game_json: dict[str, str]):
        # 建立新比賽物件
        game = Game(year = game_json['year'], 
                        season = game_json['season'],
                        start_datetime = game_json['start_datetime'],
                        duration = game_json['duration'],
                        location = game_json['location'],
                        home_team = game_json['home_team'],
                        away_team = game_json['away_team'])
        
        with Session(engine) as session:
            # 加入資料庫
            session.add(game)
            session.commit()
            
    @classmethod 
    def add_game(cls, game: 'Game'):        
        with Session(engine) as session:
            # 加入資料庫
            session.add(game)
            session.commit()

    @classmethod 
    def is_game_id_valid(cls, json):
        required_fields = ['game_id']
        return all(field in json for field in required_fields)

    @classmethod 
    def search_by_id(cls, game_id: str) -> 'Game':
        with Session(engine) as session:
            games = session.query(Game).filter(
                and_(
                    Game.id == game_id
                )
            ).all()

        return games[0] if games else None

    @classmethod 
    def is_start_end_time_json_valid(cls, json):
        required_fields = ['start_time', 'end_time']
        if not all(field in json for field in required_fields):
            return False
            
        start_time = datetime.fromisoformat(json['start_time'])
        end_time = datetime.fromisoformat(json['end_time'])    
        if not start_time.tzinfo or not end_time.tzinfo:  
            raise ValueError("Both start_time and end_time must be timezone aware")
        return True

    @classmethod 
    def search_between(cls, start_time: datetime, end_time: datetime):
        with Session(engine) as session:
            games = session.query(Game).filter(
                and_(
                    Game.start_datetime.between(start_time, end_time),
                    Game.cancellation_time == None
                )
            ).all()

        return games

    @classmethod 
    def search_for_invitation(cls, start_time: datetime, end_time: datetime):    
        return Game.search_games(start_time, end_time)

    @classmethod 
    def search_for_invited(cls):    
        return Game.search_games(datetime.now(timezone.utc), datetime.max, has_invited=True)
    
    @classmethod 
    def search_cancelled_to_announce(cls, start_time: datetime, end_time: datetime):    
        return Game.search_games(start_time, end_time, has_invited=True, has_cancelled=True)

    @classmethod 
    def search_games(cls, 
            start_time: datetime, end_time: datetime,
            has_invited: bool = False, 
            has_cancelled: bool = False, 
            has_cancellation_announced: bool = False):   
        
        filters = [
            Game.start_datetime.between(start_time, end_time),
        ]

        if has_invited:
            filters.append(Game.invitation_time != None)
        else:
            filters.append(Game.invitation_time == None)

        if has_cancelled:
            filters.append(Game.cancellation_time != None)
        else:
            filters.append(Game.cancellation_time == None)

        if has_cancellation_announced:
            filters.append(Game.cancellation_announcement_time != None)
        else:
            filters.append(Game.cancellation_announcement_time == None)

        with Session(engine) as session:
            games = session.query(Game).filter(and_(*filters)).order_by(Game.start_datetime).all()
        return games

    @classmethod 
    def is_update_game_time_valid(cls, json):
        required_fields = ['game_id', 'time']
        return all(field in json for field in required_fields)

    @classmethod 
    def update_invitation_time(cls, game_id: int, time: datetime):
        Game.update_time_field(game_id, time, 'invitation_time')
        
    @classmethod 
    def update_cancellation_time(cls, game_id: int, time: datetime):    
        Game.update_time_field(game_id, time, 'cancellation_time')

    @classmethod 
    def update_cancellation_announcement_time(cls, game_id: int, time: datetime):    
        Game.update_time_field(game_id, time, 'cancellation_announcement_time')

    @classmethod
    def update_time_field(cls, game_id: int, time: datetime, field_name: str):
        update_data = {field_name: time}
        
        with Session(engine) as session:
            session.execute(update(Game).where(Game.id == game_id).values(**update_data))
            session.commit()
        
        
    @classmethod
    def get_games_in_this_week_and_month(cls, total_games: list['Game']) -> tuple[list['Game'], list['Game']]:
        this_week_games = []
        this_month_games = []
        aware_now = datetime.now().astimezone()
        midnight_today = datetime.combine(
            datetime.now().date(), datetime.min.time()
        ).replace(tzinfo=aware_now.tzinfo)

        for game in total_games:
            if (
                game.start_datetime > midnight_today
                and game.start_datetime - midnight_today < timedelta(days=7)
            ):
                this_week_games.append(game)
            elif (
                game.start_datetime > midnight_today
                and game.start_datetime - midnight_today < timedelta(days=30)
            ):
                this_month_games.append(game)

        this_week_games.sort(key=lambda x: x.start_datetime)
        this_month_games.sort(key=lambda x: x.start_datetime)

        return this_week_games, this_month_games

