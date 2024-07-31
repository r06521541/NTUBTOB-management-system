from dataclasses import dataclass, asdict
from typing import Optional

from datetime import datetime

from sqlalchemy import MetaData, Integer, String, DateTime, Table, ForeignKey, and_, insert, update
from sqlalchemy.orm import relationship, mapped_column, Mapped, Session, DeclarativeBase

from .db import connect_with_connector, get_table_name, get_schema_name
from .base import Base

# 配置 SQLAlchemy 引擎
engine = connect_with_connector()

@dataclass
class Member(Base):
    __tablename__ = 'members'
    __table_args__ = {'schema': 'ntubtob'}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)

    # 與 LineUser 的關聯是在 relationships.py 做定義
    line_users = relationship("LineUser", back_populates="member")
        
        

