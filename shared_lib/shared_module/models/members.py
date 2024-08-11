from dataclasses import dataclass, asdict
from typing import Optional

from datetime import datetime

from sqlalchemy import MetaData, Integer, String, DateTime, Table, ForeignKey, and_, insert, update
from sqlalchemy.orm import relationship, mapped_column, Mapped, Session, DeclarativeBase

from .db import engine
from .base import Base

@dataclass
class Member(Base):
    __tablename__ = 'members'
    __table_args__ = {'schema': 'ntubtob'}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)

    # 與 LineUser 的關聯是在 relationships.py 做定義
    line_users = relationship("LineUser", back_populates="member")
    # attendance_replies = relationship("GameAttendanceReply", back_populates="member")

    @classmethod 
    def search_by_id(cls, id: str) -> 'Member':
        with Session(engine) as session:
            members = session.query(Member).filter(
                and_(
                    Member.id == id
                )
            ).all()

        return members[0] if members else None
        

