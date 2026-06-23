"""db/migrations.py 单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from db import migrations


@pytest.fixture()
def tmp_engine(tmp_path: Path):
    """创建临时 SQLite 引擎。"""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    yield engine
    engine.dispose()


@pytest.fixture()
def patched_migrations(tmp_engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """将迁移模块指向临时引擎和临时迁移目录。"""
    monkeypatch.setattr(migrations, "get_engine", lambda: tmp_engine)
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    monkeypatch.setattr(migrations, "MIGRATIONS_DIR", migrations_dir)
    return migrations_dir


class TestGetCurrentVersion:
    """get_current_version 测试。"""

    def test_no_table_returns_zero(self, patched_migrations, tmp_engine):
        assert migrations.get_current_version() == 0

    def test_returns_max_version(self, patched_migrations, tmp_engine):
        with tmp_engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE _migration_version (version INTEGER PRIMARY KEY, description TEXT)"
            ))
            conn.execute(text(
                "INSERT INTO _migration_version (version, description) VALUES (1, 'init'), (3, 'add')"
            ))
            conn.commit()

        assert migrations.get_current_version() == 3


class TestApplyMigration:
    """apply_migration 测试。"""

    def test_applies_new_migration(self, patched_migrations, tmp_engine):
        # 先创建版本表
        migrations.apply_pending_migrations()

        result = migrations.apply_migration(
            1, "create_users", "CREATE TABLE users (id INTEGER PRIMARY KEY)"
        )

        assert result is True
        with tmp_engine.connect() as conn:
            tables = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
            )).fetchall()
            assert len(tables) == 1

    def test_skips_already_applied(self, patched_migrations, tmp_engine):
        migrations.apply_pending_migrations()
        migrations.apply_migration(1, "init", "SELECT 1")

        result = migrations.apply_migration(1, "init", "SELECT 1")
        assert result is False


class TestApplyPendingMigrations:
    """apply_pending_migrations 测试。"""

    def test_creates_version_table(self, patched_migrations, tmp_engine):
        migrations.apply_pending_migrations()
        with tmp_engine.connect() as conn:
            tables = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='_migration_version'"
            )).fetchall()
            assert len(tables) == 1

    def test_applies_multiple_migrations(self, patched_migrations, tmp_engine):
        (patched_migrations / "v001_init.sql").write_text(
            "CREATE TABLE t1 (id INTEGER PRIMARY KEY)", encoding="utf-8"
        )
        (patched_migrations / "v002_add_col.sql").write_text(
            "ALTER TABLE t1 ADD COLUMN name TEXT", encoding="utf-8"
        )

        applied = migrations.apply_pending_migrations()
        assert applied == 2

        with tmp_engine.connect() as conn:
            cols = conn.execute(text("PRAGMA table_info(t1)")).fetchall()
            assert any(c[1] == "name" for c in cols)

    def test_skips_applied_migrations(self, patched_migrations, tmp_engine):
        (patched_migrations / "v001_init.sql").write_text(
            "CREATE TABLE t2 (id INTEGER PRIMARY KEY)", encoding="utf-8"
        )

        assert migrations.apply_pending_migrations() == 1
        assert migrations.apply_pending_migrations() == 0

    def test_ignores_invalid_filenames(self, patched_migrations, tmp_engine):
        (patched_migrations / "v001_valid.sql").write_text(
            "CREATE TABLE t3 (id INTEGER PRIMARY KEY)", encoding="utf-8"
        )
        (patched_migrations / "not_a_migration.sql").write_text(
            "SELECT 1", encoding="utf-8"
        )
        (patched_migrations / "vABC_invalid.sql").write_text(
            "SELECT 1", encoding="utf-8"
        )

        applied = migrations.apply_pending_migrations()
        assert applied == 1

    def test_description_parsed_from_filename(self, patched_migrations, tmp_engine):
        (patched_migrations / "v001_create_orders.sql").write_text(
            "CREATE TABLE orders (id INTEGER PRIMARY KEY)", encoding="utf-8"
        )

        migrations.apply_pending_migrations()

        with tmp_engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT description FROM _migration_version WHERE version=1"
            )).fetchall()
            assert rows[0][0] == "create_orders"
