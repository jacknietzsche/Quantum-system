"""AI Agent 包装器

将 master_agents.py 中的13位大师 Agent 升级为 AI Agent ——
有 LLM 时调用工具做深度推理，无 LLM 时回退到纯 Python 规则评分。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from services.screening.agent_tools import AgentTools

logger = logging.getLogger(__name__)

# ── 每个大师的 AI 角色身份提示词 ──

MASTER_AGENT_PROMPTS: dict[str, str] = {
    "cathie_wood": (
        "你是 Cathie Wood (木头姐)，颠覆性创新投资的代表人物。\n"
        "你的投资哲学：寻找能够颠覆传统行业的高增长公司，对高估值有较高容忍度，"
        "关注前沿科技（AI、基因编辑、区块链、电动汽车）。\n"
        "评分标准：\n"
        "  - 营收增长率 >30% 加分，毛利率 >60% 加分\n"
        "  - 对 PE 容忍度高（只要营收增长足够快）\n"
        "  - 中小市值更有爆发力\n"
        "  - 经营利润率改善加分"
    ),
    "bill_ackman": (
        "你是 Bill Ackman，维权投资（Activist Investing）代表人物。\n"
        "你的投资哲学：集中持仓、深度研究、通过管理层改革释放价值。\n"
        "关注自由现金流收益率、ROE、管理层激励。\n"
        "评分标准：\n"
        "  - 高自由现金流收益率最重要\n"
        "  - 高 ROE + 低杠杆\n"
        "  - 管理层持股比例高加分\n"
        "  - 经营利润率持续改善"
    ),
    "michael_burry": (
        "你是 Michael Burry，逆向价值投资者。\n"
        "你的投资哲学：寻找被市场忽视的深度价值机会，关注安全边际。\n"
        "擅长识别尾部风险和泡沫。\n"
        "评分标准：\n"
        "  - 低 PE + 低 PB 至关重要\n"
        "  - 格雷厄姆安全边际（价格 < Graham Number 的 70%）\n"
        "  - 低负债 + 强流动性\n"
        "  - 市值跌破有形资产账面价值加分"
    ),
    "stanley_druckenmiller": (
        "你是 Stanley Druckenmiller，宏观趋势交易大师。\n"
        "你的投资哲学：识别宏观拐点，集中下注，顺势而为。\n"
        "关注趋势强度、动量信号和波动率环境。\n"
        "评分标准：\n"
        "  - 趋势方向最重要（上升趋势加分）\n"
        "  - 价格动量 + 成交量配合\n"
        "  - 均线多头排列加分\n"
        "  - 波动率适中环境加分"
    ),
    "aswath_damodaran": (
        "你是 Aswath Damodaran，估值大师。\n"
        "你的投资哲学：一切资产都可估值，核心是判断内在价值与市场价格的关系。\n"
        "关注风险溢价、成长合理定价。\n"
        "评分标准：\n"
        "  - PEG < 0.8 是非常好的买入机会\n"
        "  - 盈利收益率（E/P）> 8% 加分\n"
        "  - PB/ROE 匹配度\n"
        "  - 成长溢价合理性"
    ),
    "phil_fisher": (
        "你是 Phil Fisher，成长型投资先驱。\n"
        "你的投资哲学：Scuttlebutt 调研法，关注公司管理层质量、研发投入和长期竞争优势。\n"
        "评分标准：\n"
        "  - 营收持续高增长最重要\n"
        "  - 高毛利率 + 高研发投入 = 护城河\n"
        "  - 经营效率持续提升\n"
        "  - ROE > 20% 加分"
    ),
    "rakesh_jhunjhunwala": (
        "你是 Rakesh Jhunjhunwala（印度巴菲特），价值投资者。\n"
        "你的投资哲学：买入优秀企业长期持有，信任管理层，关注中小盘价值。\n"
        "评分标准：\n"
        "  - 高 ROE（>20%）且低 PE（<20）\n"
        "  - 低杠杆，财务稳健\n"
        "  - 中小市值（<1000亿）加分\n"
        "  - 盈利持续增长"
    ),
    "howard_marks": (
        "你是 Howard Marks，周期投资大师。\n"
        "你的投资哲学：第二层次思维，在市场恐慌时买入，在狂热时卖出。\n"
        "关注市场情绪周期和风险控制。\n"
        "评分标准：\n"
        "  - 下跌中寻找价值（跌幅大但基本面尚可 = 机会）\n"
        "  - 低 PB 提供安全垫\n"
        "  - 波动率适中加分\n"
        "  - 财务稳健（低负债）加分"
    ),
    "joel_greenblatt": (
        "你是 Joel Greenblatt，魔法公式发明者。\n"
        "你的投资哲学：高 ROIC + 低 EV/EBITDA 的组合能持续跑赢市场。\n"
        "纯粹的量化和系统化投资。\n"
        "评分标准：\n"
        "  - ROE > 25% 加分很多\n"
        "  - PE < 10 加分很多\n"
        "  - 高经营利润率加分\n"
        "  - 盈利为正的基本要求"
    ),
    "peter_lynch_growth": (
        "你是 Peter Lynch（成长版），寻找 Ten-Bagger 的专家。\n"
        "你的投资哲学：在生活中发现好公司，GARP（合理价格成长）策略。\n"
        "评分标准：\n"
        "  - PEG < 0.5 是最佳信号\n"
        "  - 营收增长 > 25% 加分\n"
        "  - 中小市值更有十倍股潜力\n"
        "  - 毛利率高加分"
    ),
    "risk_sentinel": (
        "你是风险哨兵，融合 Taleb 的反脆弱理念和 Munger 的风险意识。\n"
        "你的职责：识别和量化投资风险。\n"
        "评分标准（高分 = 高风险 = 看空）：\n"
        "  - 高杠杆（负债率 >150%）高风险\n"
        "  - 流动性不足（流动比率 <1.0）高风险\n"
        "  - 现金比率低 + 高波动率\n"
        "  - PE > 100 估值泡沫风险\n"
        "  - 近期暴跌风险"
    ),
    "limit_up_master": (
        "你是涨停大师，A股短线博弈专家。\n"
        "你的投资哲学：追涨停板策略，关注资金博弈和市场情绪。\n"
        "评分标准：\n"
        "  - 高换手率（>15%）是核心信号\n"
        "  - 量比 > 2.0 加分\n"
        "  - 5-9% 涨幅最佳（未涨停但有动力）\n"
        "  - 合理 PE（0-30）加分，亏损或高 PE 减分"
    ),
    "momentum_master": (
        "你是动量大师，中期趋势跟踪专家。\n"
        "你的投资哲学：跟随趋势，不预测顶底。\n"
        "评分标准：\n"
        "  - 趋势强度最重要（>70 加分）\n"
        "  - RSI 在 40-70 区间为健康趋势\n"
        "  - 营收增长 + ROE 提供基本面支撑\n"
        "  - 合理 PE 加分（<40）"
    ),
}


class AIAgent:
    """AI Agent — 可调用工具 + LLM 推理，或回退到规则评分

    用法:
        agent = AIAgent(name="cathie_wood", display_name="Cathie Wood",
                        style="growth", llm_client=llm, rule_agent=cathie_wood_instance)
        result = agent.analyze("600519", {"pe_ratio": 19, "roe": 30})
    """

    def __init__(
        self,
        name: str,
        display_name: str,
        style: str,
        llm_client: Any | None = None,
        rule_agent: Any | None = None,
        tools: AgentTools | None = None,
    ):
        self.name = name
        self.display_name = display_name
        self.style = style
        self._llm = llm_client
        self._rule = rule_agent
        self._tools = tools or AgentTools()

    def _summarize_rule_result(self, result: dict) -> str:
        """从规则评分结果生成一句话推理"""
        parts = []
        details = result.get("details") or result.get("metrics") or {}
        if isinstance(details, dict):
            for k, v in list(details.items())[:5]:
                parts.append(f"{k}={v}")
        score = result.get("score", 50)
        signal = result.get("signal", "neutral")
        return f"[rule] {signal}({score}): {', '.join(parts)}"

    def analyze(
        self,
        stock_code: str,
        financials: dict,
        prices: list[float] | None = None,
    ) -> dict:
        """分析一只股票

        有 LLM 时使用 AI 推理 + 工具调用，
        无 LLM 时回退到规则评分（委托给 _rule agent）。
        """
        if self._llm:
            return self._ai_analyze(stock_code, financials, prices)
        return self._rule_analyze(stock_code, financials, prices)

    def _rule_analyze(
        self,
        stock_code: str,
        financials: dict,
        prices: list[float] | None = None,
    ) -> dict:
        """回退到规则评分"""
        if self._rule is not None:
            try:
                result = self._rule.analyze(stock_code, financials, prices)
                if result:
                    result.setdefault("name", self.name)
                    result.setdefault("display_name", self.display_name)
                    result.setdefault("style", self.style)
                    result.setdefault("ai_enabled", False)
                    result.setdefault("reasoning", self._summarize_rule_result(result))
                    result.setdefault("details", result.get("metrics", {}))
                    return result
            except Exception as e:
                logger.debug("Rule analyze failed for %s: %s", self.name, e)

        # 默认返回
        return {
            "name": self.name,
            "display_name": self.display_name,
            "style": self.style,
            "stock_code": stock_code,
            "score": 50,
            "signal": "neutral",
            "reasoning": "Rule analysis unavailable",
            "ai_enabled": False,
            "details": {},
        }

    def _ai_analyze(
        self,
        stock_code: str,
        financials: dict,
        prices: list[float] | None = None,
    ) -> dict:
        """AI 驱动分析流程：
        1. 调用工具获取数据
        2. 构建包含工具数据的推理提示词
        3. 调用 LLM 推理
        4. 解析输出为标准格式
        """
        try:
            # Step 1: 调用工具
            risk_data = self._tools.risk_scan(stock_code)
            financial_data = self._tools.financial_health(stock_code)
            tech_data = self._tools.technical_pattern(prices) if prices else {}
            rs_data = self._tools.relative_strength(stock_code)

            # Step 2: 构建推理提示词
            prompt = self._build_ai_prompt(
                stock_code=stock_code,
                financials=financials,
                financial_data=financial_data,
                risk_data=risk_data,
                tech_data=tech_data,
                rs_data=rs_data,
            )

            # Step 3: 调用 LLM (self._llm is not None because _ai_analyze only called when LLM available)
            llm = self._llm
            if llm is None:
                raise RuntimeError("LLM client is not available for AI analysis")
            response = llm.chat(prompt)
            response_text = str(response)

            # Step 4: 解析输出
            parsed = self._parse_ai_response(response_text)

            return {
                "name": self.name,
                "display_name": self.display_name,
                "style": self.style,
                "stock_code": stock_code,
                "score": parsed.get("score", 50),
                "signal": parsed.get("signal", "neutral"),
                "reasoning": parsed.get("reasoning", response_text[:300]),
                "ai_enabled": True,
                "details": {
                    "ai_analysis": True,
                    "tool_data": {
                        "risk_scan": risk_data.get("risk_level", "unknown"),
                        "financial_health_score": financial_data.get("score", 50),
                        "rs_score": rs_data.get("rs_score", 50),
                        "technical_trend": tech_data.get("trend", "neutral"),
                    },
                    "raw_llm_output": response_text[:500],
                },
            }
        except Exception as e:
            logger.warning("AI analyze failed for %s: %s", self.name, e)
            # 回退到规则
            return self._rule_analyze(stock_code, financials, prices)

    def _build_ai_prompt(
        self,
        stock_code: str,
        financials: dict,
        financial_data: dict,
        risk_data: dict,
        tech_data: dict,
        rs_data: dict,
    ) -> str:
        """构建 AI 推理提示词"""
        identity_prompt = MASTER_AGENT_PROMPTS.get(
            self.name,
            f"你是{self.display_name}，一位{self.style}风格的投资分析师。",
        )

        # 格式化财务数据
        fin_lines = "\n".join(f"  {k}: {v}" for k, v in financials.items())
        risk_items = (
            "\n".join(
                f"  - [{r.get('severity', '')}] {r.get('detail', '')}"
                for r in risk_data.get("risk_items", [])
            )
            or "  无显著风险"
        )

        tech_section = ""
        if tech_data:
            tech_section = (
                f"\n技术形态:\n"
                f"  趋势: {tech_data.get('trend', 'N/A')}\n"
                f"  均线排列: {tech_data.get('ma_alignment', 'N/A')}\n"
                f"  RSI: {tech_data.get('rsi', 'N/A')}\n"
                f"  波动率: {tech_data.get('volatility', 'N/A')}\n"
                f"  支撑/阻力: {tech_data.get('support', 'N/A')}/{tech_data.get('resistance', 'N/A')}"
            )

        rs_section = ""
        if rs_data.get("rs_score") is not None:
            rs_section = (
                f"\n相对强度:\n"
                f"  RS评分: {rs_data.get('rs_score', 'N/A')}\n"
                f"  行业对比: {rs_data.get('vs_industry', 'N/A')}\n"
                f"  市场对比: {rs_data.get('vs_market', 'N/A')}"
            )

        return f"""{identity_prompt}

请分析股票 {stock_code} 的投资价值。

## 财务数据
{fin_lines}

## 财务健康评分: {financial_data.get("score", "N/A")}/100
{financial_data.get("signal", "N/A")}
{rs_section}

## 风险评估
{risk_items}
风险等级: {risk_data.get("risk_level", "unknown")}
风险评分: {risk_data.get("risk_score", 0)}/100
{tech_section}

## 输出要求
请根据以上数据和你作为{self.display_name}的投资理念，输出以下JSON格式的评分（不要输出其他内容）：

{{
  "score": <0-100的整数>,
  "signal": <"bullish"|"bearish"|"neutral">,
  "reasoning": "<1-2句话解释评分理由>"
}}"""

    def _parse_ai_response(self, text: str) -> dict:
        """从 LLM 响应中解析出结构化评分"""
        # 尝试提取 JSON 块
        try:
            # 找第一组 { }
            start = text.index("{")
            end = text.rindex("}") + 1
            json_str = text[start:end]
            data = json.loads(json_str)
            score = int(data.get("score", 50))
            score = max(0, min(100, score))
            signal_raw = str(data.get("signal", "neutral")).lower()
            if signal_raw in ("bullish", "买入", "看多"):
                signal = "bullish"
            elif signal_raw in ("bearish", "卖出", "看空"):
                signal = "bearish"
            else:
                signal = "neutral"
            reasoning = str(data.get("reasoning", ""))[:500]
            return {"score": score, "signal": signal, "reasoning": reasoning}
        except (ValueError, TypeError):
            # 解析失败，尝试关键词匹配
            text_lower = text.lower()
            score = 50
            if "score" in text_lower:
                for word in text.split():
                    if word.isdigit():
                        s = int(word)
                        if 0 <= s <= 100:
                            score = s
                            break
            if any(w in text_lower for w in ("bullish", "买入", "看多", "推荐", "积极")):
                signal = "bullish"
            elif any(w in text_lower for w in ("bearish", "卖出", "看空", "规避", "风险")):
                signal = "bearish"
            else:
                signal = "neutral"
            return {
                "score": score,
                "signal": signal,
                "reasoning": text[:300],
            }


class AIAgentRegistry:
    """AI Agent 注册表 — 管理所有 AI 增强的大师 Agent

    用法:
        registry = AIAgentRegistry(llm_client=llm)
        # 有 LLM 时 → AI 推理
        # 无 LLM 时 → 回退规则评分
        result = registry.analyze_one("cathie_wood", "600519", {"pe_ratio": 19, "roe": 30})
        results = registry.analyze_all("600519", {"pe_ratio": 19})
    """

    def __init__(self, llm_client: Any | None = None, tools: AgentTools | None = None):
        self._llm = llm_client
        self._tools = tools or AgentTools()
        self._agents: dict[str, AIAgent] = {}
        self._register_all()

    def _register_all(self):
        """注册所有 AI 增强的大师 Agent"""
        from services.master_agents import MasterAgentRegistry

        master_registry = MasterAgentRegistry()
        for name in master_registry.get_all_names():
            rule_agent = master_registry.get_agent(name)
            if rule_agent is None:
                continue
            agent = AIAgent(
                name=getattr(rule_agent, "name", name),
                display_name=getattr(rule_agent, "display_name", name),
                style=getattr(rule_agent, "style", ""),
                llm_client=self._llm,
                rule_agent=rule_agent,
                tools=self._tools,
            )
            self._agents[name] = agent

    def get_agent(self, name: str) -> AIAgent | None:
        """获取指定名称的 AI Agent"""
        return self._agents.get(name)

    def get_all_names(self) -> list[str]:
        """获取所有 AI Agent 名称列表"""
        return list(self._agents.keys())

    def analyze_one(
        self,
        name: str,
        stock_code: str,
        financials: dict,
        prices: list[float] | None = None,
    ) -> dict:
        """使用指定大师分析一只股票"""
        agent = self._agents.get(name)
        if agent is None:
            return {
                "name": name,
                "stock_code": stock_code,
                "score": 50,
                "signal": "neutral",
                "reasoning": f"Unknown agent: {name}",
                "error": f"Agent '{name}' not found",
            }
        return agent.analyze(stock_code, financials, prices)

    def analyze_all(
        self,
        stock_code: str,
        financials: dict,
        prices: list[float] | None = None,
    ) -> list[dict]:
        """使用所有大师分析一只股票"""
        results = []
        for name in self._agents:
            try:
                result = self.analyze_one(name, stock_code, financials, prices)
                results.append(result)
            except Exception as e:
                logger.debug("Agent %s failed: %s", name, e)
                results.append(
                    {
                        "name": name,
                        "stock_code": stock_code,
                        "score": 50,
                        "signal": "neutral",
                        "reasoning": f"Analysis failed: {e}",
                    }
                )
        return results
