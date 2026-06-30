#!/usr/bin/env python
"""AShare-X 统一测试运行器 — 一键运行所有层级的测试。

执行顺序:
  1. Lint (ruff check)
  2. 后端单元测试 (pytest tests/unit/)
  3. API契约测试 (pytest tests/integration/test_api_contract.py)
  4. 前端单元测试 (vitest run)
  5. E2E浏览器测试 (playwright test)

用法:
  python run_all_tests.py              # 运行全部
  python run_all_tests.py --skip-e2e  # 跳过E2E（需要浏览器）
  python run_all_tests.py --backend   # 仅后端
  python run_all_tests.py --frontend  # 仅前端
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
ELECTRON_DIR = PROJECT_ROOT / "electron"


class TestRunner:
    def __init__(self):
        self.results: list[tuple[str, bool, float, str]] = []

    def run_step(self, name: str, cmd: list[str], cwd: Path, env: dict | None = None) -> bool:
        print(f"\n{'=' * 60}")
        print(f"  > {name}")
        print(f"{'=' * 60}")

        start = time.time()
        import os

        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        result = subprocess.run(
            cmd, cwd=str(cwd), env=full_env, capture_output=False
        )
        elapsed = time.time() - start

        passed = result.returncode == 0
        status = "[PASS]" if passed else "[FAIL]"
        self.results.append((name, passed, elapsed, status))

        print(f"\n  {status} ({elapsed:.1f}s)")
        return passed

    def print_summary(self):
        print(f"\n\n{'=' * 60}")
        print("  Test Results Summary")
        print(f"{'=' * 60}")

        all_passed = True
        for name, passed, elapsed, status in self.results:
            icon = "[OK]" if passed else "[XX]"
            print(f"  {icon} {name:<40} {elapsed:>6.1f}s")
            if not passed:
                all_passed = False

        total_time = sum(r[2] for r in self.results)
        result_str = "ALL PASSED" if all_passed else "FAILURES EXIST"
        print(f"\n  Total: {total_time:.1f}s  Result: {result_str}")
        print(f"{'=' * 60}")

        return all_passed


def main():
    parser = argparse.ArgumentParser(description="AShare-X 统一测试运行器")
    parser.add_argument("--skip-e2e", action="store_true", help="跳过E2E浏览器测试")
    parser.add_argument("--backend", action="store_true", help="仅运行后端测试")
    parser.add_argument("--frontend", action="store_true", help="仅运行前端测试")
    args = parser.parse_args()

    runner = TestRunner()
    run_backend = not args.frontend
    run_frontend = not args.backend
    run_e2e = not args.skip_e2e and not args.backend and not args.frontend

    # 1. Lint
    if run_backend:
        runner.run_step(
            "Ruff Lint",
            [sys.executable, "-m", "ruff", "check", "."],
            PROJECT_ROOT,
        )

    # 2. Backend unit tests
    if run_backend:
        runner.run_step(
            "后端单元测试",
            [sys.executable, "-m", "pytest", "tests/unit/", "-v", "--no-cov", "--timeout=30"],
            PROJECT_ROOT,
        )

    # 3. API contract tests
    if run_backend:
        runner.run_step(
            "API契约测试",
            [
                sys.executable, "-m", "pytest",
                "tests/integration/test_api_contract.py", "-v",
                "--no-cov", "--timeout=30",
            ],
            PROJECT_ROOT,
        )

    # 4. Frontend unit tests
    if run_frontend:
        runner.run_step(
            "前端单元测试 (Vitest)",
            ["npx", "vitest", "run"],
            ELECTRON_DIR,
            env={"NODE_ENV": "development"},
        )

    # 5. E2E browser tests
    if run_e2e:
        runner.run_step(
            "E2E浏览器测试 (Playwright)",
            ["npx", "playwright", "test", "--timeout=60000"],
            ELECTRON_DIR,
            env={"NODE_ENV": "development"},
        )

    all_passed = runner.print_summary()
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
