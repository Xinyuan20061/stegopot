"""多智能体运行中的点对点消息。"""

from __future__ import annotations

from collections.abc import Mapping
import dataclasses
from types import MappingProxyType
from typing import Any


@dataclasses.dataclass(frozen=True)
class AgentMessage:
  """拓扑路由后产生的一条不可变点对点消息。

  属性：
    message_id: 单次运行内唯一且递增的消息 ID。
    sender: 发送节点 ID。
    recipient: 实际接收节点 ID。
    content: 消息正文。
    round_index: 发送消息的同步轮次，从 0 开始。
    metadata: 从智能体动作继承的附加元数据。
  """

  message_id: str
  sender: str
  recipient: str
  content: str
  round_index: int
  metadata: Mapping[str, Any] = dataclasses.field(default_factory=dict)

  def __post_init__(self) -> None:
    object.__setattr__(
        self,
        "metadata",
        MappingProxyType(dict(self.metadata)),
    )

  def to_dict(self) -> dict[str, Any]:
    """返回适合日志记录和 JSON 序列化的消息字典。"""
    return {
        "message_id": self.message_id,
        "sender": self.sender,
        "recipient": self.recipient,
        "content": self.content,
        "round_index": self.round_index,
        "metadata": dict(self.metadata),
    }
