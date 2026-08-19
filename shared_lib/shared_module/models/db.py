import os

import sqlalchemy
from sqlalchemy.engine import URL


def database_url(environ=os.environ):
    portal_data_url = environ.get("PORTAL_DATA_DATABASE_URL")
    if portal_data_url:
        return portal_data_url

    values = {
        "database": environ.get("DSN_DATABASE"),
        "host": environ.get("DSN_HOSTNAME"),
        "port": environ.get("DSN_PORT"),
        "username": environ.get("DSN_UID"),
        "password": environ.get("DSN_PASSWORD"),
    }
    if any(value in (None, "") for value in values.values()):
        raise RuntimeError("Database configuration is incomplete")
    try:
        port = int(values["port"])
    except (TypeError, ValueError):
        raise RuntimeError("Database port is invalid") from None
    return URL.create(
        "postgresql+psycopg2",
        username=values["username"],
        password=values["password"],
        host=values["host"],
        port=port,
        database=values["database"],
    )


def connect_with_connector() -> sqlalchemy.engine.base.Engine:
    return sqlalchemy.create_engine(
        database_url(),
        pool_size=10,
        max_overflow=5,
        pool_timeout=10,
        pool_recycle=1800,
    )


# 配置 SQLAlchemy 引擎
engine = connect_with_connector()
