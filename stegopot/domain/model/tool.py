"""受控通用工具调用使用的不可变请求、结果和记录。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from stegopot.domain.model.experiment import json_copy, validate_id


@dataclass(frozen=True)
class ToolCallIntent:
  """Policy 请求在宿主授权范围内执行一次工具操作。

  属性：
    tool: NodeSpec 为当前节点授权的工具别名。
    operation: 工具插件定义的稳定操作名称。
    arguments: 交给工具的 JSON 参数，不包含宿主凭证。
  """

  tool: str
  operation: str
  arguments: Mapping[str, Any] = field(default_factory=dict)

  def __post_init__(self) -> None:
    validate_id(self.tool)
    validate_id(self.operation)
    if not isinstance(self.arguments, Mapping):
      raise TypeError("ToolCallIntent.arguments 必须是映射")
    object.__setattr__(
        self,
        "arguments",
        MappingProxyType(json_copy(dict(self.arguments))),
    )

  @classmethod
  def from_dict(cls, value: Mapping[str, Any]) -> "ToolCallIntent":
    """从严格 JSON 对象创建工具调用意图。

    参数：
      value: 只允许 tool、operation 和 arguments 的映射。

    返回：
      经过标识和 JSON 数据校验的工具调用意图。
    """
    if not isinstance(value, Mapping) or set(value) - {"tool", "operation", "arguments"}:
      raise ValueError("tool_call 只能包含 tool/operation/arguments")
    if "tool" not in value or "operation" not in value:
      raise ValueError("tool_call 必须包含 tool 和 operation")
    return cls(
        tool=value["tool"],
        operation=value["operation"],
        arguments=value.get("arguments", {}),
    )

  def to_dict(self) -> dict[str, Any]:
    """返回适合审计和模型历史的标准调用字典。"""
    return {
        "tool": self.tool,
        "operation": self.operation,
        "arguments": json_copy(dict(self.arguments)),
    }


@dataclass(frozen=True)
class ToolRequest:
  """宿主交给单个已授权工具组件的请求。

  属性：
    operation: 工具实现支持的操作名称。
    arguments: 已通过宿主大小限制的 JSON 参数。
  """

  operation: str
  arguments: Mapping[str, Any] = field(default_factory=dict)

  def __post_init__(self) -> None:
    validate_id(self.operation)
    if not isinstance(self.arguments, Mapping):
      raise TypeError("ToolRequest.arguments 必须是映射")
    object.__setattr__(
        self,
        "arguments",
        MappingProxyType(json_copy(dict(self.arguments))),
    )

  def to_dict(self) -> dict[str, Any]:
    """返回不含凭证的标准工具请求。"""
    return {"operation": self.operation, "arguments": json_copy(dict(self.arguments))}


@dataclass(frozen=True)
class ToolResult:
  """工具执行后返回给调用节点的标准结果。

  属性：
    output: 工具产生的 JSON 数据；不会自动公开给其他节点。
    metadata: 研究所需的非凭证诊断信息。
  """

  output: Any
  metadata: Mapping[str, Any] = field(default_factory=dict)

  def __post_init__(self) -> None:
    object.__setattr__(self, "output", json_copy(self.output))
    if not isinstance(self.metadata, Mapping):
      raise TypeError("ToolResult.metadata 必须是映射")
    object.__setattr__(
        self,
        "metadata",
        MappingProxyType(json_copy(dict(self.metadata))),
    )

  def to_dict(self) -> dict[str, Any]:
    """返回可写入研究日志和节点观察的结果副本。"""
    return {"output": json_copy(self.output), "metadata": json_copy(dict(self.metadata))}


@dataclass(frozen=True)
class ToolCallRecord:
  """一次工具调用在运行结果中的节点私有记录。

  属性：
    node_id: 发起调用的节点 ID。
    tool: 节点配置中的授权工具别名。
    operation: 被执行的工具操作。
    result: 成功时返回的工具结果。
    error: 非快速失败模式下保留的错误分类；成功时为空。
  """

  node_id: str
  tool: str
  operation: str
  result: ToolResult | None = None
  error: str | None = None

  def __post_init__(self) -> None:
    validate_id(self.node_id)
    validate_id(self.tool)
    validate_id(self.operation)
    if self.result is not None and not isinstance(self.result, ToolResult):
      raise TypeError("ToolCallRecord.result 必须是 ToolResult 或 None")
    if self.error is not None and not isinstance(self.error, str):
      raise TypeError("ToolCallRecord.error 必须是字符串或 None")

  def to_dict(self) -> dict[str, Any]:
    """返回适合研究结果的标准调用记录。"""
    return {
        "node_id": self.node_id,
        "tool": self.tool,
        "operation": self.operation,
        "result": None if self.result is None else self.result.to_dict(),
        "error": self.error,
    }
