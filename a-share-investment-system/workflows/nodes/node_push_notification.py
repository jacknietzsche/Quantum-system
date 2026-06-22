"""Node 11: Push Notification — 推送通知"""

from workflows.nodes._shared import _log
from workflows.state import AShareSuperState
from workflows.stubs import ConfigManager


def node_push_notification(state: AShareSuperState) -> dict:
    """推送通知(控制台/飞书/企微)"""
    logs = list(state.get("logs", []))
    logs.append(_log(state, "📤 推送通知..."))

    state.get("report", "")
    recommendations = state.get("recommendations", [])

    # 控制台输出摘要
    high_priority = [
        r for r in recommendations if r.get("priority") == "高" and r["stock_code"] != "SYSTEM"
    ]
    if high_priority:
        print("\n" + "=" * 60)
        print("  🚨 高优先级操作建议:")
        print("=" * 60)
        for r in high_priority:
            print(f"  • {r['stock_name']}({r['stock_code']}): {r['action']} — {r['reason']}")
        print("=" * 60)

    # 飞书/企微推送(如果配置了webhook)
    try:
        config = ConfigManager()
        feishu_webhook = config.get("alert.feishu_webhook")
        if feishu_webhook:
            import requests

            # 发送摘要
            summary = f"A股超级投研系统 {state.get('date', '')}\n"
            summary += f"高优先级建议: {len(high_priority)}条\n"
            for r in high_priority[:5]:
                summary += f"• {r['stock_name']}: {r['action']}\n"
            requests.post(
                feishu_webhook, json={"msg_type": "text", "content": {"text": summary}}, timeout=10
            )
            logs.append(_log(state, "✅ 飞书推送成功"))
    except Exception as e:
        logs.append(_log(state, f"⚠️ 推送失败: {e}"))

    return {"logs": logs}
