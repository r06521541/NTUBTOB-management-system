from sqlalchemy import Integer, String, DateTime, SmallInteger, ForeignKey
from sqlalchemy import update, and_
from sqlalchemy.orm import relationship, mapped_column, Mapped, Session
from datetime import datetime, timezone, timedelta
from typing import Optional
from dataclasses import dataclass, asdict

from .db import engine
from ..settings import (
    local_timezone
)
from .base import Base

@dataclass
class GameAttendanceReply(Base):
    __tablename__ = 'game_attendance_replies'
    __table_args__ = {'schema': 'ntubtob'}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey('ntubtob.games.id'))
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('ntubtob.line_users.id'))
    member_id: Mapped[int] = mapped_column(Integer, ForeignKey('ntubtob.members.id'))
    reply: Mapped[int] = mapped_column(SmallInteger)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    game = relationship("Game")
    user = relationship("LineUser")
    member = relationship("Member")

    def __init__(self, game_id: int, user_id: int, member_id: int, reply: int):
        self.game_id = game_id
        self.user_id = user_id
        self.member_id = member_id
        self.reply = reply
        self.updated_at = datetime.now(local_timezone)

    @classmethod
    def add(cls, reply: 'GameAttendanceReply'):
        with Session(engine) as session:
            # 加入資料庫
            session.add(reply)
            session.commit()

    @classmethod 
    def search_by_member_id(cls, member_id: int) -> list['GameAttendanceReply']:
        with Session(engine) as session:
            results = session.query(GameAttendanceReply).filter(
                and_(
                    GameAttendanceReply.member_id == member_id
                )
            ).all()

        return results

    @classmethod 
    def search_by_game_id(cls, game_id: int) -> list['GameAttendanceReply']:
        with Session(engine) as session:
            results = session.query(GameAttendanceReply).filter(
                and_(
                    GameAttendanceReply.game_id == game_id
                )
            ).all()

        return results
    
    @classmethod 
    def search_single_game_reply_of_member(cls, game_id: int, member_id: int) -> list['GameAttendanceReply']:
        with Session(engine) as session:
            results = session.query(GameAttendanceReply).filter(
                and_(
                    GameAttendanceReply.game_id == game_id,
                    GameAttendanceReply.member_id == member_id
                )
            ).all()

        return results
