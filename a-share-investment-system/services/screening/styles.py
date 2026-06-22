"""选股风格配置 — 从 stock_screener.py._load_config() 拆分

每种风格的 Stage1/2/3/4 参数集中管理，消除 if/else 分支。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Stage1Config:
    """Stage1: 行为活性过滤配置"""

    top_n: int = 200
    score_min: int = 3
    turnover_min: float = 0.3  # 最低换手率
    market_cap_min: float = 10  # 最低市值(亿)
    max_market_cap: float = 999999.0
    volatility_max: float = 99.0
    st_filter: bool = True
    require_ma_uptrend: bool = False
    use_zzshare_factors: bool = True


@dataclass
class Stage2Config:
    """Stage2: 四维评分配置 (趋势/资金/AI基本面/防御)"""

    top_n: int = 30
    score_min: int = 4  # 与 hybrid 风格默认值保持一致
    min_volume_ratio: float = 0.0
    min_roe: float = 0.0
    roe_high: float = 25.0
    roe_medium: float = 15.0
    roe_low: float = 10.0
    min_revenue_growth: float = -999.0
    min_gross_margin: float = 0.0
    max_debt_to_equity: float = 999.0
    max_pe: float = 999.0
    max_pb: float = 999.0
    min_fcf: float = -999999.0
    min_cagr: float = -999.0
    use_zzshare_factors: bool = True


@dataclass
class Stage3Config:
    deep_top: int = 15
    final_top: int = 8
    max_bias_ma5: float = 999.0
    min_trend_strength: float = 0.0
    require_mos: float = 0.0
    weights: dict = field(
        default_factory=lambda: {
            "buffett": 0.35,
            "graham": 0.20,
            "lynch": 0.25,
            "taleb": 0.20,
        }
    )
    # 增强 Stage3 使用的 Master Agent 名称
    master_agents: list[str] = field(default_factory=list)


@dataclass
class Stage4Config:
    enabled: bool = False
    top_n: int = 5
    model: str = "siliconflow:deepseek-ai/DeepSeek-R1"
    temperature: float = 0.7
    max_tokens: int = 4000
    skills: list[str] = field(default_factory=list)
    workflow: list[str] = field(default_factory=lambda: ["research", "debate", "risk", "signal"])


@dataclass
class StyleConfig:
    """一种选股风格的完整配置"""

    name: str = "hybrid"
    stage1: Stage1Config = field(default_factory=Stage1Config)
    stage2: Stage2Config = field(default_factory=Stage2Config)
    stage3: Stage3Config = field(default_factory=Stage3Config)
    stage4: Stage4Config = field(default_factory=Stage4Config)


def load_style_config(style: str, config: Any = None) -> StyleConfig:
    """从配置源加载指定风格的配置。"""
    if config is None:
        from shared.config import Config

        config = Config()

    sc = StyleConfig(name=style)

    if style == "hybrid":
        sc.stage1 = Stage1Config(
            top_n=config.get("screening.stage1.top_n", 200),
            score_min=config.get("screening.stage1.score_min", 3),
            turnover_min=config.get("screening.stage1.turnover_min", 0.3),
            market_cap_min=config.get("screening.stage1.market_cap_min", 20),
            volatility_max=config.get("screening.stage1.volatility_max", 30),
        )
        sc.stage2 = Stage2Config(
            top_n=config.get("screening.stage2.top_n", 30),
            score_min=config.get("screening.stage2.score_min", 4),
            roe_high=config.get("screening.stage2.roe_high", 25),
            roe_medium=config.get("screening.stage2.roe_medium", 15),
            roe_low=config.get("screening.stage2.roe_low", 10),
        )
        w = config.get("screening.stage3.weights", {})
        sc.stage3 = Stage3Config(
            deep_top=config.get("screening.stage3.deep_top", 15),
            final_top=config.get("screening.stage3.final_top", 8),
            weights=w if w else {"buffett": 0.35, "graham": 0.20, "lynch": 0.25, "taleb": 0.20},
        )
        s4 = config.get("screening.styles.hybrid.stage4", {})
        sc.stage4 = Stage4Config(
            **{k: v for k, v in s4.items() if k in Stage4Config.__dataclass_fields__}
        )
    else:
        cfg = config.get(f"screening.styles.{style}", {})
        s1 = cfg.get("stage1", {})
        sc.stage1 = Stage1Config(
            **{k: v for k, v in s1.items() if k in Stage1Config.__dataclass_fields__}
        )
        s2 = cfg.get("stage2", {})
        sc.stage2 = Stage2Config(
            **{k: v for k, v in s2.items() if k in Stage2Config.__dataclass_fields__}
        )
        s3 = cfg.get("stage3", {})
        sc.stage3 = Stage3Config(
            **{k: v for k, v in s3.items() if k in Stage3Config.__dataclass_fields__}
        )
        s4 = cfg.get("stage4", {})
        sc.stage4 = Stage4Config(
            **{k: v for k, v in s4.items() if k in Stage4Config.__dataclass_fields__}
        )

    # 设置风格特定的 Master Agent 列表
    _STYLE_AGENTS = {
        "limit_up": ["limit_up_master", "cathie_wood", "michael_burry"],
        "momentum": ["momentum_master", "peter_lynch_growth", "cathie_wood"],
    }
    if style in _STYLE_AGENTS:
        sc.stage3.master_agents = _STYLE_AGENTS[style]

    return sc
