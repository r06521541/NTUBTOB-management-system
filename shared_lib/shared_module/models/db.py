import os

import sqlalchemy

def connect_with_connector() -> sqlalchemy.engine.base.Engine:
    # PostgreSQL 連線字串格式：postgresql://username:password@hostname:port/database_name
    dsn_database = os.environ.get("DSN_DATABASE")
    dsn_hostname = os.environ.get("DSN_HOSTNAME")
    dsn_port = os.environ.get("DSN_PORT")
    dsn_uid = os.environ.get("DSN_UID")
    dsn_password = os.environ.get("DSN_PASSWORD")

    # 構建 PostgreSQL 連線字串
    connection_string = f"postgresql://{dsn_uid}:{dsn_password}@{dsn_hostname}:{dsn_port}/{dsn_database}"

    # 使用 create_engine 方法建立連線
    engine = sqlalchemy.create_engine(connection_string)

    return engine

# 配置 SQLAlchemy 引擎
engine = connect_with_connector()