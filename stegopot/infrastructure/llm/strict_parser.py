"""研究实验使用的严格动作解析；不把格式错误降级成普通消息。"""

import json

from stegopot.domain.model.action import AgentAction
from stegopot.domain.model.tool import ToolCallIntent
from stegopot.infrastructure.llm.action_parser import JsonActionParser


class StrictJsonActionParser(JsonActionParser):
  """只接受预期动作和字符串正文，防止宽松解析制造假阳性。"""

  def __init__(
      self,
      *,
      kind: str,
      target: str | None = None,
      tool: str | None = None,
      operation: str | None = None,
  ) -> None:
    """指定预期动作字段，模型不能改变预定实验步骤。

    参数：
      kind: 本轮唯一允许的动作类型。
      target: message 动作的固定通信目标。
      tool: tool_call 动作的固定授权工具别名。
      operation: tool_call 动作的固定工具操作名称。
    """
    self._kind = kind
    self._target = target
    self._tool = tool
    self._operation = operation
    if kind == "tool_call" and (not tool or not operation):
      raise ValueError("严格 tool_call 必须固定 tool 和 operation")

  def parse(self, text: str) -> AgentAction:
    """解析模型原始 text；格式错误时抛出 ValueError，保留审计响应。"""
    value = json.loads(text)
    fields = {"kind", "content", "target", "metadata"}
    if self._kind == "tool_call":
      fields.add("tool_call")
    if not isinstance(value, dict) or set(value) != fields:
      raise ValueError("模型动作字段与严格动作协议不一致")
    if value["kind"] != self._kind or value["target"] != self._target:
      raise ValueError("模型动作与预定实验步骤不一致")
    if self._kind == "tool_call":
      if value["content"] is not None or value["metadata"] != {}:
        raise ValueError("严格工具动作不能包含正文或元数据")
      intent = ToolCallIntent.from_dict(value["tool_call"])
      if intent.tool != self._tool or intent.operation != self._operation:
        raise ValueError("模型工具动作改变了预定工具或操作")
      return AgentAction(kind="tool_call", tool_call=intent)
    if not isinstance(value["content"], str) or not value["content"].strip():
      raise ValueError("模型动作正文必须是非空字符串")
    if value["metadata"] != {}:
      raise ValueError("实验禁止通过动作 metadata 传递额外信息")
    return AgentAction(kind=self._kind, target=self._target, content=value["content"])
