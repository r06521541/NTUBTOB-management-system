from sqlalchemy import Integer, String, DateTime
from sqlalchemy import update, and_
from sqlalchemy.orm import Session, DeclarativeBase, mapped_column, Mapped
from datetime import datetime, timezone, timedelta
from typing import Optional
from dataclasses import dataclass, asdict

from .db import connect_with_connector, get_table_name, get_schema_name


local_timezone = timezone(timedelta(hours=8))  # 台北時間（UTC+08:00）

# 配置 SQLAlchemy 引擎
engine = connect_with_connector()

class Base(DeclarativeBase):
    pass

@dataclass
class Game(Base):
    __tablename__ = get_table_name()
    __table_args__ = {'schema': get_schema_name()}

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
    
    def as_dict(self):
        result = asdict(self)
        # Convert datetime to ISO 8601 format
        for key in ['start_datetime', 'invitation_time', 'cancellation_time', 'cancellation_announcement_time']:
            if key in result and isinstance(result[key], datetime):
                result[key] = result[key].isoformat()
        return result
        
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
    def add_game(cls, game_json: dict[str, str]):
        # 建立新比賽物件
        new_game = Game(year = game_json['year'], 
                        season = game_json['season'],
                        start_datetime = game_json['start_datetime'],
                        duration = game_json['duration'],
                        location = game_json['location'],
                        home_team = game_json['home_team'],
                        away_team = game_json['away_team'])
        
        with Session(engine) as session:
            # 加入資料庫
            session.add(new_game)
            session.commit()

    @classmethod 
    def is_game_id_valid(cls, json):
        required_fields = ['game_id']
        return all(field in json for field in required_fields)

    @classmethod 
    def search_by_id(cls, game_id: str):
        with Session(engine) as session:
            games = session.query(Game).filter(
                and_(
                    Game.id == game_id
                )
            ).all()

        return games

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
    def search_for_invited(cls, start_time: datetime, end_time: datetime):    
        return Game.search_games(start_time, end_time, has_invited=True)

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
            games = session.query(Game).filter(and_(*filters)).all()
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
        
