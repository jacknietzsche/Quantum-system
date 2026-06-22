"""Test Phase 4: DynamicConfigEngine + VectorMemory"""

import os
import sys

# Ensure project root is on sys.path for direct runs
_proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

from services.screening.dynamic_config import DynamicConfigEngine
from services.screening.styles import StyleConfig, load_style_config
from services.screening.vector_memory import VectorMemory

# ── DynamicConfigEngine ──────────────────────────────────────


class TestDynamicConfigEngine:
    """动态配置引擎测试"""

    def _make_bull_state(self) -> dict:
        return {
            "regime": "BULL",
            "composite_score": 1.5,
            "strategy_bias": "momentum",
            "adjustment": {
                "stage1_top": 1.5,
                "stage2_top": 1.3,
                "stage3_top": 1.2,
            },
        }

    def _make_bear_state(self) -> dict:
        return {
            "regime": "BEAR",
            "composite_score": -1.0,
            "strategy_bias": "defensive",
            "adjustment": {
                "stage1_top": 0.7,
                "stage2_top": 0.8,
                "stage3_top": 0.9,
            },
        }

    def _make_base_config(self) -> StyleConfig:
        """使用与生产一致的风格配置加载路径"""
        return load_style_config("hybrid")

    def test_bull_market_top_n(self):
        """牛市场景: Stage1 top_n = 200 * 1.5 = 300"""
        engine = DynamicConfigEngine()
        base = self._make_base_config()
        adjusted = engine.generate(self._make_bull_state(), base)
        assert adjusted.stage1.top_n == 300

    def test_bull_market_stage2(self):
        """牛市场景: Stage2 top_n = min(100, 30 * 1.3) = 39"""
        engine = DynamicConfigEngine()
        base = self._make_base_config()
        adjusted = engine.generate(self._make_bull_state(), base)
        assert adjusted.stage2.top_n == 39
        assert adjusted.stage2.score_min == 5

    def test_bull_market_stage3(self):
        """牛市场景: Stage3 deep_top = min(30, 15 * 1.2) = 18"""
        engine = DynamicConfigEngine()
        base = self._make_base_config()
        adjusted = engine.generate(self._make_bull_state(), base)
        assert adjusted.stage3.deep_top == 18

    def test_bear_market_top_n(self):
        """熊市场景: Stage1 top_n = max(50, 200 * 0.7) = 140"""
        engine = DynamicConfigEngine()
        base = self._make_base_config()
        adjusted = engine.generate(self._make_bear_state(), base)
        assert adjusted.stage1.top_n == 140

    def test_bear_market_stage2(self):
        """熊市场景: Stage2 top_n = max(10, 30 * 0.8) = 24"""
        engine = DynamicConfigEngine()
        base = self._make_base_config()
        adjusted = engine.generate(self._make_bear_state(), base)
        assert adjusted.stage2.top_n == 24
        assert adjusted.stage2.score_min == 3
        assert adjusted.stage2.min_roe >= 5.0
        assert adjusted.stage2.max_pe <= 20.0

    def test_does_not_modify_original(self):
        """generate() 应返回新对象, 不修改原配置"""
        engine = DynamicConfigEngine()
        original = self._make_base_config()
        adjusted = engine.generate(self._make_bull_state(), original)
        assert adjusted is not original
        assert original.stage1.top_n == 200
        assert original.stage2.top_n == 30
        assert original.stage3.deep_top == 15
        assert original.stage2.score_min == 4
        assert original.stage2.min_roe == 0.0
        assert original.stage2.max_pe == 999.0

    def test_empty_market_state_fallback(self):
        """空 market_state 时应返回默认配置 (安全降级)"""
        engine = DynamicConfigEngine()
        result = engine.generate({}, self._make_base_config())
        assert result.stage1.top_n == 200

    def test_agent_weights_normalized(self):
        """Agent 权重总和应归一化为 1.0"""
        engine = DynamicConfigEngine()
        adjusted = engine.generate(self._make_bull_state(), self._make_base_config())
        total = sum(adjusted.stage3.weights.values())
        assert abs(total - 1.0) < 0.01

    def test_neutral_market(self):
        """震荡市场: 保守调整"""
        engine = DynamicConfigEngine()
        state = {
            "regime": "NEUTRAL",
            "composite_score": 0.1,
            "strategy_bias": "value",
            "adjustment": {
                "stage1_top": 1.0,
                "stage2_top": 1.0,
                "stage3_top": 1.0,
            },
        }
        adjusted = engine.generate(state, self._make_base_config())
        # NEUTRAL 应接近默认值
        assert adjusted.stage1.top_n == max(50, int(200 * 1.0))
        assert adjusted.stage2.top_n == max(15, int(30 * 1.0))

    def test_panic_market_strict_filters(self):
        """恐慌市场: 强制 PE/ROE 过滤"""
        engine = DynamicConfigEngine()
        state = {
            "regime": "PANIC",
            "composite_score": -2.0,
            "strategy_bias": "defensive",
            "adjustment": {
                "stage1_top": 0.5,
                "stage2_top": 0.6,
                "stage3_top": 0.7,
            },
        }
        adjusted = engine.generate(state, self._make_base_config())
        assert adjusted.stage1.top_n == max(50, int(200 * 0.5))
        assert adjusted.stage2.min_roe >= 5.0
        assert adjusted.stage2.max_pe <= 20.0


# ── VectorMemory ────────────────────────────────────────────


class TestVectorMemory:
    """向量记忆检索测试"""

    def test_encode_bull(self):
        """牛市状态应编码为 strong/strong"""
        vm = VectorMemory()
        tags = vm.encode_market(
            {
                "regime": "BULL",
                "composite_score": 1.5,
                "strategy_bias": "momentum",
                "breadth": {"up_ratio": 0.7},
            }
        )
        assert tags["regime"] == "BULL"
        assert tags["score_bucket"] == "strong"
        assert tags["bias"] == "momentum"
        assert tags["breadth"] == "strong"

    def test_encode_bear(self):
        """熊市状态应正确编码"""
        vm = VectorMemory()
        tags = vm.encode_market(
            {
                "regime": "BEAR",
                "composite_score": -1.5,
                "strategy_bias": "defensive",
                "breadth": {"up_ratio": 0.2},
            }
        )
        assert tags["regime"] == "BEAR"
        assert tags["score_bucket"] == "extreme"

    def test_encode_neutral(self):
        """震荡状态应编码为 neutral/normal"""
        vm = VectorMemory()
        tags = vm.encode_market(
            {
                "regime": "NEUTRAL",
                "composite_score": 0.1,
                "strategy_bias": "value",
                "breadth": {"up_ratio": 0.45},
            }
        )
        assert tags["regime"] == "NEUTRAL"
        assert tags["score_bucket"] == "neutral"
        assert tags["breadth"] == "normal"

    def test_search_returns_list(self):
        """无历史记忆时 search 应返回空列表"""
        vm = VectorMemory()
        results = vm.search(
            {
                "regime": "BULL",
                "composite_score": 1.5,
                "strategy_bias": "momentum",
                "breadth": {"up_ratio": 0.7},
            }
        )
        assert isinstance(results, list)

    def test_malformed_breadth(self):
        """异常 breadth 输入不应崩溃"""
        vm = VectorMemory()
        result = vm.encode_market(
            {
                "regime": "BULL",
                "composite_score": 1.0,
                "strategy_bias": "momentum",
                "breadth": None,
            }
        )
        assert result["breadth"] == "normal"
