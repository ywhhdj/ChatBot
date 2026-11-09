"""存档快照（Memento）回归测试 —— B1-01 / B1-02 / B1-03。

对应 GameSaveArchitecture §5（事务阶段）、§6（恢复事务）、§8（revision 生命周期）。

用 `tmp_path` 做真实文件 IO，但不依赖运行中的服务或 RuntimePath。

运行：

    cd src_py && python -m pytest tests/test_save_memento.py -v
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.manager.saves import memento  # noqa: E402
from modules.utils.file import atomic  # noqa: E402


# ─────────────────────────────────────────────────────────────
# 路径安全
# ─────────────────────────────────────────────────────────────


def test_safe_join_rejects_traversal(tmp_path):
    with pytest.raises(ValueError):
        atomic.safe_join(str(tmp_path), "../../etc/passwd")


def test_safe_join_allows_normal_nesting(tmp_path):
    p = atomic.safe_join(str(tmp_path), "slots", "slot_001")
    assert p.startswith(str(tmp_path))


def test_is_within_does_not_match_sibling_prefix(tmp_path):
    root = tmp_path / "saves"
    root.mkdir()
    sibling = tmp_path / "saves-backup"
    sibling.mkdir()
    assert atomic.is_within(str(root), str(root / "a"))
    assert not atomic.is_within(str(root), str(sibling)), (
        "前缀匹配会把 saves-backup 误判为在 saves 内"
    )


# ─────────────────────────────────────────────────────────────
# 原子写
# ─────────────────────────────────────────────────────────────


def test_atomic_write_preserves_original_when_write_fails(tmp_path):
    """写失败时原文件必须原封不动 —— 这是原子性的全部意义。"""
    target = tmp_path / "index.yaml"
    target.write_text("original", encoding="utf-8")

    def _boom(_tmp):
        raise RuntimeError("disk full")

    with pytest.raises(RuntimeError):
        atomic.atomic_write(str(target), _boom)

    assert target.read_text(encoding="utf-8") == "original"
    # 临时文件必须清掉，否则 staging 里会堆满 .part
    assert not [p for p in os.listdir(str(tmp_path)) if p.startswith(".tmp-")]


def test_atomic_write_replaces_content(tmp_path):
    target = tmp_path / "a.json"
    target.write_text("old", encoding="utf-8")
    atomic.atomic_write_text(str(target), "new")
    assert target.read_text(encoding="utf-8") == "new"


def test_canonical_json_is_stable():
    a = atomic.canonical_json_bytes({"b": 1, "a": [1, 2, {"x": None}]})
    b = atomic.canonical_json_bytes({"a": [1, 2, {"x": None}], "b": 1})
    assert a == b, "同内容必须同字节，否则 hash 校验会随机失败"


def test_atomic_write_json_matches_canonical_hash(tmp_path):
    payload = {"z": 1, "a": {"k": "v"}}
    target = tmp_path / "s.json"
    atomic.atomic_write_json(str(target), payload)
    assert atomic.sha256_file(str(target)) == atomic.sha256_bytes(
        atomic.canonical_json_bytes(payload)
    )


# ─────────────────────────────────────────────────────────────
# Manifest 校验（B1-01）
# ─────────────────────────────────────────────────────────────


def _manifest_dict(**over):
    base = {
        "format": memento.FORMAT,
        "schema_version": memento.SCHEMA_VERSION,
        "slot_id": "slot_001",
        "revision": "rev-000001",
        "consistency_level": "checkpoint",
        "status": "committed",
        "sections": {},
    }
    base.update(over)
    return base


def test_valid_manifest_passes():
    m, code, _ = memento.validate_manifest(_manifest_dict())
    assert m is not None and code == memento.RejectCode.OK


def test_unknown_schema_is_rejected_not_guessed():
    """B1-01 验收：未知 schema 安全拒绝。"""
    m, code, msg = memento.validate_manifest(
        _manifest_dict(schema_version=999)
    )
    assert m is None
    assert code == memento.RejectCode.UNSUPPORTED_SCHEMA
    assert "999" in msg


@pytest.mark.parametrize("over,expected", [
    ({"format": "other"}, memento.RejectCode.BAD_FORMAT),
    ({"slot_id": ""}, memento.RejectCode.MISSING_FIELD),
    ({"revision": "not-a-revision"}, memento.RejectCode.BAD_REVISION),
    ({"consistency_level": "ludicrous"}, memento.RejectCode.BAD_LEVEL),
    ({"status": "whatever"}, memento.RejectCode.BAD_STATUS),
])
def test_invalid_fields_are_rejected(over, expected):
    m, code, _ = memento.validate_manifest(_manifest_dict(**over))
    assert m is None and code == expected


def test_too_many_sections_rejected():
    sections = {f"s{i}": {"bytes": 1} for i in range(memento.MAX_SECTIONS + 1)}
    m, code, _ = memento.validate_manifest(_manifest_dict(sections=sections))
    assert m is None and code == memento.RejectCode.TOO_MANY_SECTIONS


def test_oversized_section_rejected():
    sections = {"big": {"bytes": memento.MAX_SECTION_BYTES + 1}}
    m, code, _ = memento.validate_manifest(_manifest_dict(sections=sections))
    assert m is None and code == memento.RejectCode.SECTION_TOO_LARGE


# ─────────────────────────────────────────────────────────────
# 一致性等级的诚实性
# ─────────────────────────────────────────────────────────────


def test_full_level_with_reference_only_is_downgraded():
    """声明 FULL 但只存了路径指针 —— 实际只能是 checkpoint。"""
    m = memento.new_manifest("slot_001", "rev-000001",
                             consistency_level=memento.ConsistencyLevel.FULL)
    m = m.with_sections((
        memento.SectionEntry(name="memory", bytes=10, reference_only=True),
        memento.SectionEntry(name="server_config", bytes=10),
    ))
    assert m.level_is_overstated()
    assert m.effective_level() == memento.ConsistencyLevel.CHECKPOINT


def test_full_level_without_references_stays_full():
    m = memento.new_manifest("slot_001", "rev-000001",
                             consistency_level=memento.ConsistencyLevel.FULL)
    m = m.with_sections((
        memento.SectionEntry(name="server_config", bytes=10),
    ))
    assert not m.level_is_overstated()
    assert m.effective_level() == memento.ConsistencyLevel.FULL


# ─────────────────────────────────────────────────────────────
# 发布（B1-02）
# ─────────────────────────────────────────────────────────────


def _make_staging(root, slot_id, revision, sections=None, level=None):
    """造一个合法 staging 目录，返回 (staging_path, manifest)。"""
    manifest = memento.new_manifest(
        slot_id, revision,
        consistency_level=level or memento.ConsistencyLevel.CHECKPOINT,
    )
    staging = memento.prepare_staging(root, slot_id, manifest.operation_id)
    entries = []
    for name, payload in (sections or {"server_config": {"a": 1}}).items():
        entries.append(memento.write_section(staging, name, payload))
    prepared = manifest.with_sections(tuple(entries))
    atomic.atomic_write_json(memento.manifest_path(staging), prepared.to_dict())
    return staging, prepared


def test_publish_happy_path(tmp_path):
    root = str(tmp_path)
    staging, prepared = _make_staging(root, "slot_001", "rev-000001")

    published, code, msg = memento.publish_revision(
        root, "slot_001", staging, prepared.revision
    )
    assert published is not None, msg
    assert code == memento.RejectCode.OK
    assert published.committed, "发布后状态必须是 committed"

    rev_dir = memento.revision_dir(root, "slot_001", "rev-000001")
    assert os.path.isdir(rev_dir)
    assert os.path.isfile(os.path.join(rev_dir, "manifest.json"))
    assert os.path.isfile(os.path.join(rev_dir, "sections", "server_config.json"))

    current, ccode, _ = memento.read_current(root, "slot_001")
    assert current is not None and current.revision == "rev-000001", ccode


def test_staging_dir_is_gone_after_publish(tmp_path):
    """发布是 rename，staging 不该留在原地被误认为有效 revision。"""
    root = str(tmp_path)
    staging, prepared = _make_staging(root, "slot_001", "rev-000001")
    memento.publish_revision(root, "slot_001", staging, prepared.revision)
    assert not os.path.isdir(staging)


def test_publish_refuses_to_overwrite_existing_revision(tmp_path):
    """committed revision 不得原地编辑（§8）。"""
    root = str(tmp_path)
    staging, prepared = _make_staging(root, "slot_001", "rev-000001")
    memento.publish_revision(root, "slot_001", staging, prepared.revision)

    staging2, prepared2 = _make_staging(root, "slot_001", "rev-000001")
    result, code, _ = memento.publish_revision(
        root, "slot_001", staging2, prepared2.revision
    )
    assert result is None
    assert code == memento.RejectCode.REVISION_EXISTS


def test_failed_publish_leaves_current_untouched(tmp_path):
    """B1-02 核心：故障注入不能损坏旧 current revision。"""
    root = str(tmp_path)
    s1, p1 = _make_staging(root, "slot_001", "rev-000001")
    memento.publish_revision(root, "slot_001", s1, p1.revision)

    # 造第二个 staging，然后破坏它的 section（模拟磁盘写坏）
    s2, p2 = _make_staging(root, "slot_001", "rev-000002")
    bad = os.path.join(s2, "sections", "server_config.json")
    with open(bad, "w", encoding="utf-8") as fh:
        fh.write('{"tampered": true}')

    result, code, _ = memento.publish_revision(
        root, "slot_001", s2, p2.revision
    )
    assert result is None
    assert code in (
        memento.RejectCode.SECTION_HASH_MISMATCH,
        memento.RejectCode.SECTION_MISSING,
    )

    # 旧 current 必须仍是 rev-000001
    current, _, _ = memento.read_current(root, "slot_001")
    assert current is not None and current.revision == "rev-000001"
    # 坏 revision 目录不该被发布出去
    assert not os.path.isdir(memento.revision_dir(root, "slot_001", "rev-000002"))


def test_corrupted_published_revision_is_detected(tmp_path):
    """发布后被改坏的 revision，重读校验必须能发现。"""
    root = str(tmp_path)
    staging, prepared = _make_staging(root, "slot_001", "rev-000001")
    memento.publish_revision(root, "slot_001", staging, prepared.revision)

    target = os.path.join(
        memento.revision_dir(root, "slot_001", "rev-000001"),
        "sections", "server_config.json",
    )
    with open(target, "w", encoding="utf-8") as fh:
        fh.write('{"hacked": true}')

    m, code, _ = memento.read_revision(root, "slot_001", "rev-000001")
    assert m is None
    assert code == memento.RejectCode.SECTION_HASH_MISMATCH


def test_uncommitted_revision_is_not_loadable(tmp_path):
    root = str(tmp_path)
    staging, prepared = _make_staging(root, "slot_001", "rev-000001")
    ok, code, _, _ = memento.verify_revision_dir(staging)
    assert not ok
    assert code == memento.RejectCode.NOT_COMMITTED, (
        "staging 里的 prepared 快照不能被当成有效 revision"
    )


def test_read_current_without_pointer(tmp_path):
    m, code, _ = memento.read_current(str(tmp_path), "slot_404")
    assert m is None and code == memento.RejectCode.NO_CURRENT


# ─────────────────────────────────────────────────────────────
# 恢复预演（B1-03）
# ─────────────────────────────────────────────────────────────


def test_preview_is_safe_for_valid_snapshot(tmp_path):
    root = str(tmp_path)
    staging, prepared = _make_staging(
        root, "slot_001", "rev-000001",
        sections={"server_config": {"a": 1}, "ui": {"theme": "dark"}},
    )
    memento.publish_revision(root, "slot_001", staging, prepared.revision)

    plan = memento.preview_restore(root, "slot_001", "rev-000001")
    assert plan.safe
    assert plan.code == memento.RejectCode.OK
    assert "config" in plan.targets


def test_preview_reports_missing_sections_without_blocking(tmp_path):
    root = str(tmp_path)
    staging, prepared = _make_staging(
        root, "slot_001", "rev-000001", sections={"server_config": {"a": 1}}
    )
    memento.publish_revision(root, "slot_001", staging, prepared.revision)

    plan = memento.preview_restore(root, "slot_001", "rev-000001")
    assert plan.safe
    assert "memory-manifest" in plan.missing
    assert any(a == memento.MigrationAction.SECTION_ABSENT.value
               for _, a in plan.migrations)


def test_preview_blocks_on_future_section_schema(tmp_path):
    """section schema 高于当前 → 不能降级，必须阻断。"""
    root = str(tmp_path)
    manifest = memento.new_manifest("slot_001", "rev-000001")
    staging = memento.prepare_staging(root, "slot_001", manifest.operation_id)
    entry = memento.write_section(staging, "server_config", {"a": 1})
    future = memento.SectionEntry(
        name=entry.name, schema_version=memento.SECTION_SCHEMA_VERSION + 5,
        sha256=entry.sha256, bytes=entry.bytes,
    )
    prepared = manifest.with_sections((future,))
    atomic.atomic_write_json(memento.manifest_path(staging), prepared.to_dict())
    memento.publish_revision(root, "slot_001", staging, prepared.revision)

    plan = memento.preview_restore(root, "slot_001", "rev-000001")
    assert not plan.safe
    assert plan.code == memento.RejectCode.UNSUPPORTED_SCHEMA


def test_preview_blocks_on_corrupted_snapshot(tmp_path):
    root = str(tmp_path)
    staging, prepared = _make_staging(root, "slot_001", "rev-000001")
    memento.publish_revision(root, "slot_001", staging, prepared.revision)

    target = os.path.join(
        memento.revision_dir(root, "slot_001", "rev-000001"),
        "sections", "server_config.json",
    )
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("[]")

    plan = memento.preview_restore(root, "slot_001", "rev-000001")
    assert not plan.safe


def test_preview_rejects_path_escape(tmp_path):
    plan = memento.preview_restore(str(tmp_path), "../../etc", "rev-000001")
    assert not plan.safe
    assert plan.code == memento.RejectCode.PATH_ESCAPE


def test_preview_does_not_modify_anything(tmp_path):
    """预演必须只读 —— 不改运行态是 §6 的硬要求。"""
    root = str(tmp_path)
    staging, prepared = _make_staging(root, "slot_001", "rev-000001")
    memento.publish_revision(root, "slot_001", staging, prepared.revision)

    before = memento.list_revisions(root, "slot_001")
    manifest_bytes = open(
        memento.manifest_path(memento.revision_dir(root, "slot_001", "rev-000001")),
        "rb",
    ).read()

    memento.preview_restore(root, "slot_001", "rev-000001")

    after = memento.list_revisions(root, "slot_001")
    assert before == after
    assert open(
        memento.manifest_path(memento.revision_dir(root, "slot_001", "rev-000001")),
        "rb",
    ).read() == manifest_bytes


def test_list_revisions_survives_broken_entry(tmp_path):
    """一个 revision 坏了，列表页不能整页打不开。"""
    root = str(tmp_path)
    staging, prepared = _make_staging(root, "slot_001", "rev-000001")
    memento.publish_revision(root, "slot_001", staging, prepared.revision)

    broken = memento.revision_dir(root, "slot_001", "rev-000002")
    os.makedirs(os.path.join(broken, "sections"), exist_ok=True)
    with open(memento.manifest_path(broken), "w", encoding="utf-8") as fh:
        fh.write("{not json")

    items = memento.list_revisions(root, "slot_001")
    assert len(items) == 2
    by_rev = {i["revision"]: i for i in items}
    assert by_rev["rev-000001"]["readable"] is True
    assert by_rev["rev-000002"]["readable"] is False
