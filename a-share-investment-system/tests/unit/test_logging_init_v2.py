"""Unit tests for agents_v2.utils.logging_init."""

import logging


def test_get_logger_returns_logger():
    from agents_v2.utils.logging_init import get_logger

    logger = get_logger("test_v2_unique")
    assert isinstance(logger, logging.Logger)


def test_get_logger_caches():
    from agents_v2.utils.logging_init import get_logger

    l1 = get_logger("cached_test_xyz")
    l2 = get_logger("cached_test_xyz")
    assert l1 is l2


def test_get_logger_with_level():
    from agents_v2.utils.logging_init import get_logger

    logger = get_logger("level_test_xyz", level=logging.DEBUG)
    assert isinstance(logger, logging.Logger)


def test_set_debug_mode():
    from agents_v2.utils.logging_init import set_debug_mode

    set_debug_mode(True)
    assert logging.getLogger().level == logging.DEBUG
    set_debug_mode(False)
    assert logging.getLogger().level == logging.INFO


def test_convenience_loggers():
    from agents_v2.utils.logging_init import (
        get_agents_logger,
        get_graph_logger,
        get_llm_logger,
        get_memory_logger,
    )

    assert isinstance(get_agents_logger(), logging.Logger)
    assert isinstance(get_graph_logger(), logging.Logger)
    assert isinstance(get_memory_logger(), logging.Logger)
    assert isinstance(get_llm_logger(), logging.Logger)
