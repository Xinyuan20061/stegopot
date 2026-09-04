"""智能体动作结构。"""

from __future__ import annotations

from collections.abc import Mapping
import dataclasses
from types import MappingProxyType
from typing import Any


BROADCAST_TARGETS = frozenset({"*", "broadcast", "all"})


@dataclasses.dataclass(frozen=True)
class AgentAction:
  """智能体输出给环境的一次结构化动作。

  属性：
    kind: 动作类型，例如 "message"、"wait"、"audit" 或 "final_answer"。
    content: 动作正文，例如消息文本或审计结论。
    target: 动作目标，例如接收者 ID；广播或无目标动作可以为空。
    metadata: 附加元数据，供环境、记录器或评估器使用。
  """

  kind: str
  content: str | None = None
  target: str | None = None
  metadata: Mapping[str, Any] = dataclasses.field(default_factory=dict)

  def __post_init__(self) -> None:
    object.__setattr__(self, "metadata",
                       MappingProxyType(dict(self.metadata)))

  @classmethod
  def wait(cls, *, metadata: Mapping[str, Any] | None = None) -> "AgentAction":
    """创建等待动作。

    参数：
      metadata: 附加元数据。

    返回：
      等待动作对象。
    """
    return cls(kind="wait", metadata=metadata or {})

  @classmethod
  def message(
      cls,
      content: str,
      *,
      target: str | None = None,
      metadata: Mapping[str, Any] | None = None,
  ) -> "AgentAction":
    """创建消息动作。

    参数：
      content: 消息正文。
      target: 消息接收目标；为空时由环境决定是否广播。
      metadata: 附加元数据。

    返回：
      消息动作对象。
    """
    return cls(
        kind="message",
        content=content,
        target=target,
        metadata=metadata or {},
    )

  @classmethod
  def audit(
      cls,
      content: str,
      *,
      target: str | None = None,
      metadata: Mapping[str, Any] | None = None,
  ) -> "AgentAction":
    """创建审计动作。

    参数：
      content: 审计结论或审计说明。
      target: 被审计目标；为空时表示不指定目标。
      metadata: 附加元数据。

    返回：
      审计动作对象。
    """
    return cls(
        kind="audit",
        content=content,
        target=target,
        metadata=metadata or {},
    )

  @classmethod
  def final_answer(
      cls,
      content: str,
      *,
      metadata: Mapping[str, Any] | None = None,
  ) -> "AgentAction":
    """创建最终答案动作。

    参数：
      content: 最终答案正文。
      metadata: 附加元数据。

    返回：
      最终答案动作对象。
    """
    return cls(kind="final_answer", content=content, metadata=metadata or {})
