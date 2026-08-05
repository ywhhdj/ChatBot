from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def write_skill(base: Path, name: str, desc: str, display_name: str = "") -> None:
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    for folder in ("scripts", "references", "assets", "agents"):
        (skill_dir / folder).mkdir(exist_ok=True)
    frontmatter = [
        "---",
        f"name: {name}",
        f"description: {desc}",
    ]
    if display_name:
        frontmatter.append(f"display_name: {display_name}")
    frontmatter.extend(["---", "", "# Workflow", "", "1. test"])
    (skill_dir / "SKILL.md").write_text("\n".join(frontmatter), encoding="utf-8")


async def run_dispatch_case(manager: SkillsManager) -> None:
    matched = await manager.dispatch(None, "please use skill-alpha now")
    assert matched["skills"], "dispatch should return at least one skill"
    assert any(x["name"] == "skill-alpha" for x in matched["skills"]), matched

    fallback = await manager.dispatch(None, "no known skill keyword")
    assert fallback["skills"], "fallback should return enabled skills"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="skill_mgr_test_") as tmpdir:
        root = Path(tmpdir)
        skill_root = root / "skills"
        conf_file = root / "skills.json"

        write_skill(skill_root, "skill-alpha", "alpha skill")
        write_skill(skill_root, "skill-beta", "beta skill", display_name="Beta Display")

        manager = SkillsManager(skill_dir=str(skill_root), conf_file=str(conf_file))
        manager.init()

        all_skills = manager.list_skills()
        assert len(all_skills) == 2, f"expect 2 skills, got {len(all_skills)}"

        alpha = manager.get_skill("skill-alpha")
        assert alpha is not None and alpha["metadata"]["name"] == "skill-alpha"
        assert manager.can_execute("skill-alpha") is True

        changed = manager.set_enabled("skill-beta", False)
        assert changed is True
        assert manager.can_execute("skill-beta") is False
        assert len(manager.list_skills(enabled_only=True)) == 1

        asyncio.run(run_dispatch_case(manager))

        # reload manager to verify config persistence
        manager2 = SkillsManager(skill_dir=str(skill_root), conf_file=str(conf_file))
        manager2.init()
        assert manager2.can_execute("skill-beta") is False

        print("Skill manager test tool passed.")


if __name__ == "__main__":
    main()
