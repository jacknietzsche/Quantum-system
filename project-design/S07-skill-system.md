# S07 — Skill系统设计

> **设计参考**: DeerFlow 2.0的渐进式加载 + OpenViking(字节跳动)的文件系统范式管理Skill。

## 7.1 Skill架构

借鉴DeerFlow 2.0的渐进式加载：Skill按需注入Agent的prompt，不一次加载所有上下文。

```
skills/
├── skill_engine.py              # Skill引擎（发现+加载+注入）
├── registry.py                  # Skill注册表
├── buffett/
│   ├── SKILL.md                 # 技能定义（frontmatter + prompt）
│   └── references/              # 参考文档
├── munger/
│   ├── SKILL.md
│   └── references/
├── taleb/
│   ├── SKILL.md
│   └── references/
├── a-share-trading/
│   ├── SKILL.md
│   └── references/
└── china-stock-research/
    ├── SKILL.md
    └── references/
```

## 7.2 SKILL.md格式规范

每个Skill由一个`SKILL.md`文件定义，包含frontmatter元数据和正文prompt：

```markdown
---
name: buffett
version: 1.0
description: 巴菲特价值投资框架
triggers:
  - "分析任何股票"
  - "评估投资机会"
  - "解读财务报告"
  - "评估护城河"
agents:
  - fundamentals_analyst
  - bull_researcher
  - portfolio_manager
priority: 1
max_tokens: 2000
---

# 巴菲特价值投资框架

## 核心原则

1. **能力圈**: 只投资你理解的生意
2. **护城河**: 寻找有持续竞争优势的企业
3. **安全边际**: 以低于内在价值的价格买入
4. **管理层**: 诚实、有能力的管理层
5. **长期持有**: 好公司值得长期持有

## 分析检查清单

### 护城河评估
- 品牌力：消费者是否愿意为品牌支付溢价？
- 转换成本：客户切换到竞争对手的成本高吗？
- 网络效应：用户越多，产品越有价值？
- 成本优势：是否有结构性的成本优势？

### 财务健康度
- ROE > 15% 持续5年以上
- 自由现金流/净利润 > 80%
- 负债率 < 50%
- 毛利率稳定或上升

### 估值
- PE < 行业平均 或 PE < 自身历史中位数
- PEG < 1（考虑增长率）
- 股息率 > 2%

## 输出格式

分析结论必须包含：
1. **护城河评级**: Strong/Moderate/Weak/None
2. **安全边际**: 当前价格 vs 估算内在价值
3. **核心风险**: 最大的1-2个风险点
4. **建议**: Buy/Hold/Sell + 置信度
```

### Frontmatter字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | ✅ | 唯一标识符 |
| version | string | ✅ | 语义化版本号 |
| description | string | ✅ | 一句话描述 |
| triggers | list[string] | ✅ | 触发条件（中文描述） |
| agents | list[string] | ✅ | 可使用的Agent列表 |
| priority | int | ❌ | 加载优先级（1最高，默认10） |
| max_tokens | int | ❌ | prompt最大token数（默认2000） |

## 7.3 SkillEngine实现

```python
from pathlib import Path
import yaml

class SkillMetadata(BaseModel):
    name: str
    version: str
    description: str
    triggers: list[str]
    agents: list[str]
    priority: int = 10
    max_tokens: int = 2000

class SkillContent(BaseModel):
    metadata: SkillMetadata
    prompt: str                          # SKILL.md正文（去掉frontmatter）

class SkillEngine:
    """Skill引擎：发现、加载、注入"""

    def __init__(self, skills_dir: str = "skills/"):
        self.skills_dir = Path(skills_dir)
        self.registry: dict[str, SkillContent] = {}  # name → SkillContent
        self._loaded = False

    def discover(self):
        """扫描skills/目录，发现所有可用Skill"""
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

    def _parse_skill(self, path: Path) -> Optional[SkillContent]:
        """解析SKILL.md文件"""
        text = path.read_text(encoding="utf-8")

        # 解析frontmatter
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                meta_dict = yaml.safe_load(parts[1])
                prompt = parts[2].strip()
                metadata = SkillMetadata(**meta_dict)
                return SkillContent(metadata=metadata, prompt=prompt)

        return None

    def get_skill(self, name: str) -> Optional[SkillContent]:
        """获取指定Skill"""
        if not self._loaded:
            self.discover()
        return self.registry.get(name)

    def get_for_agent(self, agent_name: str) -> list[SkillContent]:
        """获取指定Agent可用的所有Skill（按优先级排序）"""
        if not self._loaded:
            self.discover()

        skills = [
            s for s in self.registry.values()
            if agent_name in s.metadata.agents
        ]
        return sorted(skills, key=lambda s: s.metadata.priority)

    def activate(self, name: str) -> Optional[str]:
        """激活Skill，返回注入prompt的内容"""
        skill = self.get_skill(name)
        if skill:
            return skill.prompt
        return None
```

## 7.4 Skill注入逻辑

在Agent构建prompt时，按条件注入SKILL.md内容：

```python
def build_agent_prompt(
    agent_name: str,
    system_message: str,
    state: dict,
    skill_engine: SkillEngine,
) -> str:
    """
    构建Agent的完整prompt。
    1. 基础system_message
    2. 根据Agent名称，注入可用Skill
    3. 注入历史记忆（如果启用）
    """
    parts = [system_message]

    # 注入Skill
    skills = skill_engine.get_for_agent(agent_name)
    if skills:
        parts.append("\n\n## 可用投资框架\n")
        for skill in skills:
            parts.append(f"### {skill.metadata.name}: {skill.metadata.description}")
            parts.append(skill.prompt)
            parts.append("")

    # 注入历史记忆（来自S09）
    memory = state.get("memory_context")
    if memory:
        parts.append(f"\n\n## 历史决策记忆\n{memory}")

    return "\n".join(parts)
```

## 7.5 Skill与Agent绑定关系

| Agent | 可用Skill | 触发条件 |
|-------|----------|----------|
| 市场分析师 | a-share-trading | 所有A股分析 |
| 基本面分析师 | buffett, munger | 分析财务数据时 |
| 新闻分析师 | — | 无需Skill |
| 情绪分析师 | — | 无需Skill |
| 看涨研究员 | buffett, munger | 构建看涨论据时 |
| 看跌研究员 | taleb | 构建看跌论据时 |
| 研究经理 | buffett, munger, taleb | 综合判断时 |
| 交易员 | a-share-trading | 制定交易计划时 |
| 激进分析师 | — | 无需Skill |
| 保守分析师 | taleb | 评估下行风险时 |
| 中性分析师 | — | 无需Skill |
| 投资组合经理 | buffett, munger, china-stock-research | 最终决策时 |

## 7.6 Skill缓存

```python
class CachedSkillEngine(SkillEngine):
    """带缓存的Skill引擎，避免重复读取文件"""

    def __init__(self, skills_dir: str = "skills/"):
        super().__init__(skills_dir)
        self._prompt_cache: dict[str, str] = {}  # name → prompt缓存

    def activate(self, name: str) -> Optional[str]:
        """激活Skill（带缓存）"""
        if name in self._prompt_cache:
            return self._prompt_cache[name]

        prompt = super().activate(name)
        if prompt:
            self._prompt_cache[name] = prompt
        return prompt
```

---

**依赖**: S3(架构), S2(理念)
**被依赖**: S4(Agent), S15(LLM层)
