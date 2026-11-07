"""Milvus 向量存储适配器 —— 记忆系统**唯一的生产向量后端**。

为什么是 Milvus
──────────────
向量检索需要服务端能力，而不是进程内的库内索引：

* **先过滤再检索**：`session_id` 作为 partition key，查询带
  `session_id == ...` + layer/fingerprint/tombstone 条件，候选在
  服务端就被限定在会话内，绝不会把别的会话的向量取回本地（§7）；
* 多进程/多端共享同一份索引；
* `delete(expr=...)` 幂等，不需要维护本地 id 映射表；
* layer / fingerprint / valid_until / tombstone 都是可过滤标量字段；
* 持久化由服务端管理，没有"退出时 save 索引"这一步。

硬性约束遵守
────────────
* `pymilvus` **惰性导入**：不下载、不在模块加载时 import，
  缺依赖时 `available=False`，由 factory 抛 `VectorUnavailable`；
* 不在 import 阶段建立连接（否则服务启动会被一个不可达的
  Milvus 卡住），连接延迟到 `ensure_ready()`；
* 所有 expr 字面量过 `safe_literal()` 白名单，杜绝表达式注入；
* 指纹不一致**只告警不重建**。

pymilvus 版本
─────────────
按 2.4+ 的 `MilvusClient` + `CollectionSchema` 编写。
所有客户端调用都包了异常转换：版本差异导致的 TypeError
会变成可解释的 `MilvusUnavailable`，而不是一串 traceback。
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ...logger import logger
from ..domain.layers import MemoryLayer
from .models import VectorStoreConfig, safe_literal


class MilvusUnavailable(RuntimeError):
    """Milvus 不可用（缺依赖 / 连不上 / 版本不兼容）。

    单独一个异常类型，让 factory 能明确地降级而不是把
    所有异常都当成 bug 吞掉。
    """


class MilvusVectorStore:
    """`VectorStore` 端口的 Milvus 实现。"""

    name = "milvus"

    def __init__(self, config: VectorStoreConfig) -> None:
        self.config = config
        self._client: Any = None
        self._lock = threading.RLock()
        self._ready = False
        self._dim = 0
        self._fingerprint = ""
        self._warning: str = ""
        self._stat_writes = 0
        self._stat_deletes = 0

    # ---------- 可用性 ----------

    @property
    def available(self) -> bool:
        try:
            import pymilvus  # type: ignore
            return True
        except Exception:  # noqa: BLE001
            return False

    def _connect(self) -> Any:
        with self._lock:
            if self._client is not None:
                return self._client
            try:
                from pymilvus import MilvusClient # type: ignore
            except Exception as exc:  # noqa: BLE001
                raise MilvusUnavailable(
                    f"pymilvus 未安装或版本不兼容: {type(exc).__name__}"
                ) from exc

            if not self.config.uri:
                raise MilvusUnavailable("未配置 Milvus uri")

            kwargs: Dict[str, Any] = {"uri": self.config.uri}
            if self.config.token:
                kwargs["token"] = self.config.token
            if self.config.db_name:
                kwargs["db_name"] = self.config.db_name
            if self.config.connect_timeout:
                kwargs["timeout"] = float(self.config.connect_timeout)
            try:
                self._client = MilvusClient(**kwargs)
            except Exception as exc:  # noqa: BLE001
                raise MilvusUnavailable(
                    f"Milvus 连接失败: {type(exc).__name__}"
                ) from exc
            return self._client

    # ---------- 建集合 / 校验 ----------

    def _schema(self, dim: int):
        from pymilvus import DataType, FieldSchema, CollectionSchema # type: ignore

        fields = [
            FieldSchema(
                name="memory_id", dtype=DataType.INT64,
                is_primary=True, auto_id=False,
            ),
            FieldSchema(
                name="session_id", dtype=DataType.VARCHAR,
                max_length=128, is_partition_key=True,
            ),
            FieldSchema(name="layer", dtype=DataType.VARCHAR, max_length=32),
            FieldSchema(name="fingerprint", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dim),
            FieldSchema(name="created_at", dtype=DataType.DOUBLE),
            FieldSchema(name="valid_until", dtype=DataType.DOUBLE),
            FieldSchema(name="tombstone", dtype=DataType.BOOL),
        ]
        return CollectionSchema(
            fields=fields,
            description="分层记忆；session_id 为 partition key，先过滤再检索",
            enable_dynamic_field=False,
        )

    def ensure_ready(self, *, dim: int, fingerprint: str) -> None:
        """建集合并校验 dim / fingerprint。

        **不一致只告警不重建**：重建可能耗时很久，自动执行会在启动时
        卡死进程（明确要求把结论交给界面由用户决定）。
        """
        client = self._connect()
        collection = self.config.collection
        try:
            exists = bool(client.has_collection(collection_name=collection))
        except Exception as exc:  # noqa: BLE001
            raise MilvusUnavailable(
                f"检查 collection 失败: {type(exc).__name__}"
            ) from exc

        if not exists:
            try:
                schema = self._schema(int(dim))
                client.create_collection(
                    collection_name=collection,
                    schema=schema,
                    index_params=self._index_params(),
                    consistency_level=self.config.consistency_level,
                )
            except Exception as exc:  # noqa: BLE001
                raise MilvusUnavailable(
                    f"创建 collection 失败: {type(exc).__name__}"
                ) from exc
        else:
            self._check_existing(client, collection, int(dim), str(fingerprint))

        self._dim = int(dim)
        self._fingerprint = str(fingerprint)
        self._ready = True
        logger.info(
            f"[Milvus] collection 就绪: {collection} dim={dim} fp={str(fingerprint)[:16]}"
        )

    def _index_params(self) -> Any:
        try:
            from pymilvus import MilvusClient # type: ignore

            params = MilvusClient.prepare_index_params()
            params.add_index(
                field_name="vector",
                index_type=self.config.index_type,
                metric_type=self.config.metric_type,
                params={"M": 16, "efConstruction": 200},
            )
            return params
        except Exception:  # noqa: BLE001
            return None

    def _check_existing(
        self, client: Any, collection: str, dim: int, fingerprint: str
    ) -> None:
        """校验已有集合的维度与指纹。查不到就告警但不阻断。"""
        try:
            info = client.describe_collection(collection_name=collection)
        except Exception:  # noqa: BLE001
            self._warning = "无法读取已有 collection 描述，维度未校验"
            logger.warning(f"[Milvus] {self._warning}")
            return

        fields = (info or {}).get("fields", []) if isinstance(info, dict) else []
        vector_dim = None
        for field in fields:
            if isinstance(field, dict) and field.get("name") == "vector":
                params = field.get("params") or {}
                raw = params.get("dim", field.get("dim", 0))
                try:
                    vector_dim = int(raw or 0)
                except (TypeError, ValueError):
                    vector_dim = 0
                break
        if vector_dim and vector_dim != dim:
            self._warning = (
                f"维度不符: collection={vector_dim} 当前={dim}；"
                "需人工重建，自动重建已禁用"
            )
            logger.error(f"[Milvus] {self._warning}")

        # 抽样看集合里已有向量用的是哪套 embedding
        try:
            rows = client.query(
                collection_name=collection,
                filter="memory_id >= 0",
                output_fields=["fingerprint"],
                limit=1,
            )
            if rows:
                old = str(rows[0].get("fingerprint", "") or "")
                if old and old != fingerprint:
                    self._warning = (
                        f"embedding 指纹不符: 已有={old[:16]} 当前={fingerprint[:16]}；"
                        "需人工重建，禁止混用"
                    )
                    logger.error(f"[Milvus] {self._warning}")
        except Exception:  # noqa: BLE001
            # query 失败不影响可用性，但维度校验结论仍保留
            pass

    # ---------- 写入 ----------

    def add(
        self,
        memory_ids: Sequence[int],
        vectors: Sequence[Sequence[float]],
        *,
        session_id: str,
        layer: MemoryLayer,
        fingerprint: str,
    ) -> None:
        if not self._ready:
            raise MilvusUnavailable("ensure_ready() 尚未调用")
        if len(memory_ids) != len(vectors):
            raise ValueError("memory_ids 与 vectors 长度不一致")
        if not memory_ids:
            return
        if len(memory_ids) > self.config.max_batch:
            raise ValueError(f"单批超过 {self.config.max_batch} 上限")

        sid = str(session_id)
        safe_literal(sid)          # 白名单校验，注入直接拒绝
        safe_literal(str(fingerprint))
        layer_value = str(getattr(layer, "value", layer))
        safe_literal(layer_value)

        rows = []
        for mid, vec in zip(memory_ids, vectors):
            if len(vec) != self._dim:
                raise ValueError(
                    f"向量维度不匹配: 期望 {self._dim}, 实际 {len(vec)}"
                )
            rows.append({
                "memory_id": int(mid),
                "session_id": sid,
                "layer": layer_value,
                "fingerprint": str(fingerprint),
                "vector": [float(x) for x in vec],
                "created_at": 0.0,
                "valid_until": 0.0,
                "tombstone": False,
            })
        client = self._connect()
        try:
            # upsert 语义：同一 memory_id 重复写入覆盖，不产生重复向量
            client.upsert(collection_name=self.config.collection, data=rows)
        except Exception as exc:  # noqa: BLE001
            raise MilvusUnavailable(f"写入失败: {type(exc).__name__}") from exc
        self._stat_writes += len(rows)

    # ---------- 检索 ----------

    def search(
        self,
        query_vector: Sequence[float],
        *,
        session_id: str,
        layers: Sequence[MemoryLayer],
        top_k: int,
        fingerprint: str,
    ) -> List[Tuple[int, float]]:
        """服务端 scope 过滤 → ANN 检索。

        filter 里同时限定 `session_id` / `layer` / `fingerprint` / `tombstone`，
        所以**返回的每一条都已经在允许范围内**，Python 侧不需要再过滤。
        """
        if not self._ready:
            raise MilvusUnavailable("ensure_ready() 尚未调用")
        if len(query_vector) != self._dim:
            raise ValueError(
                f"查询向量维度不匹配: 期望 {self._dim}, 实际 {len(query_vector)}"
            )
        k = max(1, min(int(top_k), int(self.config.max_top_k)))

        sid = str(session_id)
        fp = str(fingerprint)
        layer_values = [str(getattr(x, "value", x)) for x in (layers or [])]
        for value in [sid, fp, *layer_values]:
            safe_literal(value)

        if not layer_values:
            # 不给层 = 不检索。绝不能退化成"全库检索"
            return []

        in_list = ", ".join(safe_literal(v) for v in layer_values)
        expr = (
            f"session_id == {safe_literal(sid)} "
            f"and fingerprint == {safe_literal(fp)} "
            f"and layer in [{in_list}] "
            f"and tombstone == false"
        )

        client = self._connect()
        try:
            results = client.search(
                collection_name=self.config.collection,
                data=[[float(x) for x in query_vector]],
                filter=expr,
                limit=k,
                output_fields=["memory_id", "layer"],
                search_params={"metric_type": self.config.metric_type},
            )
        except Exception as exc:  # noqa: BLE001
            raise MilvusUnavailable(f"检索失败: {type(exc).__name__}") from exc

        hits: List[Tuple[int, float]] = []
        for group in (results or [])[:1]:
            for hit in group or []:
                entity = (hit.get("entity") or {}) if isinstance(hit, dict) else {}
                mid = entity.get("memory_id", hit.get("id") if isinstance(hit, dict) else None)
                if mid is None:
                    continue
                score = float(hit.get("distance", hit.get("score", 0.0)) or 0.0)
                hits.append((int(mid), score))
        return hits

    # ---------- 删除 ----------

    def remove(self, memory_ids: Sequence[int], *, session_id: str = "") -> None:
        """删除向量。**幂等**：重复调用不报错。

        墓碑协议仍由 SQLite 侧负责（B1-05）；这里只清向量，
        因为恢复快照时重放的是"内容已删"这一事实，不是向量位置。
        """
        if not memory_ids:
            return
        client = self._connect()
        safe_ids: List[str] = []
        for raw_id in memory_ids:
            try:
                safe_ids.append(str(int(raw_id)))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                # 脏 id 跳过而不是让整批删除失败；调用方会看到计数差异
                continue
        if not safe_ids:
            return
        ids = ", ".join(safe_ids)
        expr = f"memory_id in [{ids}]"
        if session_id:
            safe_literal(str(session_id))
            expr += f" and session_id == {safe_literal(str(session_id))}"
        try:
            client.delete(collection_name=self.config.collection, filter=expr)
        except Exception as exc:  # noqa: BLE001
            raise MilvusUnavailable(f"删除失败: {type(exc).__name__}") from exc
        self._stat_deletes += len(memory_ids)

    def list_ids(self, *, session_id: str = "", limit: int = 200_000) -> List[int]:
        """列出集合里的 memory_id（对齐诊断用，B1-04）。

        MilvusClient.query 单页有上限，用 offset 分页；只读主键字段，
        不取向量、不取正文。失败时抛 `MilvusUnavailable` 由调用方标注
        "诊断不完整"，绝不返回空集合假装"没有孤儿"。
        """
        if not self._ready:
            raise MilvusUnavailable("ensure_ready() 尚未调用")
        client = self._connect()
        expr = "memory_id >= 0"
        if session_id:
            expr += f" and session_id == {safe_literal(str(session_id))}"
        out: List[int] = []
        page = 1000
        offset = 0
        while len(out) < int(limit):
            try:
                rows = client.query(
                    collection_name=self.config.collection,
                    filter=expr,
                    output_fields=["memory_id"],
                    limit=min(page, int(limit) - len(out)),
                    offset=offset,
                )
            except Exception as exc:  # noqa: BLE001
                # 老版本不支持 offset：有一页就够做抽样诊断
                if out:
                    break
                raise MilvusUnavailable(
                    f"列举向量 id 失败: {type(exc).__name__}"
                ) from exc
            if not rows:
                break
            for row in rows or []:
                try:
                    out.append(int(row.get("memory_id")))
                except (TypeError, ValueError, AttributeError):
                    continue
            if len(rows) < page:
                break
            offset += len(rows)
        return out

    def flush(self) -> None:
        if self._client is None:
            return
        try:
            self._client.flush(collection_name=self.config.collection)
        except Exception:  # noqa: BLE001
            # 老版本 MilvusClient 可能没有 flush；服务端自身会持久化，
            logger.debug("[Milvus] flush 不可用或已由服务端自动完成")

    def stats(self) -> Dict[str, Any]:
        out: Dict[str, Any] = dict(self.config.as_dict())
        out.update({
            "backend": self.name,
            "available": self.available,
            "ready": self._ready,
            "dim": self._dim,
            "fingerprint": self._fingerprint[:16],
            "warning": self._warning,
            "writes": self._stat_writes,
            "deletes": self._stat_deletes,
        })
        return out
