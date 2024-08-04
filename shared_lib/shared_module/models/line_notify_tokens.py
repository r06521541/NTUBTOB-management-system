from dataclasses import dataclass, asdict
from typing import ClassVar, List

from sqlalchemy import MetaData, Integer, String, DateTime, Table, ForeignKey, and_, insert, update
from sqlalchemy.orm import relationship, mapped_column, Mapped, Session, DeclarativeBase


from .db import engine
from .base import Base

@dataclass
class LineNotifyToken(Base):
    __tablename__ = 'line_notify_tokens'
    __table_args__ = {'schema': 'ntubtob'}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)

    def __init__(self, token: str, description: int):
        self.token = token
        self.description = description

    @classmethod 
    def from_dict(cls, data_dict: dict) -> 'LineNotifyToken':
        return cls(**data_dict)
    
    @classmethod
    def is_add_json_valid(cls, json: dict):
        required_fields = ["token", "description"]
        return all(field in json for field in required_fields)
    
    @classmethod
    def is_get_json_valid(cls, json: str | None):
        if json is None:
            return False
        return json.isdigit()
    
    def as_dict(self):
        result = asdict(self)
        return result

    @classmethod
    def add(cls, token: 'LineNotifyToken'):
        with Session(engine) as session:
            # 加入資料庫
            session.add(token)
            session.commit()

    @classmethod 
    def search_by_id(cls, id: int) -> str:
        with Session(engine) as session:
            tokens = session.query(LineNotifyToken).filter(
                and_(
                    LineNotifyToken.id == id
                )
            ).all()
        return tokens[0].token if tokens else None
