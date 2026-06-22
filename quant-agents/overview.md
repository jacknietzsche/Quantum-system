# 工作流问题修复总结

## 修复了两个核心Bug

### Bug 1: 中止按钮"永远显示中止中" ✅

**根因**: 前端存在2个轮询循环的竞态条件

- `loadWorkflowStatus()` 每2秒轮询，持续显示取消按钮
- 用户点击取消后启动 `fastPoll()` 快速轮询（800ms）
- `loadWorkflowStatus` 的异步请求未取消，收到响应后 **重新显示** 取消按钮，覆盖了 `wfRestoreButtons()` 的隐藏操作
- `wfRestoreButtons()` 未重置按钮的 `disabled` 和 `textContent`，导致按钮卡在"⏳ 中止中"

**修复**:
- 新增 `_wfCancelling` 标记，cancel时阻止 `loadWorkflowStatus` 干扰
- 超时从48s延长到60s，超时后加10s保底轮询检测后台实际停止
- `wfRestoreButtons()` 完整重置按钮状态（display/disabled/textContent）
- `runWorkflow()` 启动新工作流时也重置取消按钮状态

### Bug 2: 执行日志清空无效 ✅

**根因**: `wfClearLog()` 只清空了前端DOM显示，后端 `workflow_status["logs"]` 数据仍在，下次轮询重新填充

**修复**:
- 新增后端 `POST /api/workflow/clear-logs` 端点
- `wfClearLog` 改为 async，先调用端点清空后端数据，再清空DOM
- 清空前停止所有轮询

### 额外强化: 添加 finally 保底 ✅

`run_workflow()` 的 try-except 缺少 finally，极端情况(`KeyboardInterrupt`等)下 `running` 属性永不为 False。添加 finally 保底确保无论任何异常，`running` 都会设为 `False`。

## 改动文件

| 文件 | 改动 |
|------|------|
| `web_app.py` | 新增 clear-logs 端点 + finally 保底 |
| `static/js/main.js` | 新增 _wfCancelling 标记 + 优化轮询 + 重置按钮状态 + async 清空日志 |
