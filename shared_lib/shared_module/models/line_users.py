from dataclasses import dataclass, asdict
from typing import Optional

from datetime import datetime

from sqlalchemy import MetaData, Integer, String, Boolean, DateTime, Table, ForeignKey, and_, insert, update
from sqlalchemy.orm import relationship, mapped_column, Mapped, Session, joinedload

from .db import engine
from .members import Member
from .game_attendance_replies import GameAttendanceReply
from .base import Base
from ..settings import local_timezone

@dataclass
class LineUser(Base):
    __tablename__ = 'line_users'
    __table_args__ = {'schema': 'ntubtob'}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nickname: Mapped[str] = mapped_column(String)
    line_user_id: Mapped[str] = mapped_column(String)
    member_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('ntubtob.members.id'))
    submit_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    has_replied: Mapped[bool] = mapped_column(Boolean)
    ignored: Mapped[bool] = mapped_column(Boolean)

    # 與 Member 的關聯是在 relationships.py 做定義
    member = relationship("Member", back_populates="line_users")
    attendance_replies = relationship("GameAttendanceReply", back_populates="line_user")

    def __init__(self, nickname: str, line_user_id: int):
        self.nickname = nickname
        self.line_user_id = line_user_id
        self.submit_time = datetime.now(local_timezone)
        self.has_replied = False
        self.ignored = False

    @classmethod 
    def from_dict(cls, data_dict: dict) -> 'LineUser':
        return cls(**data_dict)

    @classmethod
    def is_add_json_valid(cls, json: dict):
        required_fields = ['nickname', 'line_user_id']
        return all(field in json for field in required_fields)
    
    @classmethod
    def is_search_json_valid(cls, json: str | None):
        if json is None:
            return False
        return True
       

    def as_dict(self):
        result = asdict(self)
        # Convert datetime to ISO 8601 format
        key = 'submit_time'
        print(result[key])
        if key in result and isinstance(result[key], datetime):
            result[key] = result[key].isoformat()
        return result
    
    @classmethod
    def add(cls, line_user: 'LineUser'):
        with Session(engine) as session:
            # 加入資料庫
            session.add(line_user)
            session.commit()

    @classmethod 
    def search_by_id(cls, line_user_id: str) -> 'LineUser':
        with Session(engine) as session:
            users = session.query(LineUser).options(joinedload(LineUser.member)).filter(
                and_(
                    LineUser.line_user_id == line_user_id
                )
            ).all()

        return users[0] if users else None
    
    @classmethod 
    def search_all_unknowns(cls) -> list['LineUser']:
        with Session(engine) as session:
            users = session.query(LineUser).filter(
                and_(                    
                    LineUser.member_id == None,
                    LineUser.ignored == False
                )
            ).all()

        return users

    @classmethod 
    def update_member_id(cls, line_user_id: str, new_member_id: str):        
        with Session(engine) as session:
            session.execute(update(LineUser).where(LineUser.line_user_id == line_user_id).values(member_id=new_member_id))
            session.commit()

    @classmethod 
    def update_as_ignored(cls, line_user_id: str):
        with Session(engine) as session:
            session.execute(update(LineUser).where(LineUser.line_user_id == line_user_id).values(ignored=True))
            session.commit()

    def mark_as_first_replied(self):
        with Session(engine) as session:
            session.execute(update(LineUser).where(LineUser.id == self.id).values(has_replied=True))
            session.commit()