"""Skill引擎：发现 + 加载 + 注入。

设计依据: S07, experiments exp12.5。
SKILL.md格式：frontmatter元数据 + 正文prompt。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class SkillMetadata:
    """Skill元数据。"""

    name: str
    version: str
    description: str
    triggers: list[str]
    agents: list[str]
    priority: int = 10
    max_tokens: int = 2000


@dataclass
class SkillContent:
    """Skill完整内容。"""

    metadata: SkillMetadata
    prompt: str


class SkillEngine:
    """Skill引擎。"""

    def __init__(self, skills_dir: str = "skills/"):
        self.skills_dir = Path(skills_dir)
        self.registry: dict[str, SkillContent] = {}
        self._loaded = False

    def discover(self):
        """扫描skills/目录，发现所有可用Skill。"""
        if not self.skills_dir.exists():
            return

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                content = self._parse_skill(skill_md)
                if content:
                    self.registry[content.metadata.name] = content

        self._loaded = True

    def _parse_skill(self, path: Path) -> SkillContent | None:
        """解析SKILL.md文件。"""
        text = path.read_text(encoding="utf-8")

        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                try:
                    meta_dict = yaml.safe_load(parts[1])
                    prompt = parts[2].strip()
                    metadata = SkillMetadata(**meta_dict)
                    return SkillContent(metadata=metadata, prompt=prompt)
                except Exception:
                    return None
        return None

    def get_skill(self, name: str) -> SkillContent | None:
        """获取指定Skill。"""
        if not self._loaded:
            self.discover()
        return self.registry.get(name)

    def get_for_agent(self, agent_name: str) -> list[SkillContent]:
        """获取指定Agent可用的所有Skill。"""
        if not self._loaded:
            self.discover()
        skills = [s for s in self.registry.values() if agent_name in s.metadata.agents]
        return sorted(skills, key=lambda s: s.metadata.priority)

    def activate(self, name: str) -> str | None:
        """激活Skill，返回注入prompt的内容。"""
        skill = self.get_skill(name)
        return skill.prompt if skill else None
