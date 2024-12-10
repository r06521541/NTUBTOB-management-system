from dataclasses import dataclass, asdict
from typing import Optional

from datetime import datetime

from sqlalchemy import MetaData, Integer, String, DateTime, Table, ForeignKey, and_, insert, update
from sqlalchemy.orm import relationship, mapped_column, Mapped, Session, DeclarativeBase

from .db import engine
from .base import Base

@dataclass
class Ballpark(Base):
    __tablename__ = 'ballparks'
    __table_args__ = {'schema': 'ntubtob'}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    city_name: Mapped[str] = mapped_column(String)
    city_weather_code: Mapped[str] = mapped_column(String)
    district_name: Mapped[str] = mapped_column(String)

    @classmethod 
    def search_by_name(cls, name: str) -> 'Ballpark':
        with Session(engine) as session:
            members = session.query(Ballpark).filter(
                and_(
                    Ballpark.name == name
                )
            ).all()

        return members[0] if members else None

