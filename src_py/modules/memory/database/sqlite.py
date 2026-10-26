"""异步 SQLite 封装
线程模型：所有 DB 操作串行提交到单线程 executor，并用 threading.Lock
保护 sqlite 连接（连接本身不是线程安全的）。
"""

from __future__ import annotations
# 原位于 modules/memory/storage/sqlite.py；按 database.py 的 `from ...database.sqlite` 归位到此处

import asyncio
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union


@dataclass
class BatchContext:
    sql: str = ""
    params: List[tuple] = field(default_factory=list)
    batch_size: int = 500


class AsyncSqlite:
    """SQLite 异步封装（单例，串行执行）。"""

    _instance: Optional["AsyncSqlite"] = None
    _cls_lock = threading.Lock()

    def __new__(cls, db: str = "", *args, **kwargs):
        with cls._cls_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._fresh = True
        return cls._instance

    def __init__(self, db: str = "", batch_size: int = 500, max_workers: int = 1) -> None:
        # C116：初始化守卫。否则每次实例化都会丢掉已有连接并新建线程池
        if not getattr(self, "_fresh", False):
            return
        self._fresh = False

        self.db = db
        self.conn: Optional[sqlite3.Connection] = None
        # C113/C115：单线程 executor + threading.Lock。
        # 串行执行本身就保证了连接安全，锁只是防止其它调用路径并发。
        self.executor = ThreadPoolExecutor(max_workers=max_workers,
                                           thread_name_prefix="SqliteWorker")
        self._lock = threading.RLock()
        self.default_batch_size = batch_size

    # ---------- 连接 ----------

    def _connect_sync(self) -> None:
        with self._lock:
            if self.conn is not None:
                return
            db_path = Path(self.db)
            if db_path.parent and str(db_path.parent) not in ("", "."):
                db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
            self.conn.row_factory = sqlite3.Row

    async def connect(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self.executor, self._connect_sync)

    async def _ensure_conn(self) -> None:
        if self.conn is None:
            await self.connect()

    # ---------- 执行（C113：单下划线，供 Query/Insert 调用） ----------

    async def _execute(self, sql: str, params: tuple = ()) -> Optional[List[Any]]:
        await self._ensure_conn()
        loop = asyncio.get_running_loop()

        def _run() -> List[Any]:
            with self._lock:
                assert self.conn is not None
                cursor = self.conn.execute(sql, params)
                result = cursor.fetchall()
                cursor.close()
                return list(result)

        try:
            return await loop.run_in_executor(self.executor, _run)
        except Exception as exc:
            raise RuntimeError(f"SQLite error: {exc}") from exc

    # 保留旧名，避免外部已有调用断裂
    __execute = _execute

    async def _execute_many(self, sql: str, params_list: List[tuple]) -> int:
        if not params_list:
            return 0
        await self._ensure_conn()
        loop = asyncio.get_running_loop()

        def _run() -> int:
            with self._lock:
                assert self.conn is not None
                cursor = self.conn.executemany(sql, params_list)
                affected = cursor.rowcount
                cursor.close()
                return affected

        try:
            return await loop.run_in_executor(self.executor, _run)
        except Exception as exc:
            raise RuntimeError(f"SQLite batch error: {exc}") from exc

    async def get_lastrowid(self) -> int:
        if self.conn is None:
            return 0
        loop = asyncio.get_running_loop()

        def _run() -> int:
            with self._lock:
                assert self.conn is not None
                cursor = self.conn.execute("SELECT last_insert_rowid()")
                row = cursor.fetchone()
                cursor.close()
                return int(row[0]) if row else 0

        return await loop.run_in_executor(self.executor, _run)

    # ---------- 链式入口 ----------

    def select(self, table_name: str) -> "Query":
        if not table_name:
            raise ValueError("Table name is not specified")
        return Query(self, table_name)

    def insert(self, table_name: str) -> "Insert":
        if not table_name:
            raise ValueError("Table name is not specified")
        return Insert(self, table_name)

    def update(self, table_name: str) -> "Update":
        if not table_name:
            raise ValueError("Table name is not specified")
        return Update(self, table_name)

    def delete(self, table_name: str) -> "Delete":
        if not table_name:
            raise ValueError("Table name is not specified")
        return Delete(self, table_name)

    # ---------- 批量 ----------

    async def insert_batch(self, table: str, data: List[Dict[str, Any]]) -> int:
        if not data:
            return 0
        columns = ",".join(data[0].keys())
        placeholders = ",".join(["?" for _ in data[0]])
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        values_list = [tuple(d.values()) for d in data]
        # C118：先确保连接
        await self._ensure_conn()
        loop = asyncio.get_running_loop()

        def _run() -> int:
            with self._lock:
                assert self.conn is not None
                cursor = self.conn.executemany(sql, values_list)
                affected = cursor.rowcount
                cursor.close()
                return affected

        try:
            return await loop.run_in_executor(self.executor, _run)
        except Exception as exc:
            raise RuntimeError(f"SQLite error: {exc}") from exc

    async def execute_sql_file(self, file_path: Union[str, Path], encoding: str = "utf-8") -> None:
        # C117：同步读文件放到 executor，避免阻塞事件循环
        def _read() -> str:
            with open(file_path, "r", encoding=encoding) as f:
                return f.read()

        script = await asyncio.get_running_loop().run_in_executor(self.executor, _read)
        await self._ensure_conn()
        loop = asyncio.get_running_loop()

        def _run() -> None:
            with self._lock:
                assert self.conn is not None
                self.conn.executescript(script)

        try:
            await loop.run_in_executor(self.executor, _run)
        except Exception as exc:
            raise RuntimeError(f"SQLite script execution error: {exc}") from exc

    # ---------- 关闭（C119） ----------

    async def close(self) -> None:
        if self.conn is not None:
            conn = self.conn
            self.conn = None
            try:
                await asyncio.get_running_loop().run_in_executor(
                    self.executor, lambda: conn.close()
                )
            except Exception:
                pass
        try:
            self.executor.shutdown(wait=False)
        except Exception:
            pass
        # C119：清真正的类属性，而不是实例属性
        AsyncSqlite._instance = None
        self._fresh = True

    def __del__(self):  # pragma: no cover
        try:
            if self.conn is not None:
                self.conn.close()
        except Exception:
            pass


# Query / Insert / Update / Delete 共用的锁访问入口
def _db_lock(db: AsyncSqlite):
    return db._lock  # noqa: SLF001 —— 同模块内访问，避免 name mangling


class Query:
    def __init__(self, db: AsyncSqlite, table_name: str) -> None:
        self.db = db
        self.table_name = table_name
        # C114：统一用单下划线，读写一致
        self._conditions: List[str] = []
        self._params: List[Any] = []
        self._limit: Optional[int] = None
        self._offset: Optional[int] = None
        self._order_by: List[str] = []
        self._columns: List[str] = ["*"]
        self._group_by: List[str] = []
        self._having: Optional[str] = None

    def where(self, conditions: Dict[str, Any]) -> "Query":
        for key, value in conditions.items():
            self._conditions.append(f"{key} = ?")
            self._params.append(value)
        return self

    def where_raw(self, condition: str, *params: Any) -> "Query":
        self._conditions.append(condition)
        self._params.extend(params)
        return self

    def where_in(self, column: str, values: List[Any]) -> "Query":
        if not values:
            # 空 IN 集合：用恒假条件，避免生成 `IN ()` 语法错误
            self._conditions.append("1 = 0")
            return self
        placeholders = ",".join(["?" for _ in values])
        self._conditions.append(f"{column} IN ({placeholders})")
        self._params.extend(values)
        return self

    def limit(self, limit: int) -> "Query":
        self._limit = limit
        return self

    def offset(self, offset: int) -> "Query":
        self._offset = offset
        return self

    def order_by(self, column: str, direction: Literal["ASC", "DESC"] = "ASC") -> "Query":
        self._order_by.append(f"{column} {direction}")
        return self

    def set_fields(self, columns: List[str]) -> "Query":
        self._columns = columns
        return self

    def group_by(self, columns: List[str]) -> "Query":
        self._group_by = columns
        return self

    def having(self, condition: str, *params: Any) -> "Query":
        self._having = condition
        self._params.extend(params)
        return self

    def _build_select_sql(self) -> Tuple[str, tuple]:
        columns = ",".join(self._columns) if self._columns else "*"
        sql = f"SELECT {columns} FROM {self.table_name}"
        if self._conditions:
            sql += " WHERE " + " AND ".join(self._conditions)
        if self._group_by:
            sql += " GROUP BY " + ",".join(self._group_by)
        if self._having:
            sql += f" HAVING {self._having}"
        if self._order_by:
            sql += " ORDER BY " + ",".join(self._order_by)
        # C114：limit / offset 现在真的会拼进 SQL
        if self._limit is not None:
            sql += f" LIMIT {int(self._limit)}"
        if self._offset is not None:
            sql += f" OFFSET {int(self._offset)}"
        return sql, tuple(self._params)

    async def query(self) -> Optional[List[Any]]:
        if self.db.conn is None:
            raise ValueError("Database connection is not established")
        sql, params = self._build_select_sql()
        return await self.db._execute(sql, params)

    async def first(self) -> Optional[Any]:
        self.limit(1)
        results = await self.query()
        return results[0] if results else None

    async def count(self, alias: str = "count") -> int:
        # 不要在已设置字段上覆盖（count 可能与其他聚合连用）
        self._columns = [f"COUNT(*) as {alias}"]
        result = await self.first()
        if result is None:
            return 0
        try:
            return int(result[alias])
        except Exception:
            return int(result[0])

    async def exists(self) -> bool:
        return await self.count() > 0

    async def sum(self, column: str) -> Optional[float]:
        self._columns = [f"SUM({column}) as total"]
        result = await self.first()
        return result["total"] if result else None

    async def avg(self, column: str, alias: str = "average") -> Optional[float]:
        self._columns = [f"AVG({column}) as {alias}"]
        result = await self.first()
        return result[alias] if result else None

    async def max(self, column: str, alias: str = "max_val") -> Optional[Any]:
        self._columns = [f"MAX({column}) as {alias}"]
        result = await self.first()
        return result[alias] if result else None

    async def min(self, column: str, alias: str = "min_val") -> Optional[Any]:
        self._columns = [f"MIN({column}) as {alias}"]
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
            "has_prev": page > 1,
        }


AddBatch = Union[Dict[str, Any], List[Dict[str, Any]]]


class Insert:
    def __init__(self, db: AsyncSqlite, table_name: str) -> None:
        self.db = db
        self.table_name = table_name
        self._batch_context = BatchContext(batch_size=db.default_batch_size)
        self._pending_count = 0
        self._fields: List[str] = []
        self._data: Optional[tuple] = None
        self.sql: str = ""

    def set_fields(self, fields: List[str]) -> "Insert":
        self._fields = fields
        return self

    def add(self, data: Union[Dict[str, Any], Tuple[Any, ...]]) -> "Insert":
        if self.db.conn is None:
            raise ValueError("Database connection is not established")
        if isinstance(data, dict):
            columns = ",".join(data.keys())
            placeholders = ",".join(["?" for _ in data])
            self._data = tuple(data.values())
        elif isinstance(data, tuple):
            if not self._fields:
                raise ValueError("Fields must be set before adding tuple data. Use .set_fields() first.")
            columns = ",".join(self._fields)
            placeholders = ",".join(["?" for _ in data])
            self._data = data
        else:
            raise ValueError("Data must be a dictionary or a tuple.")
        self.sql = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"
        return self

    async def save(self) -> int:
        if self.db.conn is None:
            raise ValueError("Database connection is not established")
        loop = asyncio.get_running_loop()

        def _run() -> int:
            with _db_lock(self.db):
                assert self.db.conn is not None
                cursor = self.db.conn.execute(self.sql, self._data or ())
                last_id = cursor.lastrowid
                cursor.close()
                return last_id or 0

        return await loop.run_in_executor(self.db.executor, _run)

    def add_batch(self, data: Union[Dict[str, Any], List[Any], Tuple[Any, ...]]) -> "Insert":
        if isinstance(data, dict):
            if not self._batch_context.sql:
                columns = list(data.keys())
                self._columns = columns
                placeholders = ",".join(["?" for _ in columns])
                self._batch_context.sql = (
                    f"INSERT INTO {self.table_name} "
                    f"({','.join(columns)}) VALUES ({placeholders})"
                )
            if set(data.keys()) != set(self._columns):
                raise ValueError(
                    f"All records must have the same fields. "
                    f"Expected: {self._columns}, Got: {list(data.keys())}"
                )
            self._batch_context.params.append(tuple(data.values()))
        elif isinstance(data, (list, tuple)):
            if not self._batch_context.sql:
                if not self._fields:
                    raise ValueError(
                        "For tuple/list format, you must specify columns first using .set_fields()"
                    )
                columns = ",".join(self._fields)
                placeholders = ",".join(["?" for _ in self._fields])
                self._batch_context.sql = (
                    f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"
                )
            if len(data) != len(self._fields):
                raise ValueError(
                    f"Data length mismatch. Expected {len(self._fields)} values, got {len(data)}"
                )
            self._batch_context.params.append(tuple(data))
        else:
            raise TypeError(f"Unsupported data type: {type(data)}")
        self._pending_count += 1
        return self

    def batch_size(self, size: int) -> "Insert":
        self._batch_context.batch_size = size
        return self

    async def save_batch(self) -> int:
        """真正执行批量插入（原实现只有累积没有落盘入口）。"""
        if not self._batch_context.params:
            return 0
        affected = await self.db._execute_many(
            self._batch_context.sql, self._batch_context.params
        )
        self._batch_context.params.clear()
        self._pending_count = 0
        return affected


class Update:
    """极简 Update 构造器（原实现缺失）。"""

    def __init__(self, db: AsyncSqlite, table_name: str) -> None:
        self.db = db
        self.table_name = table_name
        self._sets: List[str] = []
        self._params: List[Any] = []
        self._conditions: List[str] = []

    def set(self, values: Dict[str, Any]) -> "Update":
        for key, value in values.items():
            self._sets.append(f"{key} = ?")
            self._params.append(value)
        return self

    def where(self, conditions: Dict[str, Any]) -> "Update":
        for key, value in conditions.items():
            self._conditions.append(f"{key} = ?")
            self._params.append(value)
        return self

    def where_in(self, column: str, values) -> "Update":
        vals = list(values)
        if not vals:
            # 空集合：用恒假条件，避免误更新全表
            self._conditions.append("1 = 0")
            return self
        placeholders = ",".join(["?" for _ in vals])
        self._conditions.append(f"{column} IN ({placeholders})")
        self._params.extend(vals)
        return self

    def where_raw(self, condition: str, *params: Any) -> "Update":
        self._conditions.append(condition)
        self._params.extend(params)
        return self

    async def execute(self) -> int:
        if not self._sets:
            raise ValueError("No fields to update")
        sql = f"UPDATE {self.table_name} SET {', '.join(self._sets)}"
        if self._conditions:
            sql += " WHERE " + " AND ".join(self._conditions)
        loop = asyncio.get_running_loop()

        def _run() -> int:
            with _db_lock(self.db):
                assert self.db.conn is not None
                cursor = self.db.conn.execute(sql, tuple(self._params))
                affected = cursor.rowcount
                cursor.close()
                return affected

        return await loop.run_in_executor(self.db.executor, _run)


class Delete:
    """极简 Delete 构造器"""

    def __init__(self, db: AsyncSqlite, table_name: str) -> None:
        self.db = db
        self.table_name = table_name
        self._conditions: List[str] = []
        self._params: List[Any] = []

    def where(self, conditions: Dict[str, Any]) -> "Delete":
        for key, value in conditions.items():
            self._conditions.append(f"{key} = ?")
            self._params.append(value)
        return self

    def where_in(self, column: str, values) -> "Delete":
        vals = list(values)
        if not vals:
            # 空集合：用恒假条件，避免误删全表
            self._conditions.append("1 = 0")
            return self
        placeholders = ",".join(["?" for _ in vals])
        self._conditions.append(f"{column} IN ({placeholders})")
        self._params.extend(vals)
        return self

    def where_raw(self, condition: str, *params: Any) -> "Delete":
        self._conditions.append(condition)
        self._params.extend(params)
        return self

    async def execute(self) -> int:
        sql = f"DELETE FROM {self.table_name}"
        if self._conditions:
            sql += " WHERE " + " AND ".join(self._conditions)
        loop = asyncio.get_running_loop()

        def _run() -> int:
            with _db_lock(self.db):
                assert self.db.conn is not None
                cursor = self.db.conn.execute(sql, tuple(self._params))
                affected = cursor.rowcount
                cursor.close()
                return affected

        return await loop.run_in_executor(self.db.executor, _run)
