"""模型输出到智能体动作的解析器。"""

from __future__ import annotations

import json
from typing import Any

from meltingpot.utils.policies.action import AgentAction


class JsonActionParser:
  """把模型输出的 JSON 对象解析为 AgentAction。

  如果模型没有输出合法 JSON，会降级为普通 message 动作，
  避免一次格式错误直接中断整个实验。
  """

  def __init__(self, *, fallback_kind: str = "message") -> None:
    """初始化解析器。

    参数：
      fallback_kind: 模型输出不是合法 JSON 时使用的默认动作类型。
    """
    self._fallback_kind = fallback_kind

  def parse(self, text: str) -> AgentAction:
    """解析模型输出文本。

    参数：
      text: 模型返回的原始文本。

    返回：
      解析得到的结构化智能体动作。
    """
    payload = self._load_json_object(text)
    if payload is None:
      fallback_content = self._optional_string(text)
      if self._fallback_kind == "message" and not fallback_content:
        return AgentAction.wait(metadata={
            "normalized_from": "empty_response",
        })
      return AgentAction(
          kind=self._fallback_kind,
          content=fallback_content,
      )
    kind = str(
        payload.get("kind") or payload.get("type") or self._fallback_kind
    ).strip().lower()
    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
      metadata = {"raw_metadata": metadata}
    content = self._optional_string(payload.get("content"))
    target = self._optional_string(payload.get("target"))
    if kind == "message" and not content:
      return AgentAction.wait(metadata={
          **metadata,
          "normalized_from": "empty_message",
      })
    return AgentAction(
        kind=kind,
        content=content,
        target=target,
        metadata=metadata,
    )

  def _load_json_object(self, text: str) -> dict[str, Any] | None:
    """从文本中读取一个 JSON 对象。

    参数：
      text: 可能包含 JSON 对象的文本。

    返回：
      解析得到的字典；无法解析时返回 None。
    """
    try:
      value = json.loads(text)
    except json.JSONDecodeError:
      start = text.find("{")
      end = text.rfind("}")
      if start < 0 or end <= start:
        return None
      try:
        value = json.loads(text[start:end + 1])
      except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
      return None
    return value

  @staticmethod
  def _optional_string(value: Any) -> str | None:
    """把可选 JSON 字段规范化为非空字符串或 None。

    参数：
      value: 模型 JSON 中的 content 或 target 字段值。

    返回：
      去除首尾空白后的字符串；值为空时返回 None。
    """
    if value is None:
      return None
    normalized = str(value).strip()
    return normalized or None
