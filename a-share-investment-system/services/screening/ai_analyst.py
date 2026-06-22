"""AI 基本面分析师 — 在财务数据缺失时通过有限信息推理评分

核心思路: 不依赖精确 ROE/EPS/毛利率, 而是利用:
  1. 股价走势与行业对比 → 相对强度
  2. 公告/新闻标题摘要 (如有) → 基本面信号
  3. 量价行为模式 → 市场隐含预期

所有评分 0-10, None 表示无法判断 (不贡献分数)
"""

import json
import logging

logger = logging.getLogger(__name__)


def score_from_available_data(stock: dict) -> dict:
    """基于可用数据推理基本面质量 (0-10分, 无需AI)

    当AI不可用或无需AI时, 用规则推理基本面分数。
    """
    score = 5.0  # 默认中性
    signals = []

    # 1. PE信号: 即使PE缺失也能推理
    pe = stock.get("pe", 0)
    if pe > 0:
        if pe < 15:
            score += 1.5
            signals.append("PE偏低(低估)")
        elif pe < 25:
            score += 0.5
            signals.append("PE合理")
        elif pe > 80:
            score -= 0.5
            signals.append("PE偏高(警惕)")

    # 2. 市值信号: 大盘股默认基本面更可靠
    mc = stock.get("market_cap", 0)
    if mc >= 500:
        score += 1.0
        signals.append("大盘股")
    elif mc >= 100:
        score += 0.5
        signals.append("中盘股")
    elif mc > 0 and mc < 30:
        score -= 0.5
        signals.append("小盘微盘")

    # 3. 流动性信号: 成交额反映市场认可度
    amt = stock.get("amount", 0)
    if amt >= 5e8:
        score += 1.0
        signals.append("成交活跃(市场关注)")
    elif amt >= 1e8:
        score += 0.5
        signals.append("成交正常")

    # 4. 换手率信号: 过低=僵尸, 过高=投机
    tr = stock.get("turnover_rate", 0)
    if tr > 0:
        if tr < 0.3:
            score -= 0.5
            signals.append("换手率极低")
        elif tr > 20:
            score -= 0.5
            signals.append("换手率过高(投机)")

    # 5. 趋势信号: 上涨趋势反映基本面向好
    chg = stock.get("change_pct", 0)
    if chg > 3:
        score += 0.5
        signals.append("近期走强")
    elif chg < -5:
        score -= 0.5
        signals.append("近期走弱")

    return {
        "score": max(0, min(10, score)),
        "signals": signals,
        "basis": len(signals),
        "method": "rule",
    }


def score_with_llm(stock: dict) -> dict:
    """用LLM评估基本面 (可选, 需配置LLM)

    读取股票的可公开信息, 让AI推理基本面质量。
    当前是轻量版, 仅基于stock dict字段推理。
    """
    try:
        from llm_clients.factory import get_client_for_role

        client = get_client_for_role("secondary")
        if client is None:
            return score_from_available_data(stock)

        code = stock.get("stock_code", "")
        name = stock.get("stock_name", "")
        industry = stock.get("industry", "")
        pe = stock.get("pe", 0)
        mc = stock.get("market_cap", 0)
        price = stock.get("latest_price", 0)
        chg = stock.get("change_pct", 0)
        tr = stock.get("turnover_rate", 0)

        prompt = f"""你是A股基本面分析师。基于以下有限信息, 对该股票基本面质量评分 (0-10):

股票: {name} ({code})
行业: {industry}
价格: {price}, 近期涨幅: {chg}%
市值: {mc}亿
PE: {pe}, 换手率: {tr}%

请输出JSON:
{{"score": 0-10, "reason": "一段简短推理", "risk": "主要风险"}}
注意: 在数据有限时, 用你对中国股票市场的知识弥补。"""
        resp = client.chat(prompt, temperature=0.3, max_tokens=200)
        text = resp.get("text", "") if isinstance(resp, dict) else ""
        if not text:
            return score_from_available_data(stock)

        # 尝试解析JSON
        try:
            result = json.loads(text)
            return {
                "score": max(0, min(10, float(result.get("score", 5)))),
                "reason": result.get("reason", ""),
                "risk": result.get("risk", ""),
                "method": "llm",
            }
        except (json.JSONDecodeError, ValueError, TypeError):
            # 回退到规则评分
            return score_from_available_data(stock)

    except Exception as e:
        logger.debug("[AIAnalyst] LLM fallback to rule: %s", e)
        return score_from_available_data(stock)


def batch_assess(stocks: list[dict], use_llm: bool = False) -> dict[str, dict]:
    """批量评估股票基本面

    Args:
        stocks: 股票字典列表
        use_llm: 是否使用LLM (默认False, 用规则评分)

    Returns:
        {stock_code: {score, signals, method}}
    """
    results = {}
    for stock in stocks:
        code = stock.get("stock_code", "")
        if use_llm:
            results[code] = score_with_llm(stock)
        else:
            results[code] = score_from_available_data(stock)
    return results
