"""智能体动作结构。"""

from __future__ import annotations

from collections.abc import Mapping
import dataclasses
from types import MappingProxyType
from typing import Any

from stegopot.domain.model.communication import CommunicationIntent
from stegopot.domain.model.tool import ToolCallIntent


BROADCAST_TARGETS = frozenset({"*", "broadcast", "all"})


@dataclasses.dataclass(frozen=True)
class AgentAction:
  """智能体输出给环境的一次结构化动作。

  属性：
    kind: 动作类型，例如 message、tool_call、wait、audit 或 final_answer。
    content: 动作正文，例如消息文本或审计结论。
    target: 动作目标，例如接收者 ID；广播或无目标动作可以为空。
    metadata: 附加元数据，供环境、记录器或评估器使用。
    communication: 可选的载体来源声明；只允许 message 使用且不对外投递。
    tool_call: 可选的工具调用意图；kind 为 tool_call 时必须提供。
  """

  kind: str
  content: str | None = None
  target: str | None = None
  metadata: Mapping[str, Any] = dataclasses.field(default_factory=dict)
  communication: CommunicationIntent | None = None
  tool_call: ToolCallIntent | None = None

  def __post_init__(self) -> None:
    object.__setattr__(self, "metadata",
                       MappingProxyType(dict(self.metadata)))
    if self.communication is not None:
      if self.kind != "message" or not isinstance(
          self.communication, CommunicationIntent
      ):
        raise ValueError("communication 只能附加到 message 动作")
    if self.kind == "tool_call":
      if not isinstance(self.tool_call, ToolCallIntent):
        raise ValueError("tool_call 动作必须包含 ToolCallIntent")
      if self.content is not None or self.target is not None:
        raise ValueError("tool_call 动作不能复用消息正文或目标字段")
    elif self.tool_call is not None:
      raise ValueError("非 tool_call 动作不能包含工具调用意图")

  @classmethod
  def from_dict(
      cls,
      value: Mapping[str, Any],
      *,
      allow_communication: bool = False,
  ) -> "AgentAction":
    """从标准字典恢复动作，并默认拒绝伪造通信来源标签。

    参数：
      value: 动作字段映射；未知字段由构造器拒绝。
      allow_communication: 仅可信研究结果恢复时可设为 True；用户配置和
        模型输出必须保持 False，instrumented 标签只能由受控 codec 创建。

    返回：
      经过动作种类、工具调用和通信来源约束验证的不可变动作。
    """
    if not isinstance(value, Mapping):
      raise TypeError("动作声明必须是映射")
    data = dict(value)
    communication = data.get("communication")
    if communication is not None:
      if not allow_communication:
        raise ValueError("配置或模型输出不能声明 communication 来源")
      data["communication"] = CommunicationIntent.from_dict(communication)
    tool_call = data.get("tool_call")
    if tool_call is not None:
      data["tool_call"] = ToolCallIntent.from_dict(tool_call)
    return cls(**data)

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
      communication: CommunicationIntent | None = None,
  ) -> "AgentAction":
    """创建消息动作。

    参数：
      content: 消息正文。
      target: 消息接收目标；为空时由环境决定是否广播。
      metadata: 附加元数据。
      communication: 可选的宿主研究来源声明，不会进入实际投递消息。

    返回：
      消息动作对象。
    """
    return cls(
        kind="message",
        content=content,
        target=target,
        metadata=metadata or {},
        communication=communication,
    )

  @classmethod
  def call_tool(
      cls,
      tool: str,
      operation: str,
      *,
      arguments: Mapping[str, Any] | None = None,
      metadata: Mapping[str, Any] | None = None,
  ) -> "AgentAction":
    """创建受控工具调用动作。

    参数：
      tool: 当前节点在 NodeSpec 中获准使用的工具别名。
      operation: 工具插件定义的操作名称。
      arguments: 提交给工具的 JSON 参数。
      metadata: 只供宿主研究记录使用的动作元数据。

    返回：
      不包含公开消息正文的工具调用动作。
    """
    return cls(
        kind="tool_call",
        metadata=metadata or {},
        tool_call=ToolCallIntent(
            tool=tool,
            operation=operation,
            arguments=arguments or {},
        ),
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
