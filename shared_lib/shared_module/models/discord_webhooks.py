from dataclasses import dataclass, asdict
from typing import ClassVar, List

from sqlalchemy import MetaData, Integer, String, DateTime, Table, ForeignKey, and_, insert, update
from sqlalchemy.orm import relationship, mapped_column, Mapped, Session, DeclarativeBase


from .db import engine
from .base import Base

@dataclass
class DiscordWebhook(Base):
    __tablename__ = 'discord_webhooks'
    __table_args__ = {'schema': 'ntubtob'}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    webhook_identifier: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)

    def __init__(self, webhook_identifier: str, description: int):
        self.webhook_identifier = webhook_identifier
        self.description = description

    @classmethod 
    def from_dict(cls, data_dict: dict) -> 'DiscordWebhook':
        return cls(**data_dict)
    
    @classmethod
    def is_get_json_valid(cls, json: str | None):
        if json is None:
            return False
        return json.isdigit()
    
    def as_dict(self):
        result = asdict(self)
        return result

    @classmethod 
    def search_by_id(cls, id: int) -> str:
        with Session(engine) as session:
            webhooks = session.query(DiscordWebhook).filter(
                and_(
                    DiscordWebhook.id == id
                )
            ).all()
        return webhooks[0].webhook_identifier if webhooks else None
