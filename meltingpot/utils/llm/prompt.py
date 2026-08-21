"""提示词构造工具。"""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from meltingpot.utils.llm.client import LLMMessage


class PromptBuilder:
  """把环境观察和节点状态转换成模型消息。"""

  def __init__(self, *, system_prompt: str = "") -> None:
    """初始化提示词构造器。

    参数：
      system_prompt: 额外系统提示词，会放在通用格式约束之前。
    """
    self._system_prompt = system_prompt.strip()

  def build(
      self,
      *,
      node_id: str,
      role: str,
      observation: Any,
      memory: Mapping[str, Any],
      step_count: int,
  ) -> tuple[LLMMessage, ...]:
    """构造一次模型调用所需的消息。

    参数：
      node_id: 当前智能体节点 ID。
      role: 当前智能体在实验中的角色。
      observation: 当前环境观察。
      memory: 当前节点内部记忆。
      step_count: 当前节点已经执行过的步数。

    返回：
      发送给模型的消息序列。
    """
    system_content = "\n".join(
        part for part in [
            self._system_prompt,
            "你是一个可被多智能体实验框架调度的智能体节点。",
            "你必须只输出一个 JSON 对象，不要输出额外解释。",
            (
                'JSON 字段固定为：'
                '{"kind": 动作类型, "content": 内容, '
                '"target": 目标, "metadata": 元数据对象}。'
            ),
            (
                'kind 可使用 "message"、"wait" 或 "final_answer"。'
                '发送消息时，target 必须是观察中列出的 outgoing_neighbors；'
                'target 为 null 或 "*" 表示向全部出邻居广播。'
            ),
            (
                '没有需要发送的内容时使用 wait；任务已经完成时使用 '
                'final_answer，并把最终结果放入 content。'
            ),
        ] if part
    )
    user_content = "\n\n".join([
        f"节点 ID：{node_id}",
        f"角色：{role}",
        f"当前步数：{step_count}",
        f"内部记忆：{self._format_value(memory)}",
        f"环境观察：{self._format_value(observation)}",
    ])
    return (
        LLMMessage(role="system", content=system_content),
        LLMMessage(role="user", content=user_content),
    )

  def _format_value(self, value: Any) -> str:
    """把任意 Python 值转换成稳定、易读的文本。

    参数：
      value: 需要放入提示词的 Python 值。

    返回：
      JSON 优先、字符串兜底的文本表示。
    """
    try:
      return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except TypeError:
      return str(value)
