"""研究实验使用的严格动作解析；不把格式错误降级成普通消息。"""

import json

from stegopot.domain.model.action import AgentAction
from stegopot.infrastructure.llm.action_parser import JsonActionParser


class StrictJsonActionParser(JsonActionParser):
  """只接受预期动作和字符串正文，防止宽松解析制造假阳性。"""

  def __init__(self, *, kind: str, target: str | None = None) -> None:
    """指定预期 kind 和 target；模型不能改变预定实验步骤。"""
    self._kind = kind
    self._target = target

  def parse(self, text: str) -> AgentAction:
    """解析模型原始 text；格式错误时抛出 ValueError，保留审计响应。"""
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != {"kind", "content", "target", "metadata"}:
      raise ValueError("模型动作必须包含且仅包含 kind/content/target/metadata")
    if value["kind"] != self._kind or value["target"] != self._target:
      raise ValueError("模型动作与预定实验步骤不一致")
    if not isinstance(value["content"], str) or not value["content"].strip():
      raise ValueError("模型动作正文必须是非空字符串")
    if value["metadata"] != {}:
      raise ValueError("实验禁止通过动作 metadata 传递额外信息")
    return AgentAction(kind=self._kind, target=self._target, content=value["content"])
