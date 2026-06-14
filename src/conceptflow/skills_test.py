"""Validate shipped SKILL.md files against the Agent Skills spec basics.

Guards our own skills: every SKILL.md must have YAML frontmatter whose
``name`` matches its immediate parent directory and a non-empty
``description``. A mismatch causes SkillsMiddleware to silently drop the skill.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from conceptflow.paths import skills_dir

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

_SKILL_FILES = sorted(skills_dir().glob("*/*/SKILL.md"))


def test_at_least_three_skills_are_shipped() -> None:
    """Assert the package includes the expected baseline skill set."""
    assert len(_SKILL_FILES) >= 3


@pytest.mark.parametrize("skill_md", _SKILL_FILES, ids=lambda p: str(p.parent.name))
def test_skill_frontmatter_is_valid(skill_md: Path) -> None:
    """Assert every shipped skill has valid frontmatter for discovery."""
    content = skill_md.read_text(encoding="utf-8")
    match = _FRONTMATTER.match(content)
    assert match, f"{skill_md} has no YAML frontmatter"

    data = yaml.safe_load(match.group(1))
    assert isinstance(data, dict), f"{skill_md} frontmatter is not a mapping"

    name = str(data.get("name", "")).strip()
    description = str(data.get("description", "")).strip()
    assert name == skill_md.parent.name, (
        f"{skill_md}: name '{name}' must match dir '{skill_md.parent.name}'"
    )
    assert _NAME.match(name), f"{skill_md}: name '{name}' not lowercase-hyphen form"
    assert description, f"{skill_md}: description is required"
