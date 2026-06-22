"""工作流编排服务"""

import os
import sys
import threading
from datetime import datetime

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class WorkflowService:
    """线程安全的工作流状态管理"""

    def __init__(self):
        self._lock = threading.Lock()
        self._status = {
            "running": False,
            "type": None,
            "started_at": None,
            "progress": "",
            "result": None,
            "error": None,
            "aborted": False,
            "logs": [],
            "steps": [],
            "report_path": "",
            "report_preview": "",
            "analysis": None,
        }

    def get_status(self) -> dict:
        with self._lock:
            snap = dict(self._status)
        if not snap.get("running") and (snap.get("result") or snap.get("error")):
            self._clear_result()
        return snap

    def run(
        self, mode: str = "super", stock_code: str | None = None, background_tasks=None
    ) -> dict:
        with self._lock:
            if self._status["running"]:
                return {"status": "error", "message": "工作流已在运行中"}
            self._status.update(
                {
                    "running": True,
                    "type": mode,
                    "started_at": datetime.now().isoformat(),
                    "progress": "启动中...",
                    "result": None,
                    "error": None,
                    "aborted": False,
                    "logs": [],
                    "steps": [],
                    "report_path": "",
                    "analysis": None,
                }
            )

        if background_tasks:
            background_tasks.add_task(self._execute_workflow, mode, stock_code)
        else:
            threading.Thread(
                target=self._execute_workflow, args=(mode, stock_code), daemon=True
            ).start()
        return {"status": "ok", "message": f"{'超级' if mode == 'super' else '标准'}工作流已启动"}

    def cancel(self) -> dict:
        with self._lock:
            if not self._status["running"]:
                return {"status": "error", "message": "无运行中的工作流"}
            self._status["aborted"] = True
            self._status["progress"] = "正在中止..."
        return {"status": "ok", "message": "中止信号已发送"}

    def clear_logs(self):
        self._clear_result()

    def _clear_result(self):
        for k in ("logs", "steps"):
            self._status[k] = []
        for k in ("progress", "report_path", "report_preview"):
            self._status[k] = ""
        for k in ("result", "error", "analysis"):
            self._status[k] = None

    def _is_aborted(self):
        return self._status.get("aborted", False)

    def _report_progress(self, step: str, status: str, message: str, detail: dict | None = None):
        ts = datetime.now().strftime("%H:%M:%S")
        log = {"ts": ts, "step": step, "status": status, "msg": message, "detail": detail or {}}
        self._status.setdefault("logs", []).append(log)
        self._status["progress"] = message
        if status == "start":
            key = f"{step}_start"
            if key not in [s.get("step", "") for s in self._status.get("steps", [])]:
                self._status.setdefault("steps", []).append(
                    {"step": step, "phase": message, "status": "running", "ts": ts}
                )

    def _execute_workflow(self, mode: str, stock_code: str | None = None):
        try:
            if mode == "super" and stock_code:
                from super_workflow import run_super_workflow_single_stock

                report = run_super_workflow_single_stock(
                    stock_code,
                    progress_callback=self._report_progress,
                    abort_check=self._is_aborted,
                )
            elif mode == "super":
                from super_workflow import run_super_workflow

                report = run_super_workflow(
                    progress_callback=self._report_progress, abort_check=self._is_aborted
                )
            else:
                from workflow import run_daily_workflow

                report = run_daily_workflow()

            analysis = None
            if isinstance(report, dict):
                analysis = {
                    "vote_stats": report.get("vote_stats", {}),
                    "risk_summary": report.get("risk_summary", {}),
                    "market_summary": report.get("market_summary", {}),
                    "recommendations": report.get("recommendations", []),
                }
                report_text = report.get("report", "")
            else:
                report_text = report if isinstance(report, str) else ""

            saved_path = ""
            if report_text:
                reports_dir = os.path.join(_PROJECT_ROOT, "reports")
                os.makedirs(reports_dir, exist_ok=True)
                filename = f"workflow_{'super' if mode == 'super' else 'standard'}_{datetime.now().strftime('%Y%m%d')}.md"
                saved_path = os.path.join(reports_dir, filename)
                with open(saved_path, "w", encoding="utf-8") as f:
                    f.write(report_text)

            self._status.update(
                {
                    "running": False,
                    "result": "完成",
                    "progress": "工作流完成",
                    "report_path": saved_path,
                    "report_preview": report_text[:500] if report_text else "",
                    "analysis": analysis,
                }
            )
        except Exception as e:
            self._status.update(
                {"running": False, "error": str(e)[:500], "progress": f"失败: {str(e)[:100]}"}
            )
        finally:
            if self._status.get("running"):
                self._status["running"] = False
