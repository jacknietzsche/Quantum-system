"""
技能引擎 - 加载SKILL.md + 引用文件的知识注入系统
支持: buffett-skills / munger-skill / taleb-skill / china-stock-research-skills / a-share-skill 等
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shared.logging import log_exception

SKILL_SEARCH_ROOTS = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "quant-agents"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "quant-agents"),
    os.path.expanduser("~/.config/opencode/skills"),
]


@dataclass
class SkillRef:
    """单个引用文件"""

    path: str
    content: str = ""
    section: str = ""


@dataclass
class SkillMeta:
    """技能元数据"""

    name: str
    description: str
    category: str = "general"  # value/risk/analysis/quant/data/trading
    triggers: list[str] = field(default_factory=list)
    source_project: str = ""
    skill_dir: str = ""
    references: list[SkillRef] = field(default_factory=list)
    main_content: str = ""
    output_template: str = ""
    language: str = "zh"


class SkillEngine:
    """技能引擎 - 发现,加载,查询,注入投资技能"""

    def __init__(self, search_roots: list[str] | None = None):
        self._roots = search_roots or SKILL_SEARCH_ROOTS
        self._skills: dict[str, SkillMeta] = {}
        self._loaded = False

    @property
    def skills(self) -> dict[str, SkillMeta]:
        if not self._loaded:
            self.discover_all()
        return self._skills

    def discover_all(self) -> int:
        """扫描所有搜索根目录,发现并加载SKILL.md"""
        self._skills.clear()
        for root in self._roots:
            norm_root = os.path.normpath(root)
            if not os.path.isdir(norm_root):
                continue
            for skill_md in Path(norm_root).rglob("SKILL.md"):
                try:
                    meta = self._parse_skill_md(str(skill_md))
                    if meta and meta.name:
                        self._skills[meta.name] = meta
                except Exception as e:
                    log_exception("skill_engine", e)
        self._loaded = True
        return len(self._skills)

    def get_skill(self, name: str) -> SkillMeta | None:
        return self.skills.get(name)

    def query_by_context(self, context: str) -> list[SkillMeta]:
        """根据上下文文本匹配相关技能"""
        context_lower = context.lower()
        matched = []
        for skill in self.skills.values():
            score = self._match_score(skill, context_lower)
            if score > 0:
                matched.append((score, skill))
        matched.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in matched]

    def query_by_category(self, category: str) -> list[SkillMeta]:
        """按类别查询技能"""
        return [s for s in self.skills.values() if s.category == category]

    def inject_knowledge(self, skill_name: str, context: str = "", max_refs: int = 3) -> str:
        """注入技能知识到prompt - 返回格式化的知识文本"""
        skill = self.get_skill(skill_name)
        if not skill:
            return ""

        parts = [f"## 投资哲学: {skill.name}\n"]
        if skill.description:
            parts.append(f"**框架说明**: {skill.description[:300]}\n")

        if skill.main_content:
            parts.append(f"**核心方法论**:\n{skill.main_content[:2000]}\n")

        if skill.references:
            relevant_refs = self._select_relevant_refs(skill, context, max_refs)
            for ref in relevant_refs:
                parts.append(f"**参考 [{ref.section}]**:\n{ref.content[:1500]}\n")

        if skill.output_template:
            parts.append(f"**输出模板**:\n{skill.output_template[:800]}\n")

        return "\n---\n".join(parts)

    def get_all_skill_names(self) -> list[str]:
        return list(self.skills.keys())

    def get_stats(self) -> dict[str, Any]:
        cats: dict[str, int] = {}
        for s in self.skills.values():
            cats[s.category] = cats.get(s.category, 0) + 1
        return {
            "total_skills": len(self.skills),
            "by_category": cats,
            "skills": [
                {
                    "name": s.name,
                    "category": s.category,
                    "source": s.source_project,
                    "refs": len(s.references),
                }
                for s in self.skills.values()
            ],
        }

    # ── 内部方法 ──

    def _parse_skill_md(self, filepath: str) -> SkillMeta | None:
        """解析SKILL.md文件,提取元数据和引用"""
        with open(filepath, encoding="utf-8", errors="replace") as f:
            content = f.read()

        meta = SkillMeta(name="", description="", skill_dir=os.path.dirname(filepath))

        # 解析YAML frontmatter
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if fm_match:
            fm_text = fm_match.group(1)
            meta.name = self._yaml_get(fm_text, "name") or ""
            meta.description = self._yaml_get(fm_text, "description") or ""
            # 提取triggers
            triggers_str = self._yaml_get(fm_text, "triggers") or ""
            if triggers_str:
                meta.triggers = [
                    t.strip().strip('"').strip("'")
                    for t in re.split(r"[,\n]", triggers_str)
                    if t.strip()
                ]
            content = content[fm_match.end() :]
        else:
            # 尝试从第一个#标题提取name
            title_match = re.match(r"^#\s+(.+)", content)
            if title_match:
                meta.name = title_match.group(1).strip()

        meta.main_content = content

        # 确定分类
        meta.category = self._infer_category(meta.name, meta.description, filepath)

        # 确定来源项目
        meta.source_project = self._infer_source(filepath)

        # 加载引用文件
        meta.references = self._load_references(meta.skill_dir, content)

        # 提取输出模板
        template_match = re.search(
            r"(?:输出模板|Output Template|Standard Output|Required Output)[:\s]*\n([\s\S]{100,2000}?)(?:\n---|\n##|\Z)",
            content,
            re.IGNORECASE,
        )
        if template_match:
            meta.output_template = template_match.group(1).strip()

        return meta

    def _yaml_get(self, text: str, key: str) -> str:
        """从YAML文本中提取简单键值"""
        pattern = rf"^{key}:\s*(.+?)(?=\n\w|\n---|\Z)"
        m = re.search(pattern, text, re.DOTALL | re.MULTILINE)
        if m:
            val = m.group(1).strip()
            val = val.strip('"').strip("'")
            if val.startswith("|"):
                val = val[1:].strip()
            return val
        return ""

    def _infer_category(self, name: str, desc: str, filepath: str) -> str:
        """推断技能分类"""
        text = f"{name} {desc} {filepath}".lower()
        if any(
            k in text for k in ["buffett", "graham", "value", "moat", "安全边际", "护城河", "价值"]
        ):
            return "value"
        if any(k in text for k in ["munger", "taleb", "risk", "反脆弱", "黑天鹅", "逆向", "风险"]):
            return "risk"
        if any(k in text for k in ["factor", "quant", "因子", "backtest", "回测"]):
            return "quant"
        if any(k in text for k in ["strategy", "trading", "macd", "策略", "交易", "paper-trading"]):
            return "trading"
        if any(k in text for k in ["data", "数据", "行情", "a-share-data"]):
            return "data"
        return "analysis"

    def _infer_source(self, filepath: str) -> str:
        """从路径推断来源项目"""
        path_lower = filepath.lower()
        sources = {
            "buffett-skills": "buffett-skills",
            "munger-skill": "munger-skill",
            "taleb-skill": "taleb-skill",
            "china-stock-research": "china-stock-research-skills",
            "a-share-skill": "a-share-skill",
            "daily_stock_analysis": "daily_stock_analysis",
            "tradingagents-ashare": "TradingAgents-AShare",
            "qingfeng-skills": "qingfeng-skills",
            "report-reader": "report-reader",
        }
        for key, source in sources.items():
            if key in path_lower:
                return source
        return "unknown"

    def _load_references(self, skill_dir: str, main_content: str) -> list[SkillRef]:
        """加载技能目录下的引用文件"""
        refs: list[SkillRef] = []
        ref_dir = os.path.join(skill_dir, "references")
        if not os.path.isdir(ref_dir):
            return refs

        # 从main_content中提取引用文件名
        mentioned_files = set()
        for m in re.finditer(r"references/([^\s\)]+\.md)", main_content):
            mentioned_files.add(m.group(1))

        # 加载所有md文件
        for md_file in sorted(Path(ref_dir).glob("*.md")):
            fname = md_file.name
            try:
                with open(md_file, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                section = fname.replace(".md", "").replace("-", " ").title()
                refs.append(
                    SkillRef(
                        path=str(md_file),
                        content=content[:3000],
                        section=section,
                    )
                )
            except Exception as e:
                log_exception("skill_engine", e)

        return refs

    def _match_score(self, skill: SkillMeta, context_lower: str) -> int:
        """计算技能与上下文的匹配分数"""
        score = 0
        # 名称匹配
        if skill.name.lower() in context_lower:
            score += 10
        # 触发词匹配
        for trigger in skill.triggers:
            if trigger.lower() in context_lower:
                score += 5
        # 描述关键词匹配
        desc_words = set(re.findall(r"[\u4e00-\u9fff]+|[a-z]+", skill.description.lower()))
        ctx_words = set(re.findall(r"[\u4e00-\u9fff]+|[a-z]+", context_lower))
        overlap = desc_words & ctx_words
        score += len(overlap)
        return score

    def _select_relevant_refs(
        self, skill: SkillMeta, context: str, max_refs: int
    ) -> list[SkillRef]:
        """选择与上下文最相关的引用文件"""
        if not skill.references:
            return []
        if not context:
            return skill.references[:max_refs]

        scored = []
        ctx_lower = context.lower()
        for ref in skill.references:
            ref_lower = ref.content.lower()
            # 计算关键词重叠
            ctx_words = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-z]{3,}", ctx_lower))
            ref_words = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-z]{3,}", ref_lower))
            overlap = len(ctx_words & ref_words)
            scored.append((overlap, ref))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:max_refs]]


# 全局单例
_global_engine: SkillEngine | None = None


def get_skill_engine() -> SkillEngine:
    global _global_engine  # noqa: PLW0603
    if _global_engine is None:
        _global_engine = SkillEngine()
        _global_engine.discover_all()
    return _global_engine
