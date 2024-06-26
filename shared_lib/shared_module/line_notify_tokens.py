from dataclasses import dataclass, field
from typing import ClassVar, List

from sqlalchemy import MetaData, Table, insert

from .db import connect_with_connector, get_table_name, get_schema_name

# 配置 SQLAlchemy 引擎
engine = connect_with_connector()

# 定義資料表的 metadata
metadata = MetaData()


@dataclass
class LineNotifyToken:
    _required_fields: ClassVar[List[str]] = ["token", "description"]
    table: Table = field(init=False)

    def __post_init__(self):
        # 從資料庫中反射資料表
        self.table = Table(
            get_table_name(), metadata, autoload_with=engine, schema=get_schema_name()
        )

    @classmethod
    def is_get_json_valid(cls, json: str | None):
        if json is None:
            return False
        return json.isdigit()

    @classmethod
    def is_add_json_valid(cls, json: dict):
        return all(field in json for field in cls._required_fields)

    def get_token_by_id(self, id: str):
        # 創建連線
        with engine.connect() as connection:
            # 執行 SELECT 查詢
            select_statement = self.table.select().where(self.table.c.id == id)
            result = connection.execute(select_statement).first()

            return result.token if result else ""

    def insert(self, json):
        # 創建一個插入操作
        insert_statement = insert(self.table).values(
            token=json["token"], description=json["description"]
        )

        # 使用引擎執行插入操作
        with engine.connect() as connection:
            result = connection.execute(insert_statement)
            connection.commit()

        # 檢查插入結果
        if result.rowcount == 1:
            print("成功插入一筆新資料到 line_notify_tokens 資料表")
        else:
            print("插入資料失敗")
