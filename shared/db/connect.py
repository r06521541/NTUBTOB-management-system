import os
import sqlalchemy

def get_schema_name():
    return os.environ["DB_NAME"]

def get_db_name():
    return os.environ["DB_TABLE"]

def connect_with_connector() -> sqlalchemy.engine.base.Engine:
    # PostgreSQL 連線字串格式：postgresql://username:password@hostname:port/database_name
    dsn_database = os.environ["DSN_DATABASE"]
    dsn_hostname = os.environ["DSN_HOSTNAME"]
    dsn_port = os.environ["DSN_PORT"]
    dsn_uid = os.environ["DSN_UID"]
    dsn_password = os.environ["DSN_PASSWORD"]

    # 構建 PostgreSQL 連線字串
    connection_string = f"postgresql://{dsn_uid}:{dsn_password}@{dsn_hostname}:{dsn_port}/{dsn_database}"

    # 使用 create_engine 方法建立連線
    engine = sqlalchemy.create_engine(connection_string)

    return engine