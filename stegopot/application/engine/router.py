"""根据领域拓扑把动作转换为点对点消息。"""

from __future__ import annotations

from stegopot.domain.model import AgentAction
from stegopot.domain.model import AgentMessage
from stegopot.domain.model import AgentTopology


class MessageRoutingError(ValueError):
  """消息不符合拓扑约束时抛出的异常。"""


class MessageRouter:
  """根据通信拓扑把消息动作展开成点对点消息。"""

  BROADCAST_TARGETS = frozenset({"*", "broadcast", "all"})

  def __init__(self, topology: AgentTopology) -> None:
    """初始化消息路由器。

    参数：
      topology: 用于限制消息可达范围的通信拓扑。
    """
    self._topology = topology
    self._message_counter = 0

  def reset(self) -> None:
    """重置消息 ID 计数器，用于开始一次新的运行。"""
    self._message_counter = 0

  def route(
      self,
      *,
      sender: str,
      action: AgentAction,
      round_index: int,
  ) -> tuple[AgentMessage, ...]:
    """把一个消息动作路由到一个或多个直接邻居。

    参数：
      sender: 产生该动作的节点 ID。
      action: 智能体输出的结构化动作。
      round_index: 当前运行轮次，从 0 开始。

    返回：
      为每个实际接收者分别创建的点对点消息。

    异常：
      MessageRoutingError: 消息正文为空、目标不存在或没有直连边。
    """
    if action.kind != "message":
      return ()
    if action.content is None or not str(action.content).strip():
      raise MessageRoutingError(f"节点 {sender} 发送了空消息")

    neighbors = self._topology.outgoing_neighbors(sender)
    if action.target is None or action.target in self.BROADCAST_TARGETS:
      targets = neighbors
    else:
      targets = (action.target,)

    messages = []
    for target in targets:
      if target not in self._topology.nodes:
        raise MessageRoutingError(
            f"节点 {sender} 的消息目标不存在：{target}"
        )
      if not self._topology.can_send(sender, target):
        raise MessageRoutingError(
            f"拓扑不允许节点 {sender} 向节点 {target} 发送消息"
        )
      self._message_counter += 1
      messages.append(AgentMessage(
          message_id=f"msg-{self._message_counter:06d}",
          sender=sender,
          recipient=target,
          content=str(action.content),
          round_index=round_index,
          metadata=action.metadata,
      ))
    return tuple(messages)
