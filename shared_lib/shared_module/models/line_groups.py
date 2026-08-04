from dataclasses import dataclass, asdict
from typing import Optional

from datetime import datetime

from sqlalchemy import MetaData, Integer, String, Boolean, DateTime, Table, ForeignKey, and_, insert, update
from sqlalchemy.orm import relationship, mapped_column, Mapped, Session, joinedload

from .db import engine
from .base import Base
from ..settings import local_timezone

@dataclass
class LineGroup(Base):
    __tablename__ = 'line_groups'
    __table_args__ = {'schema': 'ntubtob'}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    line_group_id: Mapped[str] = mapped_column(String)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    description: Mapped[str] = mapped_column(String)
    is_broadcast_enabled: Mapped[bool] = mapped_column(Boolean)

    def __init__(self, line_group_id: str, description: str, is_broadcast_enabled: bool):
        self.line_group_id = line_group_id
        self.created_at = datetime.now(local_timezone)
        self.description = description
        self.is_broadcast_enabled = is_broadcast_enabled

    @classmethod 
    def from_dict(cls, data_dict: dict) -> 'LineGroup':
        return cls(**data_dict)

    def as_dict(self):
        result = asdict(self)
        # Convert datetime to ISO 8601 format
        key = 'created_at'
        if key in result and isinstance(result[key], datetime):
            result[key] = result[key].isoformat()
        return result
    
    @classmethod
    def add(cls, line_group: 'LineGroup'):
        with Session(engine) as session:
            # 加入資料庫
            session.add(line_group)
            session.commit()

    @classmethod 
    def search_by_id(cls, line_group_id: str) -> 'LineGroup':
        with Session(engine) as session:
            groups = session.query(LineGroup).filter(
                and_(
                    LineGroup.line_group_id == line_group_id
                )
            ).all()

        return groups[0] if groups else None

    @classmethod 
    def search_groups_to_broadcast(cls) -> list['LineGroup']:
        with Session(engine) as session:
            groups = session.query(LineGroup).filter(
                and_(
                    LineGroup.is_broadcast_enabled == True
                )
            ).all()

        return groups
    
    @classmethod 
    def enable_broadcast_for_group(cls, line_group_id: str):
        if not LineGroup.search_by_id(line_group_id):
            LineGroup.add(LineGroup(line_group_id, '', True))
        else:
            with Session(engine) as session:
                session.execute(update(LineGroup).where(LineGroup.line_group_id == line_group_id).values(is_broadcast_enabled=True))
                session.commit()