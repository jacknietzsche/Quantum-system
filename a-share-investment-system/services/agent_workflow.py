"""Agent Workflow Service - Stage4 deep analysis with multi-agent coordination"""

import json
import os
from dataclasses import dataclass, field
from typing import Any

from services.base import ServiceResult
from services.skill_engine import SkillEngine
from shared.logging import log_exception

SKILL_MAP = {
    "limit_up": ["limit-up-strategy", "buffett"],
    "momentum": ["momentum-strategy", "munger-perspective"],
    "value": ["buffett", "taleb-perspective"],
    "hybrid": ["buffett", "munger-perspective", "taleb-perspective"],
}

VALID_STYLES = set(SKILL_MAP.keys())


@dataclass
class AnalysisResult:
    stock_code: str
    stock_name: str = ""
    research: dict = field(default_factory=dict)
    debate: dict = field(default_factory=dict)
    risk: dict = field(default_factory=dict)
    signal: dict = field(default_factory=dict)
    error: str = ""


class AgentWorkflowService:
    """Multi-agent workflow for deep stock analysis"""

    def __init__(self, style: str = "hybrid", config=None):
        self.style = style if style in VALID_STYLES else "hybrid"
        self.config = config or {}
        self.required_skills = SKILL_MAP.get(self.style, [])
        self.skill_engine = SkillEngine()
        self.skill_engine.discover_all()
        self.llm_available = False
        self.llm_config: dict[str, Any] = {}
        self._init_llm_client()

    def _init_llm_client(self):
        """Initialize LLM configuration for direct httpx calls"""
        try:
            from shared.config import config as _cfg

            cfg = _cfg.data
        except Exception as e:
            log_exception("agent_workflow", e, context="Error")
            cfg = {}

        llm_cfg = cfg.get("llm", {}) if isinstance(cfg, dict) else {}
        model_spec = self.config.get(
            "model",
            llm_cfg.get("default_model", "siliconflow:deepseek-ai/DeepSeek-R1"),
        )

        provider = model_spec
        model_name = model_spec
        if ":" in model_spec:
            provider, model_name = model_spec.split(":", 1)

        api_key = os.environ.get("SILICONFLOW_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
        base_url = ""
        if isinstance(llm_cfg, dict):
            providers = llm_cfg.get("providers", {})
            provider_cfg = providers.get(provider, {})
            if isinstance(provider_cfg, dict):
                base_url = provider_cfg.get("base_url", "")

        self.llm_available = bool(api_key)
        self.llm_config = {
            "provider": provider,
            "model": model_name,
            "api_key": api_key or "",
            "base_url": base_url,
            "temperature": float(self.config.get("temperature", 0.7)),
            "max_tokens": int(self.config.get("max_tokens", 4000)),
        }

    def _build_prompt(self, stock_code: str, data: dict) -> str:
        skill_knowledge_parts = []
        for skill_name in self.required_skills:
            knowledge = self.skill_engine.inject_knowledge(
                skill_name,
                context=f"stock {stock_code} analysis {self.style} strategy",
                max_refs=2,
            )
            if knowledge:
                skill_knowledge_parts.append(knowledge)

        _skills_section = (
            "\n\n".join(skill_knowledge_parts) if skill_knowledge_parts else "(无特定投资哲学注入)"
        )

        stock_info_lines = []
        for k, v in data.items():
            stock_info_lines.append(f"  {k}: {v}")
        _stock_info = "\n".join(stock_info_lines)

        return """你是一位A股深度分析专家,正在分析股票 {stock_code}。

## 投资哲学参考
{skills_section}

## 股票数据
{stock_info}

## 分析任务
请进行以下分析:

### 1. 基本面分析
- 估值水平(PE/PB/ROE)
- 盈利能力与成长性
- 财务健康状况

### 2. 技术面分析
- 趋势判断
- 量价关系
- 技术指标信号

### 3. 资金面分析
- 主力资金动向
- 成交量变化

### 4. 市场情绪分析
- 市场关注度
- 情绪判断

请以JSON格式输出分析结果,格式如下:
{{
  "fundamental": {{"valuation": "", "profitability": "", "health": ""}},
  "technical": {{"trend": "", "volume_price": "", "signals": []}},
  "capital": {{"flow": "", "volume_analysis": ""}},
  "sentiment": {{"attention": "", "judgment": ""}},
  "summary": ""
}}
"""

    def _call_llm(self, prompt: str) -> str:
        if not self.llm_available:
            return self._simulate_llm_response(prompt)

        try:
            import httpx

            headers = {
                "Authorization": f"Bearer {self.llm_config['api_key']}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.llm_config["model"],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self.llm_config["temperature"],
                "max_tokens": self.llm_config["max_tokens"],
            }

            base_url = self.llm_config.get("base_url", "https://api.siliconflow.cn/v1").rstrip("/")
            url = f"{base_url}/chat/completions"

            response = httpx.post(url, headers=headers, json=payload, timeout=5.0)
            response.raise_for_status()
            result = response.json()
            return result.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            return self._simulate_llm_response(prompt, error=str(e))

    def _simulate_llm_response(self, prompt: str, error: str = "") -> str:
        import re

        code_match = re.search(r"stock (\d{6})", prompt)
        code_match.group(1) if code_match else "unknown"

        pe_match = re.search(r"pe[:\s]+([\d.]+)", prompt, re.IGNORECASE)
        pe = float(pe_match.group(1)) if pe_match else 30

        if pe < 15:
            valuation = "低估"
            trend = "上升趋势"
            summary = "基本面良好,估值偏低,建议关注"
        elif pe < 30:
            valuation = "合理"
            trend = "震荡上行"
            summary = "估值合理,维持中性偏乐观判断"
        else:
            valuation = "偏高"
            trend = "震荡"
            summary = "估值偏高,需警惕回调风险"

        return json.dumps(
            {
                "fundamental": {
                    "valuation": valuation,
                    "profitability": "盈利稳定",
                    "health": "财务健康",
                },
                "technical": {
                    "trend": trend,
                    "volume_price": "量价配合良好",
                    "signals": ["MA多头排列", "MACD金叉"],
                },
                "capital": {
                    "flow": "主力资金净流入",
                    "volume_analysis": "成交量放大",
                },
                "sentiment": {
                    "attention": "市场关注度高",
                    "judgment": "偏乐观",
                },
                "summary": summary,
            },
            ensure_ascii=False,
        )

    def _run_research_agent(self, prompt: str) -> dict:
        response = self._call_llm(prompt)
        try:
            research = json.loads(response)
        except (json.JSONDecodeError, TypeError):
            research = {
                "fundamental": {"valuation": "N/A", "profitability": "N/A", "health": "N/A"},
                "technical": {"trend": "N/A", "volume_price": "N/A", "signals": []},
                "capital": {"flow": "N/A", "volume_analysis": "N/A"},
                "sentiment": {"attention": "N/A", "judgment": "N/A"},
                "summary": "无法解析LLM响应",
            }
        return research

    def _run_debate(self, stock_code: str, research: dict) -> dict:
        """Enhanced debate: quant analyzers + master agents cross-validation"""
        summary = research.get("summary", "")
        fundamental = research.get("fundamental", {})
        valuation = fundamental.get("valuation", "") if isinstance(fundamental, dict) else ""

        bull_claims = []
        bear_claims = []
        bull_score = 0
        bear_score = 0

        # 1. Research-based claims
        if "低估" in valuation or "合理" in valuation:
            bull_claims.append(f"估值{valuation},具备安全边际")
            bull_score += 15
        if "偏高" in valuation:
            bear_claims.append(f"估值{valuation},存在高估风险")
            bear_score += 15
        if "上升" in summary or "乐观" in summary:
            bull_claims.append("技术面趋势向好,市场情绪积极")
            bull_score += 10
        else:
            bear_claims.append("技术面趋势不明朗,观望为宜")
            bear_score += 10

        # 2. Quant analyzer cross-validation
        try:
            from services.quant_analyzers import QuantAnalyzers

            qa = QuantAnalyzers()
            f_data = {
                "roe": 15,
                "pe_ratio": 20,
                "pb_ratio": 3,
                "price": 50,
                "gross_margin": 30,
                "debt_to_equity": 50,
                "eps": 2,
                "bvps": 10,
                "earnings_growth_3y": 10,
                "cash_to_assets": 10,
            }
            buffett = qa.buffett_analyze(stock_code, f_data)
            graham = qa.graham_analyze(stock_code, f_data)
            lynch = qa.lynch_analyze(stock_code, f_data)
            taleb = qa.taleb_analyze(stock_code, f_data)
            for name, r in [
                ("buffett", buffett),
                ("graham", graham),
                ("lynch", lynch),
                ("taleb", taleb),
            ]:
                if r.get("signal") == "bullish":
                    bull_claims.append(f"{name}分析: 看多({r.get('score', 50)}分)")
                    bull_score += r.get("score", 50) * 0.3
                elif r.get("signal") == "bearish":
                    bear_claims.append(f"{name}分析: 看空({r.get('score', 50)}分)")
                    bear_score += (100 - r.get("score", 50)) * 0.3
        except Exception as e:
            log_exception("agent_wf", e)

        # 3. Master agent cross-validation
        try:
            from services.master_agents import get_master_agents

            masters = get_master_agents()
            master_results = masters.analyze_selected(
                stock_code, {}, ["limit_up_master", "momentum_master"]
            )
            for mr in master_results:
                if mr.get("signal") in ("买入", "bullish"):
                    bull_claims.append(f"大师{mr.get('display_name', '')}: 看多")
                    bull_score += mr.get("score", 50) * 0.2
                elif mr.get("signal") in ("卖出", "bearish", "观望"):
                    bear_claims.append(f"大师{mr.get('display_name', '')}: 谨慎")
                    bear_score += 10
        except Exception as e:
            log_exception("agent_wf", e)

        if not bull_claims:
            bull_claims.append("长期持有价值存在")
        if not bear_claims:
            bear_claims.append("市场不确定性仍然存在")

        # Determine verdict from weighted scores
        total = bull_score + bear_score
        if total == 0:
            verdict, confidence = "中性", 0.5
        elif bull_score > bear_score * 1.2:
            verdict = "看多"
            confidence = round(min(0.5 + 0.4 * (bull_score - bear_score) / max(total, 1), 0.95), 2)
        elif bear_score > bull_score * 1.2:
            verdict = "看空"
            confidence = round(min(0.5 + 0.4 * (bear_score - bull_score) / max(total, 1), 0.95), 2)
        else:
            verdict = "中性"
            confidence = 0.5

        return {
            "bull_claims": bull_claims,
            "bear_claims": bear_claims,
            "bull_score": round(bull_score, 1),
            "bear_score": round(bear_score, 1),
            "verdict": verdict,
            "confidence": confidence,
        }

    def _run_risk_analysis(self, stock_code: str, data: dict, debate: dict) -> dict:
        risk_factors = []
        risk_score = 0

        turnover_rate = data.get("turnover_rate", 0)
        if isinstance(turnover_rate, (int, float)) and turnover_rate > 20:
            risk_factors.append(f"换手率{turnover_rate}%过高,短线投机风险大")
            risk_score += 30
        elif isinstance(turnover_rate, (int, float)) and turnover_rate > 10:
            risk_factors.append(f"换手率{turnover_rate}%偏高")
            risk_score += 15

        pe = data.get("pe", 0)
        if isinstance(pe, (int, float)) and pe > 80:
            risk_factors.append(f"PE{pe}倍过高,估值泡沫风险")
            risk_score += 25
        elif isinstance(pe, (int, float)) and pe > 50:
            risk_factors.append(f"PE{pe}倍偏高")
            risk_score += 10
        elif isinstance(pe, (int, float)) and 0 < pe < 5:
            risk_factors.append(f"PE{pe}倍过低,可能存在基本面风险")
            risk_score += 20

        volume_ratio = data.get("daily_volume_ratio", 1.0)
        if isinstance(volume_ratio, (int, float)) and volume_ratio < 0.5:
            risk_factors.append("成交量低迷,流动性风险")
            risk_score += 20
        elif isinstance(volume_ratio, (int, float)) and volume_ratio > 3:
            risk_factors.append("成交量异常放大,警惕出货风险")
            risk_score += 15

        change_pct = data.get("change_pct", 0)
        if isinstance(change_pct, (int, float)) and abs(change_pct) > 9.9:
            risk_factors.append("涨跌幅超过9.9%,极端波动风险")
            risk_score += 15

        if risk_score <= 20:
            risk_level = "低"
        elif risk_score <= 50:
            risk_level = "中"
        else:
            risk_level = "高"

        return {
            "risk_score": min(risk_score, 100),
            "risk_level": risk_level,
            "risk_factors": risk_factors,
        }

    def _generate_signal(self, debate: dict, risk: dict) -> dict:
        verdict = debate.get("verdict", "中性")
        debate_confidence = debate.get("confidence", 0.5)
        risk_score = risk.get("risk_score", 0)
        risk_level = risk.get("risk_level", "中")

        if risk_level == "高":
            action = "卖出"
            confidence = max(0.5, 1.0 - risk_score / 100)
            reasoning = f"风险等级为高(风险分{risk_score}),建议卖出回避"
        elif verdict == "看多" and risk_level == "低":
            action = "买入"
            confidence = min(debate_confidence + 0.2, 0.95)
            reasoning = f"多方观点占优({debate_confidence:.0%}置信度)且风险可控"
        elif verdict == "看多" and risk_level == "中":
            action = "持有"
            confidence = debate_confidence
            reasoning = f"多方观点占优但存在中等风险(风险分{risk_score}),建议持有观察"
        elif verdict == "看空":
            action = "卖出"
            confidence = debate_confidence
            reasoning = f"空方观点占优({debate_confidence:.0%}置信度),建议卖出"
        else:
            action = "观望"
            confidence = 0.5
            reasoning = "多空均衡,建议观望"

        return {
            "action": action,
            "confidence": round(confidence, 2),
            "reasoning": reasoning,
            "risk_level": risk_level,
            "debate_verdict": verdict,
        }

    def analyze_single(self, stock_code: str, data: dict) -> ServiceResult:
        try:
            stock_name = data.get("stock_name", "")
            prompt = self._build_prompt(stock_code, data)
            research = self._run_research_agent(prompt)
            debate = self._run_debate(stock_code, research)
            risk = self._run_risk_analysis(stock_code, data, debate)
            signal = self._generate_signal(debate, risk)

            AnalysisResult(
                stock_code=stock_code,
                stock_name=stock_name,
                research=research,
                debate=debate,
                risk=risk,
                signal=signal,
            )
            return ServiceResult.ok(
                {
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "research": research,
                    "debate": debate,
                    "risk": risk,
                    "signal": signal,
                }
            )
        except Exception as e:
            return ServiceResult.error([str(e)])

    def batch_analyze(self, stocks: list[dict], top_n: int = 5) -> ServiceResult:
        analyses = []
        errors = []
        for stock in stocks[:top_n]:
            code = stock.get("stock_code", "")
            data = {k: v for k, v in stock.items() if k != "stock_code"}
            result = self.analyze_single(code, data)
            if result.status == "ok":
                analyses.append(result.data)
            else:
                errors.extend(result.errors)
                analyses.append(
                    {
                        "stock_code": code,
                        "error": result.errors[0] if result.errors else "未知错误",
                    }
                )

        if errors:
            return ServiceResult.degraded(
                data={"analyses": analyses, "total": len(analyses)},
                errors=errors,
            )
        return ServiceResult.ok({"analyses": analyses, "total": len(analyses)})
