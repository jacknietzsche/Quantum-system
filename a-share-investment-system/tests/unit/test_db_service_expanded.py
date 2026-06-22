"""Expanded tests for shared/db_service.py."""

from __future__ import annotations


class TestDbServiceExpanded:
    def test_module_importable(self):
        import shared.db_service as dbs

        assert dbs is not None
