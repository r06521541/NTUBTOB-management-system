from dataclasses import dataclass, field
from typing import ClassVar, List

from datetime import datetime

from .db import connect_with_connector, get_table_name, get_schema_name
from sqlalchemy import MetaData, Table, insert, update

# 配置 SQLAlchemy 引擎
engine = connect_with_connector()

# 定義資料表的 metadata
metadata = MetaData()


@dataclass
class LineUser:
    _required_fields: ClassVar[List[str]] = ['nickname', 'line_user_id']
    table: Table = field(init=False)

    def __post_init__(self):
        # 從資料庫中反射資料表
        self.table = Table(
            get_table_name(), metadata, autoload_with=engine, schema=get_schema_name()
        )

    @classmethod
    def is_add_json_valid(cls, json: dict):
        return all(field in json for field in cls._required_fields)
    
    @classmethod
    def is_search_json_valid(cls, json: str | None):
        if json is None:
            return False
        return True
       
    @classmethod
    def as_dict(cls, row):
        row_mapping = dict(row)
        # Convert datetime to ISO 8601 format
        if 'submit_time' in row_mapping and isinstance(row_mapping['submit_time'], datetime):
            row_mapping['submit_time'] = row_mapping['submit_time'].isoformat()

        return row_mapping
    
    def insert(self, json):        
        # 創建一個插入操作
        insert_statement = insert(self.table).values(
            nickname=json["nickname"], line_user_id=json["line_user_id"]
        )
        
        # 使用引擎執行插入操作
        with engine.connect() as connection:
            result = connection.execute(insert_statement)
            connection.commit()
            
        # 檢查插入結果
        if result.rowcount == 1:
            print(f"成功插入一筆新資料到 {get_table_name()} 資料表")
        else:
            print("插入資料失敗")

    def get_user_by_id(self, line_user_id: str):
        # 創建連線
        with engine.connect() as connection:
            # 執行 SELECT 查詢
            select_statement = self.table.select().where(self.table.c.line_user_id == line_user_id)
            row = connection.execute(select_statement).first()
            
            return LineUser.as_dict(row._mapping) if row else ""

    def update_member_id(self, line_user_id: str, new_member_id: str):
        
        update_statement = update(self.table).where(
            self.table.c.line_user_id == line_user_id).values(
            member_id=new_member_id
        )
        
        with engine.connect() as connection:
            connection.execute(update_statement)
            connection.commit()  # 確保更改被提交
        
        

