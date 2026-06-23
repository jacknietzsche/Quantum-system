"""定时调度命令单元测试。"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from main import _is_trading_day, cmd_schedule


class TestTradingDay:
    def test_weekday_is_trading_day(self):
        assert _is_trading_day(datetime(2026, 6, 23)) is True  # 周二

    def test_saturday_not_trading_day(self):
        assert _is_trading_day(datetime(2026, 6, 20)) is False  # 周六

    def test_sunday_not_trading_day(self):
        assert _is_trading_day(datetime(2026, 6, 21)) is False  # 周日


class TestScheduleCommand:
    def test_schedule_once_runs_jobs_and_returns(self):
        with (
            patch("main.cmd_daily") as mock_daily,
            patch("main.cmd_screen"),
            patch("main.cmd_plan"),
            patch("schedule.run_all") as mock_run_all,
        ):
            cmd_schedule(once=True)
            mock_run_all.assert_called_once()
            # 三个任务已注册，但 once 模式下不直接调用业务函数
            assert not mock_daily.called

    def test_schedule_registers_three_jobs(self):
        import schedule

        # 清空现有任务，避免其他测试干扰
        schedule.clear()
        with (
            patch("main.cmd_daily"),
            patch("main.cmd_screen"),
            patch("main.cmd_plan"),
        ):
            # 使用 once=True 避免进入常驻循环
            cmd_schedule(once=True)
            jobs = schedule.get_jobs()
            assert len(jobs) == 3
            schedule.clear()

    def test_weekend_job_is_skipped(self):
        import schedule

        schedule.clear()
        with (
            patch("main._is_trading_day", return_value=False),
            patch("main.cmd_daily") as mock_daily,
            patch("main.cmd_screen"),
            patch("main.cmd_plan"),
            patch("builtins.print") as mock_print,
        ):
            # once=True 会立即执行所有已注册任务
            cmd_schedule(once=True)
            assert not mock_daily.called
            assert any("跳过（非交易日）" in str(call) for call in mock_print.call_args_list)
        schedule.clear()
