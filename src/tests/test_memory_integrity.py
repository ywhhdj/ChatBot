"""记忆索引完整性回归测试 —— B1-04 / B1-05 / B1-06。

对应 SecurityAndAuditDesign §7（删除需覆盖 metadata、FAISS、压缩引用、
缓存与快照恢复）、MemoryDesign 相关要求。

只用标准库：`memory/integrity.py` 是纯函数模块，
不 import faiss / numpy / sqlite，因此本测试无需这些依赖。

运行：

    cd src_py && python -m pytest tests/test_memory_integrity.py -v
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.memory.integrity import (  # noqa: E402
    UNKNOWN_DIGEST,
    CompressedVerdict,
    DeleteReason,
    EmbeddingFingerprint,
    IndexHealth,
    Issue,
    RebuildPlan,
    Tombstone,
    analyze_alignment,
    assess_compressed,
    cache_key,
    compatible,
    content_digest,
    filter_compressed,
    filter_resurrected,
    parse_original_ids,
    plan_rebuild,
    purge_before,
    tombstone_for,
)


# ─────────────────────────────────────────────────────────────
# 内容摘要
# ─────────────────────────────────────────────────────────────


def test_digest_is_stable_and_one_way():
    d = content_digest("你好")
    assert d == content_digest("你好")
    assert d != content_digest("你好吗")
    assert "你好" not in d, "摘要里不能出现正文"


def test_empty_content_digest_is_well_defined():
    assert content_digest("") == content_digest("")


# ─────────────────────────────────────────────────────────────
# 墓碑匹配
# ─────────────────────────────────────────────────────────────


def test_tombstone_matches_same_id_and_content():
    t = tombstone_for(42, "秘密内容")
    assert t.matches(42, content_digest("秘密内容"))


def test_tombstone_does_not_match_different_id():
    t = tombstone_for(42, "秘密内容")
    assert not t.matches(43, content_digest("秘密内容"))


def test_tombstone_does_not_kill_reused_id_with_new_content():
    """核心陷阱：快照恢复后 id 可能被新记忆复用。

    只按 id 匹配会误杀一条完全不同的新记忆。
    """
    t = tombstone_for(42, "已删除的旧内容")
    assert not t.matches(42, content_digest("全新的内容")), (
        "id 相同但内容不同 = 另一条记忆，不能被墓碑命中"
    )


def test_unknown_digest_falls_back_to_id_match():
    """墓碑没记下原文时退化为弱匹配——宁可多挡也不能让内容复活。"""
    t = Tombstone(memory_id=42, digest=UNKNOWN_DIGEST)
    assert t.matches(42, content_digest("任意内容"))


def test_filter_resurrected_removes_hits():
    rows = [
        {"id": 1, "content": "保留"},
        {"id": 42, "content": "秘密内容"},
    ]
    marks = [tombstone_for(42, "秘密内容")]
    out = filter_resurrected(rows, marks)
    assert [r["id"] for r in out] == [1]


def test_filter_resurrected_keeps_reused_id():
    rows = [{"id": 42, "content": "全新的内容"}]
    marks = [tombstone_for(42, "已删除的旧内容")]
    assert len(filter_resurrected(rows, marks)) == 1


def test_filter_resurrected_without_tombstones_is_identity():
    rows = [{"id": 1, "content": "a"}, {"id": 2, "content": "b"}]
    assert len(filter_resurrected(rows, [])) == 2


def test_tombstone_roundtrip():
    t = tombstone_for(7, "x", session_id="s1", reason=DeleteReason.POLICY, deleted_at=1.5)
    back = Tombstone.from_dict(t.to_dict())
    assert back == t


def test_tombstone_rejects_bad_dict():
    assert Tombstone.from_dict(None) is None
    assert Tombstone.from_dict({"memory_id": "abc"}) is None
    assert Tombstone.from_dict({}) is None


def test_purge_keeps_recent_only():
    marks = [
        Tombstone(1, deleted_at=100.0),
        Tombstone(2, deleted_at=10.0),
    ]
    kept = purge_before(marks, cutoff_ts=50.0)
    assert [t.memory_id for t in kept] == [1]


# ─────────────────────────────────────────────────────────────
# 压缩引用
# ─────────────────────────────────────────────────────────────


def test_parse_original_ids_json_and_csv():
    assert parse_original_ids("[1,2,3]") == [1, 2, 3]
    assert parse_original_ids("1,2,3") == [1, 2, 3]
    assert parse_original_ids("") == []
    assert parse_original_ids(None) == []


def test_parse_original_ids_unparseable_is_not_empty():
    """解析不了必须返回 None（不可信），不能被当成"没有引用"从而放行。"""
    assert parse_original_ids("not-a-list") is None
    assert parse_original_ids("{{") is None


def test_compressed_clean_when_no_overlap():
    v = assess_compressed({"id": "c1", "original_ids": "[1,2]"}, {99})
    assert v.verdict == CompressedVerdict.CLEAN
    assert v.injectable


def test_compressed_dead_when_all_originals_deleted():
    v = assess_compressed({"id": "c1", "original_ids": "[1,2]"}, {1, 2})
    assert v.verdict == CompressedVerdict.DEAD
    assert not v.injectable


def test_compressed_partial_excluded_by_default():
    """部分原始记忆被删 → 摘要可能仍含被删内容，默认排除。

    这是保守默认：压缩摘要无法只切掉其中一段。
    """
    v = assess_compressed({"id": "c1", "original_ids": "[1,2,3]"}, {2})
    assert v.verdict == CompressedVerdict.PARTIAL
    assert not v.injectable
    assert v.removed == (2,)
    assert v.surviving == (1, 3)


def test_compressed_partial_can_be_opted_in():
    v = assess_compressed(
        {"id": "c1", "original_ids": "[1,2,3]"}, {2}, on_partial="keep"
    )
    assert v.injectable


def test_compressed_unparseable_is_blocked():
    v = assess_compressed({"id": "c1", "original_ids": "garbage"}, set())
    assert v.verdict == CompressedVerdict.UNPARSEABLE
    assert not v.injectable


def test_filter_compressed_returns_kept_and_verdicts():
    rows = [
        {"id": "keep", "original_ids": "[1]"},
        {"id": "drop", "original_ids": "[2]"},
    ]
    kept, verdicts = filter_compressed(rows, {2})
    assert [r["id"] for r in kept] == ["keep"]
    assert len(verdicts) == 2


# ─────────────────────────────────────────────────────────────
# Embedding 版本化（B1-06）
# ─────────────────────────────────────────────────────────────


def test_identical_fingerprints_are_compatible():
    a = EmbeddingFingerprint("openai", "m1", 384)
    b = EmbeddingFingerprint("openai", "m1", 384)
    assert compatible(a, b)
    assert a.digest() == b.digest()


def test_dim_change_is_incompatible():
    a = EmbeddingFingerprint("openai", "m1", 384)
    b = EmbeddingFingerprint("openai", "m1", 768)
    assert not compatible(a, b)


def test_same_dim_different_model_is_incompatible():
    """同维度不同模型也不能混用——向量空间不同。"""
    a = EmbeddingFingerprint("openai", "m1", 384)
    b = EmbeddingFingerprint("openai", "m2", 384)
    assert not compatible(a, b)
    assert a.digest() != b.digest()


def test_unknown_fingerprint_is_incompatible_with_everything():
    """空指纹 = 不知道这批向量怎么来的，与任何东西混用都不安全。"""
    a = EmbeddingFingerprint("openai", "m1", 384)
    assert not compatible(None, a)
    assert not compatible(a, None)
    assert not compatible(None, None)


def test_plan_rebuild_not_required_when_matching():
    fp = EmbeddingFingerprint("openai", "m1", 384)
    plan = plan_rebuild(fp, EmbeddingFingerprint("openai", "m1", 384))
    assert not plan.required


def test_plan_rebuild_required_when_no_record():
    """索引没记过指纹 → 来源不可确认，要求重建。"""
    plan = plan_rebuild(None, EmbeddingFingerprint("openai", "m1", 384))
    assert plan.required
    assert "指纹" in plan.reason


def test_plan_rebuild_dim_change_blocks_background():
    """维度变了，旧索引无法继续服务，不能后台慢慢重建。"""
    plan = plan_rebuild(
        EmbeddingFingerprint("openai", "m1", 384),
        EmbeddingFingerprint("openai", "m1", 768),
    )
    assert plan.required
    assert plan.background_ok is False
    assert "维度" in plan.reason


def test_plan_rebuild_model_change_allows_background():
    plan = plan_rebuild(
        EmbeddingFingerprint("openai", "m1", 384),
        EmbeddingFingerprint("openai", "m2", 384),
    )
    assert plan.required
    assert plan.background_ok is True


def test_fingerprint_roundtrip():
    fp = EmbeddingFingerprint("p", "m", 512, "2")
    assert EmbeddingFingerprint.from_dict(fp.to_dict()) == fp


def test_cache_key_includes_all_dimensions():
    """缺任一项都会造成跨会话或跨版本串味（ContextArchitecture §8）。"""
    fp = EmbeddingFingerprint("openai", "m1", 384)
    k1 = cache_key("s1", "查询", fp, memory_revision="r1")
    k2 = cache_key("s2", "查询", fp, memory_revision="r1")
    k3 = cache_key("s1", "查询", fp, memory_revision="r2")
    k4 = cache_key("s1", "查询", EmbeddingFingerprint("openai", "m2", 384),
                   memory_revision="r1")
    assert len({k1, k2, k3, k4}) == 4


# ─────────────────────────────────────────────────────────────
# 索引对齐诊断（B1-04）
# ─────────────────────────────────────────────────────────────


def test_healthy_when_everything_aligned():
    health = analyze_alignment(
        memory_ids=[1, 2, 3],
        mapped_memory_ids=[1, 2, 3],
        mapped_faiss_ids=[10, 11, 12],
        index_faiss_ids=[10, 11, 12],
        index_dim=384, expected_dim=384,
    )
    assert health.healthy
    assert not health.findings


def test_orphan_metadata_detected():
    """有记忆无向量 → 永远检索不到。"""
    health = analyze_alignment(
        memory_ids=[1, 2], mapped_memory_ids=[1],
        mapped_faiss_ids=[10], index_faiss_ids=[10],
    )
    assert not health.healthy
    assert health.counts_by_issue()[Issue.ORPHAN_METADATA.value] == 1


def test_lost_mapping_detected():
    """映射指向不存在的记忆 → 悬空。"""
    health = analyze_alignment(
        memory_ids=[1], mapped_memory_ids=[1, 99],
        mapped_faiss_ids=[10, 11], index_faiss_ids=[10, 11],
    )
    assert health.counts_by_issue()[Issue.LOST_MAPPING.value] == 1


def test_orphan_vector_detected():
    """索引里的向量没有映射 → 白占 top_k 名额，拖垮召回。"""
    health = analyze_alignment(
        memory_ids=[1], mapped_memory_ids=[1],
        mapped_faiss_ids=[10], index_faiss_ids=[10, 77, 78],
    )
    assert health.counts_by_issue()[Issue.ORPHAN_VECTOR.value] == 2


def test_dim_mismatch_recommends_rebuild():
    health = analyze_alignment(
        memory_ids=[1], mapped_memory_ids=[1],
        mapped_faiss_ids=[10], index_faiss_ids=[10],
        index_dim=384, expected_dim=768,
    )
    assert health.counts_by_issue()[Issue.DIM_MISMATCH.value] == 1
    assert health.rebuild_recommended


def test_dim_zero_skips_dim_check():
    """拿不到维度时不该误报——未知 ≠ 不匹配。"""
    health = analyze_alignment(
        memory_ids=[1], mapped_memory_ids=[1],
        mapped_faiss_ids=[10], index_faiss_ids=[10],
        index_dim=0, expected_dim=384,
    )
    assert health.healthy


def test_samples_are_limited():
    """诊断报告进日志，不能把整库 id 灌进去。"""
    ids = list(range(1000))
    health = analyze_alignment(
        memory_ids=ids, mapped_memory_ids=[],
        mapped_faiss_ids=[], index_faiss_ids=[],
    )
    finding = next(f for f in health.findings if f.issue == Issue.ORPHAN_METADATA)
    assert len(finding.samples) <= 5


def test_empty_everything_is_healthy():
    health = analyze_alignment(
        memory_ids=[], mapped_memory_ids=[],
        mapped_faiss_ids=[], index_faiss_ids=[],
    )
    assert health.healthy


def test_health_as_dict_is_serializable():
    health = analyze_alignment(
        memory_ids=[1, 2], mapped_memory_ids=[1],
        mapped_faiss_ids=[10], index_faiss_ids=[10],
    )
    payload = health.as_dict()
    assert payload["healthy"] is False
    assert isinstance(payload["findings"], list)
