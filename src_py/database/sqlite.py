from __future__ import annotations
import _sqlite3
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional,Tuple, Union

@dataclass
class BatchContext:
    sql: str = ""
    params: List[tuple] = field(default_factory=list)
    batch_size: int = 500  # 每批最大记录数

#单例模式
class AsyncSqlite:
    _instance = None
    def __new__(cls, db:str,):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance.db = db
        return cls._instance
    
    def __init__(self, db:str, batch_size:int=500, max_workers:int=4):
        self.db = db
        self.conn: Optional[_sqlite3.Connection] = None
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.__lock = asyncio.Lock()
        self.default_batch_size = batch_size
    
    async def get_lastrowid(self) -> int:
        if not self.conn:
            return 0
        loop = asyncio.get_event_loop()
        async with self.__lock:
            cursor = await loop.run_in_executor(
                self.executor,
                lambda: self.conn.execute("SELECT last_insert_rowid()") # type: ignore
            )
            row = cursor.fetchone()
            cursor.close()
            return int(row[0]) if row else 0
    
    async def connect(self):
        loop = asyncio.get_event_loop()
        self.conn = await loop.run_in_executor(
            self.executor,
            lambda: _sqlite3.connect(self.db)
        )
        if self.conn:
            self.conn.row_factory = _sqlite3.Row
    
    def select(self,table_name: str):
        if not table_name:
            raise ValueError("Table name is not specified")
        return Query(self, table_name)
    
    def insert(self,table_name: str):
        if not table_name:
            raise ValueError("Table name is not specified")
        return Insert(self, table_name)

    def update(self,table_name: str):
        if not table_name:
            raise ValueError("Table name is not specified")
        return Update(self, table_name)

    def delete(self,table_name: str):
        if not table_name:
            raise ValueError("Table name is not specified")
        return Delete(self, table_name)
    
    async def close(self):
        if self.conn:
            self.conn.close()
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)
        self.__class__._instance = None
            
    def __del__(self):
        if self.conn:
            self.conn.close()
        self._instance = None

    async def __execute(self, sql: str, params: tuple = ()) -> Optional[List[Any]]:
        if not self.conn:
            await self.connect()
            
        loop = asyncio.get_event_loop()
        async with self.__lock:
            try:
                cursor = await loop.run_in_executor(
                    self.executor,
                    lambda: self.conn.execute(sql, params) # type: ignore
                )
                result = cursor.fetchall()
                cursor.close()
                return result
            except Exception as e:
                raise RuntimeError(f"SQLite error: {e}")
    
    async def insert_batch(self, table: str, data: List[Dict[str, Any]]) -> int:
        """批量插入（使用executemany提升性能）"""
        if not data:
            return 0
            
        columns = ",".join(data[0].keys())
        placeholders = ",".join(["?" for _ in data[0]])
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        
        # 提取所有值
        values_list = [tuple(d.values()) for d in data]
        
        loop = asyncio.get_event_loop()
        async with self.__lock:
            cursor = await loop.run_in_executor(
                self.executor,
                lambda: self.conn.executemany(sql, values_list) # type: ignore
            )
            affected = cursor.rowcount
            cursor.close()
            return affected
    
    async def __execute_many(self, sql: str, params_list: List[tuple]) -> int:
        if not self.conn:
            await self.connect()
            
        if not params_list:
            return 0
        loop = asyncio.get_event_loop()
        async with self.__lock:
            try:
                cursor = await loop.run_in_executor(
                    self.executor,
                    lambda: self.conn.executemany(sql, params_list) # type: ignore
                )
                affected = cursor.rowcount
                cursor.close()
                return affected
            except Exception as e:
                raise RuntimeError(f"SQLite batch error: {e}")

    async def execute_sql_file(self, file_path:Union[str,Path],encoding:str="utf-8"):
        with open(file_path, "r", encoding=encoding) as f:
            sql_script = f.read()
            if not self.conn:
                await self.connect()
                
            loop = asyncio.get_event_loop()
            async with self.__lock:
                try:
                    await loop.run_in_executor(
                        self.executor,
                        lambda: self.conn.executescript(sql_script) # type: ignore
                    )
                except Exception as e:
                    raise RuntimeError(f"SQLite script execution error: {e}")


class Query:    
    def __init__(self, db: AsyncSqlite, table_name: str):
        self.db = db
        self.table_name = table_name
        self.__conditions: List[str] = []
        self.__params: List[Any] = []
        self.__limit: Optional[int] = None
        self.__offset: Optional[int] = None
        self.__order_by: List[str] = []
        self.__columns: List[str] = ["*"]
        self.__group_by: List[str] = []
        self.__having: Optional[str] = None
        
    def where(self, conditions: Dict[str, Any]):
        for key, value in conditions.items():
            self.__conditions.append(f"{key} = ?")
            self.__params.append(value)
        return self
    
    def where_raw(self, condition: str, *params: Any):
        self.__conditions.append(condition)
        self.__params.extend(params)
        return self
    
    def where_in(self, column: str, values: List[Any]):
        placeholders = ",".join(["?" for _ in values])
        self.__conditions.append(f"{column} IN ({placeholders})")
        self.__params.extend(values)
        return self
    
    def limit(self, limit: int):
        self._limit = limit
        return self
    
    def offset(self, offset: int):
        self._offset = offset
        return self
    
    def order_by(self, column: str, direction: Literal["ASC","DESC"] = "ASC"):
        self.__order_by.append(f"{column} {direction}")
        return self
    
    def set_fields(self, columns: List[str]):
        self.__columns = columns
        return self
    
    def group_by(self, columns: List[str]):
        self.__group_by = columns
        return self
    
    def having(self, condition: str, *params: Any) :
        self.__having = condition
        self.__params.extend(params)
        return self
    
    def __build_select_sql(self) -> tuple:
        if hasattr(self,"__columns"):
            columns = ",".join(self.__columns)
        else:
            columns = "*"
        sql = f"SELECT {columns} FROM {self.table_name}"
        if self.__conditions:
            sql += " WHERE " + " AND ".join(self.__conditions)
        if self.__group_by:
            sql += " GROUP BY " + ",".join(self.__group_by)
        if self.__having:
            sql += f" HAVING {self.__having}"
        if self.__order_by:
            sql += " ORDER BY " + ",".join(self.__order_by)
        if self.__limit is not None:
            sql += f" LIMIT {self.__limit}"
        if self.__offset is not None:
            sql += f" OFFSET {self.__offset}"
        return sql, tuple(self.__params)
    
    async def query(self) -> Optional[List[Any]]:
        if not self.db.conn:
            raise ValueError("Database connection is not established")
        sql, params = self.__build_select_sql()
        return await self.db.__execute(sql, params)
    
    async def first(self) -> Optional[Any]:
        self.limit(1)
        results = await self.query()
        return results[0] if results else None
    
    async def count(self,alias:str="count") -> int:
        self.set_fields([f"COUNT(*) as {alias}"])
        result = await self.first()
        return result[alias] if result else 0
    
    async def exists(self) -> bool:
        return await self.count() > 0
    
    async def sum(self, column: str) -> Optional[float]:
        self.set_fields([f"SUM({column}) as total"])
        result = await self.first()
        return result["total"] if result else None
    
    async def avg(self, column: str,alias:str="average") -> Optional[float]:
        self.set_fields([f"AVG({column}) as {alias}"])
        result = await self.first()
        return result[alias] if result else None
    
    async def max(self, column: str,alias:str="max_val") -> Optional[Any]:
        self.set_fields([f"MAX({column}) as {alias}"])
        result = await self.first()
        return result[alias] if result else None
    
    async def min(self, column: str,alias:str="min_val") -> Optional[Any]:
        self.set_fields([f"MIN({column}) as {alias}"])
        result = await self.first()
        return result[alias] if result else None
    
    async def paginate(self, page: int, per_page: int = 20) -> Dict[str, Any]:
        total = await self.count()
        total_pages = (total + per_page - 1) // per_page
        
        self.limit(per_page).offset((page - 1) * per_page)
        items = await self.query()
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }


ADDBatch=Union[Dict[str, Any], List[Dict[str, Any]]]

class Insert:
    def __init__(self, db: AsyncSqlite, table_name: str):
        self.db = db
        self.table_name = table_name
        self.__batch_context = BatchContext(batch_size=db.default_batch_size)
        self.__pending_count = 0
        self.__fields: List[str] = []
        self.__single_data: Optional[Union[Dict[str, Any], Tuple[Any, ...]]] = None
        self.__single_sql: str = ""

    def set_fields(self, fields: List[str]):
        self.__fields = fields
        return self    
    
    def add(self, data: Union[Dict[str, Any], Tuple[Any, ...]]):
        if not self.db.conn:
            raise ValueError("Database connection is not established")
        if isinstance(data, dict):
            columns = ",".join(data.keys())
            placeholders = ",".join(["?" for _ in data])
            self.__data= tuple(data.values())
        elif isinstance(data, tuple):
            if not self.__fields:
                raise ValueError("Fields must be set before adding tuple data. Use .set_fields() first.")
            columns = ",".join(self.__fields)
            placeholders = ",".join(["?" for _ in data])
            self.__data= data
        else:
            raise ValueError("Data must be a dictionary or a tuple.")
        self.sql = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"
        return self

    async def save(self) -> int:
        loop = asyncio.get_event_loop()
        async with self.db.__lock:
            cursor = await loop.run_in_executor(
                self.db.executor,
                lambda: self.db.conn.execute(self.sql, self.__data) #type: ignore
            )
            last_id = cursor.lastrowid
            cursor.close()
            return last_id or 0
    
    def add_batch(self, data: Union[Dict[str, Any], List[Any], Tuple[Any, ...]]):
        """添加批量插入数据（链式累积）"""
        if isinstance(data, dict):
            # Dict格式
            if not self.__batch_context.sql:
                self.__columns = list(data.keys())
                columns = ",".join(self.__columns)
                placeholders = ",".join(["?" for _ in self.__columns])
                self.__batch_context.sql = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"
            # 验证字段一致性
            if set(data.keys()) != set(self.__columns):
                raise ValueError(f"All records must have the same fields. Expected: {self.__columns}, Got: {list(data.keys())}")
            self.__batch_context.params.append(tuple(data.values()))
        elif isinstance(data, (list, tuple)):
            # List/Tuple格式
            if not self.__batch_context.sql:
                if not self.__fields:
                    raise ValueError("For tuple/list format, you must specify columns first using .set_fields()")
                columns = ",".join(self.__fields)
                placeholders = ",".join(["?" for _ in self.__fields])
                self.__batch_context.sql = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"
            if len(data) != len(self.__fields):
                raise ValueError(f"Data length mismatch. Expected {len(self.__fields)} values, got {len(data)}")
            self.__batch_context.params.append(tuple(data))
        else:
            raise TypeError(f"Unsupported data type: {type(data)}")
        self.__pending_count += 1
        return self
    
    def batch_size(self, size: int):
        self.__batch_context.batch_size = size
        return self
    
    async def save_batch(self) -> int:
        if not self.__batch_context.params:
            return 0
            
        affected = await self.db.__execute_many(
            self.__batch_context.sql, 
            self.__batch_context.params
        )
        # 重置批量上下文
        self.__batch_context = BatchContext(batch_size=self.db.default_batch_size)
        self.__pending_count = 0
        return affected
    
    @asynccontextmanager
    async def batch_insert(self):
        """批量插入上下文管理器，自动分批提交"""
        batch_params = []
        batch_size = self.__batch_context.batch_size
        sql_template = None
        class BatchCollector:
            def __init__(self, builder):
                self.builder = builder
                
            def add(self, data: Dict[str, Any]):
                nonlocal sql_template
                if sql_template is None:
                    columns = ",".join(data.keys())
                    placeholders = ",".join(["?" for _ in data])
                    sql_template = f"INSERT INTO {self.builder.table_name} ({columns}) VALUES ({placeholders})"
                batch_params.append(tuple(data.values()))    
                # 自动分批提交
                if len(batch_params) >= batch_size:
                    pass                
        collector = BatchCollector(self)
        try:
            yield collector
            # 提交剩余数据
            if batch_params:
                if sql_template is None:
                    raise ValueError("Batch insert context not initialized")
                affected = await self.db.__execute_many(sql_template, batch_params)
                print(f"Batch inserted {affected} records")
        except Exception as e:
            print(f"Batch insert failed: {e}")
            raise

class Update:
    def __init__(self, db: AsyncSqlite, table_name: str):
        self.db = db
        self.table_name = table_name
        self.__data: Dict[str, Any] = {}
        self.__conditions: List[str] = []
        self.__params: List[Any] = []
        self.__batch_updates: List[tuple] = []
        self.__update_fields: List[str] = []
        
    def set(self, data: Dict[str, Any]):
        self.__data.update(data)
        return self
    
    def where(self, conditions: Dict[str, Any]):
        for key, value in conditions.items():
            self.__conditions.append(f"{key} = ?")
            self.__params.append(value)
        return self
    
    def where_in(self, column: str, values: List[Any]):
        """添加IN条件（用于批量更新）"""
        placeholders = ",".join(["?" for _ in values])
        self.__conditions.append(f"{column} IN ({placeholders})")
        self.__params.extend(values)
        return self
    
    async def save(self) -> int:
        if not self.__data:
            raise ValueError("No data to update")
        if not self.db.conn:
            raise ValueError("Database connection is not established")
        set_clause = ",".join([f"{k} = ?" for k in self.__data.keys()])
        sql = f"UPDATE {self.table_name} SET {set_clause}"
        
        all_params = list(self.__data.values())
        
        if self.__conditions:
            sql += " WHERE " + " AND ".join(self.__conditions)
            all_params.extend(self.__params)
            
        loop = asyncio.get_event_loop()
        async with self.db.__lock:
            cursor = await loop.run_in_executor(
                self.db.executor,
                lambda: self.db.conn.execute(sql, tuple(all_params)) #type: ignore
            )
            affected_rows = cursor.rowcount
            cursor.close()
            return affected_rows
    
    def set_fields(self, fields: List[str]):
        self.__update_fields = fields
        return self
        
    def add_batch(self, data: Union[dict, tuple], conditions: Dict[str, Any]):
        if isinstance(data, dict):
            self.__batch_updates.append((data, conditions or {}))
        elif isinstance(data, tuple):
            if hasattr(self, '__update_fields'):
                data_dict = dict(zip(self.__update_fields, data))
                self.__batch_updates.append((data_dict, conditions or {}))
            else:
                raise ValueError("For tuple format, use .set_fields() first")
        return self
    
    async def save_batch(self) -> int:
        if not self.__batch_updates:
            return 0
        total_affected = 0
        for data, conditions in self.__batch_updates:
            set_clause = ",".join([f"{k} = ?" for k in data.keys()])
            where_clause = " AND ".join([f"{k} = ?" for k in conditions.keys()])
            sql = f"UPDATE {self.table_name} SET {set_clause} WHERE {where_clause}"
            params = tuple(list(data.values()) + list(conditions.values()))
            await self.db.__execute(sql, params)
            total_affected += 1
        return total_affected


class Delete:    
    def __init__(self, db: AsyncSqlite, table_name: str):
        self.db = db
        self.table_name = table_name
        self.__conditions: List[str] = []
        self.__params: List[Any] = []
        self.__batch_ids: List[Any] = []
        
    def where(self, conditions: Dict[str, Any]):
        for key, value in conditions.items():
            self.__conditions.append(f"{key} = ?")
            self.__params.append(value)
        return self
    
    def where_in(self, column: str, values: List[Any]):
        placeholders = ",".join(["?" for _ in values])
        self.__conditions.append(f"{column} IN ({placeholders})")
        self.__params.extend(values)
        return self
    
    async def delete(self) -> int:
        if not self.db.conn:
            raise ValueError("Database connection is not established")
        sql = f"DELETE FROM {self.table_name}"
        if self.__conditions:
            sql += " WHERE " + " AND ".join(self.__conditions)
            
        loop = asyncio.get_event_loop()
        async with self.db.__lock:
            cursor = await loop.run_in_executor(
                self.db.executor,
                lambda: self.db.conn.execute(sql, tuple(self.__params)) #type: ignore
            )
            affected_rows = cursor.rowcount
            cursor.close()
            return affected_rows
    
    def add_batch(self, id_value: Any):
        self.__batch_ids.append(id_value)
        return self
    
    async def delete_batch(self) -> int:
        if not self.__batch_ids:
            return 0
        placeholders = ",".join(["?" for _ in self.__batch_ids])
        sql = f"DELETE FROM {self.table_name} WHERE id IN ({placeholders})"
        return await self.db.__execute_many(sql, [(id_,) for id_ in self.__batch_ids])
