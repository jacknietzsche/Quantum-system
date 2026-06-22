"""
A股超级智能投研系统 - 统一 LangGraph 超级工作流
融合所有 Agent + Skill -> 统一决策系统

节点实现已拆分到 workflows/nodes/ 各独立文件。
本文件为向后兼容的导入包装器。
"""

from workflows.nodes import run_super_workflow

if __name__ == "__main__":
    run_super_workflow()
