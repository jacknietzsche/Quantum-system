"""System domain models — SystemLog, AnalysisTask, StyleSignal, ScreenResult, MigrationVersion"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.models._base import Base


class SystemLog(Base):
    __tablename__ = "system_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(10), nullable=False, default="INFO")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


class AnalysisTask(Base):
    __tablename__ = "analysis_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    stock_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    stock_name: Mapped[str] = mapped_column(String(50), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    error_msg: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    task_type: Mapped[str] = mapped_column(String(20), default="single")

    @property
    def finish_time(self) -> datetime | None:
        """Compatibility alias for finished_at."""
        return self.finished_at

    @property
    def error(self) -> str:
        """Compatibility alias for error_msg."""
        return self.error_msg or ""

    @property
    def signal(self) -> str:
        """Extract signal from result_json if available."""
        import json

        try:
            data = json.loads(self.result_json or "{}")
            return str(data.get("signal", "")) if isinstance(data, dict) else ""
        except Exception:
            return ""

    @property
    def confidence(self) -> float:
        """Extract confidence from result_json if available."""
        import json

        try:
            data = json.loads(self.result_json or "{}")
            value = data.get("confidence", 0) if isinstance(data, dict) else 0
            return float(value) if value is not None else 0.0
        except Exception:
            return 0.0


class StyleSignal(Base):
    """Per-stock screening signal — stores individual stock scoring results per style.

    NOTE: This model matches the actual DB schema (per-stock design), NOT the
    original ORM which was a run-level aggregate.  Run-level data lives in screen_result.
    """

    __tablename__ = "style_signal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    style: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    signal: Mapped[str] = mapped_column(String(10), default="")
    rank: Mapped[int] = mapped_column(Integer, default=0)
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    data_freshness: Mapped[str] = mapped_column(String(20), default="")
    source_chain: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class ScreenResult(Base):
    __tablename__ = "screen_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    style: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    market_regime: Mapped[str] = mapped_column(String(20), default="NEUTRAL")
    total_universe: Mapped[int] = mapped_column(Integer, default=0)
    stage1_passed: Mapped[int] = mapped_column(Integer, default=0)
    stage2_passed: Mapped[int] = mapped_column(Integer, default=0)
    stage3_recommended: Mapped[int] = mapped_column(Integer, default=0)
    recommendations_json: Mapped[str] = mapped_column(Text, default="[]")
    elapsed_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="completed")
    error_msg: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


class MigrationVersion(Base):
    """Database migration version tracking"""

    __tablename__ = "_migration_version"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
