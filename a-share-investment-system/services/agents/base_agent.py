"""Agent Tool calling 基础设施 - OpenAI-compatible function calling 循环"""

import json
import logging
import re as _re
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx


def extract_json(text: str) -> str:
    """Extract JSON from LLM output, handling markdown fences and embedded text"""
    text = text.strip()
    # Try markdown code block first
    m = _re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, _re.DOTALL)
    if m:
        return m.group(1)
    # Try finding JSON object directly
    m = _re.search(r"(\{.*\})", text, _re.DOTALL)
    if m:
        return m.group(1)
    return text


logger = logging.getLogger(__name__)


@dataclass
class AgentTool:
    """Agent 工具定义"""

    name: str
    description: str
    parameters: dict
    fn: Callable
    required_params: list = field(default_factory=list)

    def to_openai_tool(self) -> dict:
        def _infer_type(v):
            if isinstance(v, str):
                return "string"
            if isinstance(v, bool):
                return "boolean"
            if isinstance(v, (int, float)):
                return "number"
            return "string"  # default for dict/list

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {k: {"type": _infer_type(v)} for k, v in self.parameters.items()},
                    "required": self.required_params,
                },
            },
        }

    @staticmethod
    def create_registry() -> dict[str, "AgentTool"]:
        return {}


class AgentExecutor:
    """通用 Agent 执行器 - 支持 function calling 循环"""

    def __init__(self, llm_config: dict, tools: list[AgentTool], max_turns: int = 8):
        self.llm_config = llm_config
        self.tool_map = {t.name: t for t in tools}
        self.max_turns = max_turns

    def run(self, system_prompt: str, user_message: str) -> dict:
        """执行 agent 工具循环, 返回最终响应"""
        model_name = self.llm_config.get("model", "unknown")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        tool_defs = [t.to_openai_tool() for t in self.tool_map.values()]
        turn = 0
        with httpx.Client(timeout=60) as client:
            while turn < self.max_turns:
                turn += 1
                choice = self._call_llm(client, messages, tool_defs, model_name, turn)
                if choice is None:
                    continue
                if "error" in choice:
                    return choice

                msg = choice["message"]
                if choice.get("finish_reason") == "tool_calls":
                    self._handle_tool_calls(msg, messages)
                else:
                    return {
                        "content": msg.get("content", ""),
                        "turns": turn,
                        "finish_reason": choice.get("finish_reason"),
                    }
        return {"content": "Max turns reached", "turns": turn, "finish_reason": "max_turns"}

    def _call_llm(
        self,
        client: httpx.Client,
        messages: list,
        tool_defs: list,
        model_name: str,
        turn: int,
    ) -> dict | None:
        """Make LLM API call, return choice dict or None for retry or error dict"""
        result = None
        try:
            resp = client.post(
                f"{self.llm_config['base_url']}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.llm_config['api_key']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_name,
                    "messages": messages,
                    "tools": tool_defs,
                    "tool_choice": "auto",
                },
            )
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 2**turn))
                logger.warning(f"LLM 429 {model_name}: retry after {retry_after}s (turn {turn})")
                time.sleep(min(retry_after, 30))
            elif resp.status_code != 200:
                body = resp.text[:200]
                logger.warning(f"LLM API error {resp.status_code} on {model_name}: {body}")
                if turn < self.max_turns:
                    time.sleep(1)
                else:
                    result = {
                        "error": True,
                        "content": f"API error {resp.status_code}: {body}",
                        "turns": turn,
                        "finish_reason": "error",
                    }
            else:
                data = resp.json()
                result = data["choices"][0]
        except httpx.TimeoutException:
            logger.warning(f"LLM timeout on {model_name} (turn {turn})")
            if turn < self.max_turns:
                pass
            else:
                result = {
                    "error": True,
                    "content": "Timeout",
                    "turns": turn,
                    "finish_reason": "timeout",
                }
        except Exception as e:
            logger.warning(f"LLM error on {model_name}: {e}")
            result = {
                "error": True,
                "content": f"Error: {e}",
                "turns": turn,
                "finish_reason": "error",
            }
        return result

    def _handle_tool_calls(self, msg: dict, messages: list) -> None:
        """Process tool call responses from LLM"""
        messages.append(msg)
        for tc in msg.get("tool_calls", []):
            tool_name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}
            tool = self.tool_map.get(tool_name)
            if tool:
                try:
                    result = tool.fn(**args)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
                except Exception as e:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps({"error": str(e)}),
                        }
                    )
