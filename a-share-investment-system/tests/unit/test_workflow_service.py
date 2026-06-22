"""Tests for services.workflow - WorkflowService."""


class TestWorkflowService:
    def test_init(self):
        from services.workflow import WorkflowService

        ws = WorkflowService()
        assert ws is not None

    def test_get_status(self):
        from services.workflow import WorkflowService

        ws = WorkflowService()
        status = ws.get_status()
        assert isinstance(status, dict)

    def test_clear_logs(self):
        from services.workflow import WorkflowService

        ws = WorkflowService()
        ws.clear_logs()  # should not raise

    def test_cancel(self):
        from services.workflow import WorkflowService

        ws = WorkflowService()
        ws.cancel()  # should not raise
